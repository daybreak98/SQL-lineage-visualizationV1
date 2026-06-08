from __future__ import annotations

from collections.abc import Mapping
import time

from . import diagnostics as diag_codes
from .dialect import DialectProfile, get_dialect_profile
from .feature_tagger import detect_dialect_features
from .models import (
    AnalysisStatus,
    ComplexSqlAnalysisResult,
    Diagnostic,
    ParseStageStatus,
    ParseStatus,
    Severity,
)
from .normalizer import OffsetLocator
from .parser_adapter import ParserAdapter, SqlglotParserAdapter
from .preflight import PreflightChecker, PreflightOptions
from .script_cleaner import select_analysis_statement
from .segmenter import SqlSegmenter
from .shields import DirtySqlPreprocessor, ShieldOptions


class ComplexSqlAnalyzer:
    def __init__(self, parser: ParserAdapter | None = None) -> None:
        self.parser = parser or SqlglotParserAdapter()

    def analyze(
        self,
        sql: str,
        dialect: str = "spark",
        options: Mapping[str, object] | None = None,
    ) -> ComplexSqlAnalysisResult:
        opts = dict(options or {})
        profile = get_dialect_profile(dialect)

        preflight = PreflightChecker(self._preflight_options(opts))
        preprocessor = DirtySqlPreprocessor(self._shield_options(opts))
        segmenter = SqlSegmenter(max_segments=int(opts.get("max_segments", 500)))

        diagnostics: list[Diagnostic] = []
        stage_statuses: list[ParseStageStatus] = []
        unsupported_features: list[str] = []

        stage_started = time.perf_counter()
        preflight_report = preflight.check(sql)
        hard_preflight_error = any(diagnostic.severity == Severity.ERROR for diagnostic in preflight_report.diagnostics)
        diagnostics.extend(preflight_report.diagnostics)
        stage_statuses.append(self._stage_status(
            "preflight",
            stage_started,
            preflight_report.diagnostics,
            "SQL preflight checks completed.",
        ))

        stage_started = time.perf_counter()
        statement_selection = select_analysis_statement(sql)
        diagnostics.extend(statement_selection.diagnostics)
        stage_statuses.append(self._stage_status(
            "statement_clean",
            stage_started,
            statement_selection.diagnostics,
            "Statement cleaning and analyzable query selection completed.",
        ))

        stage_started = time.perf_counter()
        selected_sql = statement_selection.analysis_sql or sql
        feature_result = detect_dialect_features(
            selected_sql,
            original_sql=sql,
            offset_shift=statement_selection.start_offset,
        )
        diagnostics.extend(feature_result.diagnostics)
        unsupported_features.extend(feature_result.risk_features)
        stage_statuses.append(self._stage_status(
            "feature_detect",
            stage_started,
            feature_result.diagnostics,
            "Dialect feature tagging completed for selected analysis SQL.",
        ))

        stage_started = time.perf_counter()
        text_bundle, preprocess_diagnostics = preprocessor.preprocess(selected_sql)
        text_bundle = self._rebase_text_bundle(
            text_bundle,
            original_sql=sql,
            offset_shift=statement_selection.start_offset,
        )
        preprocess_diagnostics = self._rebase_diagnostics(
            preprocess_diagnostics,
            original_sql=sql,
            offset_shift=statement_selection.start_offset,
        )
        diagnostics.extend(preprocess_diagnostics)
        stage_statuses.append(self._stage_status(
            "preprocess",
            stage_started,
            preprocess_diagnostics,
            "Dirty SQL preprocessing and shielding completed.",
        ))

        stage_started = time.perf_counter()
        segments = segmenter.segment(
            text_bundle.analysis_sql,
            original_sql=text_bundle.original_sql,
            offset_mapping=text_bundle.offset_mapping,
        )
        if any(segment.segment_type == "lateral_view" for segment in segments):
            diagnostics.append(Diagnostic(
                code=diag_codes.UNSUPPORTED_LATERAL_VIEW,
                severity=Severity.WARNING,
                message="lateral view is detected; lineage will use defensive mode.",
                stage="segment",
                confidence=0.65,
            ))
            unsupported_features.append("lateral_view")
        stage_statuses.append(self._stage_status(
            "segment",
            stage_started,
            [diagnostic for diagnostic in diagnostics if diagnostic.stage == "segment"],
            "Best-effort SQL segmentation completed.",
        ))

        parse_attempts = []
        selected_attempt = None
        seen_targets: set[str] = set()
        target_prefix = (
            f"{statement_selection.selected_target}:"
            if statement_selection.selected_target != "analysis_sql" or statement_selection.selected_kind != "full_script"
            else ""
        )
        parse_candidates = [
            (f"{target_prefix}original_sql", selected_sql),
            (f"{target_prefix}normalized_sql", text_bundle.normalized_sql),
            (f"{target_prefix}analysis_sql", text_bundle.analysis_sql),
        ]

        stage_started = time.perf_counter()
        for target, candidate_sql in parse_candidates:
            if candidate_sql in seen_targets:
                continue
            seen_targets.add(candidate_sql)
            attempt = self.parser.parse(candidate_sql, profile.parser_dialect, target)
            parse_attempts.append(attempt)
            diagnostics.extend(attempt.diagnostics)
            if attempt.status == ParseStatus.SUCCESS and selected_attempt is None:
                selected_attempt = attempt
                break

        if selected_attempt is None and segments:
            diagnostics.append(Diagnostic(
                code=diag_codes.SEGMENT_PARSE_FALLBACK,
                severity=Severity.WARNING,
                message="Full SQL parse failed; segment-level fallback is enabled.",
                stage="sql_parse",
                confidence=0.6,
            ))

        stage_statuses.append(self._stage_status(
            "sql_parse",
            stage_started,
            [diagnostic for diagnostic in diagnostics if diagnostic.stage == "sql_parse"],
            "sqlglot parse attempts completed.",
        ))

        segment_parse_success = False
        segment_parse_attempted = False
        stage_started = time.perf_counter()
        enable_segment_parse = bool(opts.get("enable_segment_parse", True))
        if selected_attempt is None and enable_segment_parse:
            for segment in segments:
                candidate_sql = self._segment_sql_for_parse(segment.segment_type, segment.raw_text)
                if not candidate_sql:
                    continue
                segment_parse_attempted = True
                attempt = self.parser.parse(candidate_sql, profile.parser_dialect, segment.segment_id)
                if attempt.status == ParseStatus.SUCCESS and self._is_useful_segment_parse(segment.segment_type, attempt.tree):
                    segment.parse_status = ParseStatus.SUCCESS
                    segment_parse_success = True
                elif attempt.status == ParseStatus.SUCCESS:
                    segment.parse_status = ParseStatus.PARTIAL
                else:
                    segment.parse_status = ParseStatus.FAILED
                segment.diagnostics.extend(attempt.diagnostics)
                diagnostics.extend(attempt.diagnostics)

        if selected_attempt is not None:
            stage_statuses.append(ParseStageStatus(
                stage="segment_parse",
                status="skipped",
                elapsed_ms=int((time.perf_counter() - stage_started) * 1000),
                diagnostic_codes=[],
                message="Segment-level parser fallback was not needed.",
            ))
        else:
            segment_diagnostics = [diagnostic for diagnostic in diagnostics if diagnostic.stage == "segment_parse"]
            stage_statuses.append(self._stage_status(
                "segment_parse",
                stage_started,
                segment_diagnostics,
                "Segment-level parser fallback completed." if enable_segment_parse else "Segment-level parser fallback is disabled.",
                force_status="success" if segment_parse_success else ("partial" if segment_parse_attempted else "failed"),
            ))

        if selected_attempt is not None:
            self._collect_tree_diagnostics(selected_attempt.tree, profile, diagnostics, unsupported_features)

        if selected_attempt is None and segment_parse_success:
            diagnostics.append(Diagnostic(
                code=diag_codes.PARTIAL_PARSE_RESULT,
                severity=Severity.WARNING,
                message="Partial parse result is returned from guarded preprocessing and segment fallback.",
                stage="analyze",
                confidence=0.6,
            ))
            diagnostics.append(Diagnostic(
                code=diag_codes.LOW_CONFIDENCE_LINEAGE,
                severity=Severity.WARNING,
                message="Lineage confidence is reduced because the full SQL parse did not succeed.",
                stage="analyze",
                confidence=0.45,
            ))
        elif hard_preflight_error:
            diagnostics.append(Diagnostic(
                code=diag_codes.LOW_CONFIDENCE_LINEAGE,
                severity=Severity.WARNING,
                message="Lineage confidence is reduced because preflight checks reported blocking risk.",
                stage="analyze",
                confidence=0.35,
            ))
        elif unsupported_features:
            diagnostics.append(Diagnostic(
                code=diag_codes.LOW_CONFIDENCE_LINEAGE,
                severity=Severity.WARNING,
                message="Lineage confidence is reduced because unsupported structures were detected.",
                stage="analyze",
                confidence=0.55,
            ))

        if selected_attempt is not None and hard_preflight_error:
            status = AnalysisStatus.PARTIAL
        elif selected_attempt is not None:
            status = AnalysisStatus.SUCCESS
        elif segment_parse_success:
            status = AnalysisStatus.PARTIAL
        else:
            status = AnalysisStatus.FAILED

        capabilities = self._capabilities(
            selected_attempt is not None,
            segment_parse_success,
            text_bundle,
            segments,
            statement_selection,
            feature_result.features,
            feature_result.risk_features,
        )
        confidence = self._confidence(
            selected_attempt is not None,
            segment_parse_success,
            unsupported_features,
            segments,
            hard_preflight_error=hard_preflight_error,
            feature_confidence_cap=feature_result.confidence_cap,
        )

        return ComplexSqlAnalysisResult(
            status=status,
            dialect=profile.name,
            text_bundle=text_bundle,
            preflight_report=preflight_report,
            segments=segments,
            parse_attempts=parse_attempts,
            diagnostics=self._dedupe_diagnostics(diagnostics),
            stage_statuses=stage_statuses,
            capabilities=capabilities,
            confidence=confidence,
            unsupported_features=sorted(set(unsupported_features)),
            selected_target=selected_attempt.target if selected_attempt is not None else statement_selection.selected_target,
            selected_tree=selected_attempt.tree if selected_attempt is not None else None,
        )

    def _preflight_options(self, options: Mapping[str, object]) -> PreflightOptions:
        return PreflightOptions(
            max_sql_chars=int(options.get("max_sql_chars", 200_000)),
            warn_sql_chars=int(options.get("warn_sql_chars", 50_000)),
            warn_line_count=int(options.get("warn_line_count", 800)),
            complex_score_threshold=int(options.get("complex_score_threshold", 8)),
        )

    def _shield_options(self, options: Mapping[str, object]) -> ShieldOptions:
        return ShieldOptions(
            shield_string_literals=bool(options.get("enable_literal_shield", True)),
            shield_templates=bool(options.get("enable_template_shield", True)),
            shield_comments=bool(options.get("enable_comment_shield", True)),
            shield_quoted_identifiers=bool(options.get("enable_quoted_identifier_shield", False)),
        )

    def _stage_status(
        self,
        stage: str,
        started: float,
        diagnostics: list[Diagnostic],
        message: str,
        *,
        force_status: str | None = None,
    ) -> ParseStageStatus:
        elapsed = int((time.perf_counter() - started) * 1000)
        diagnostic_codes = [diagnostic.code for diagnostic in diagnostics]
        if force_status is not None:
            status = force_status
        elif any(diagnostic.severity == Severity.ERROR for diagnostic in diagnostics):
            status = "failed"
        elif diagnostics:
            status = "partial"
        else:
            status = "success"
        return ParseStageStatus(
            stage=stage,
            status=status,
            elapsed_ms=elapsed,
            diagnostic_codes=diagnostic_codes,
            message=message,
        )

    def _segment_sql_for_parse(self, segment_type: str, raw_text: str) -> str | None:
        text = raw_text.strip()
        if not text:
            return None
        if segment_type in {"statement", "main_select"}:
            return text
        if segment_type == "cte_item":
            lowered = text.lower()
            as_index = lowered.find(" as ")
            if as_index >= 0:
                open_paren = text.find("(", as_index)
                close_paren = text.rfind(")")
                if open_paren >= 0 and close_paren > open_paren:
                    return text[open_paren + 1:close_paren].strip()
        if segment_type == "from_join":
            return f"select 1 {text}"
        if segment_type in {"from_source", "join_block", "lateral_view"}:
            return f"select 1 from t {text}"
        if segment_type in {"where", "group_by", "having", "order_by"}:
            return f"select 1 from t {text}"
        if segment_type == "join_condition":
            return f"select 1 from t join u {text}"
        return None

    def _is_useful_segment_parse(self, segment_type: str, tree) -> bool:
        if tree is None:
            return False

        from_expr = tree.args.get("from_") or tree.args.get("from")
        if segment_type in {"statement", "cte_item"}:
            return bool(getattr(tree, "selects", None))
        if segment_type == "main_select":
            return bool(getattr(tree, "selects", None))
        if segment_type in {"from_join", "from_source", "join_block"}:
            return from_expr is not None
        if segment_type == "lateral_view":
            try:
                from sqlglot import exp
            except Exception:
                return False
            return any(tree.find_all(exp.Lateral))
        if segment_type in {"where", "group_by", "having", "order_by", "join_condition"}:
            return from_expr is not None
        return False

    def _collect_tree_diagnostics(
        self,
        tree,
        profile: DialectProfile,
        diagnostics: list[Diagnostic],
        unsupported_features: list[str],
    ) -> None:
        try:
            from sqlglot import exp
        except Exception:
            return

        if any(tree.find_all(exp.Lateral)):
            diagnostics.append(Diagnostic(
                code=diag_codes.UNSUPPORTED_LATERAL_VIEW,
                severity=Severity.WARNING,
                message="lateral view is parsed but downstream lineage only has defensive support.",
                stage="analyze",
                confidence=0.6,
            ))
            unsupported_features.append("lateral_view")

        known_functions = {
            *profile.function_registry.transparent_functions,
            *profile.function_registry.regex_functions,
            *profile.function_registry.json_functions,
            *profile.udtf_registry.row_expanding_functions,
        }
        for node in tree.find_all(exp.Anonymous):
            function_name = (getattr(node, "name", "") or "").lower()
            if not function_name or function_name in known_functions:
                continue
            diagnostics.append(Diagnostic(
                code=diag_codes.BLACK_BOX_UDF,
                severity=Severity.WARNING,
                message=f"Black-box UDF {function_name} is detected; lineage will keep only defensive diagnostics.",
                stage="analyze",
                confidence=0.55,
                extra={"function_name": function_name},
            ))
            unsupported_features.append(f"udf:{function_name}")

    def _capabilities(
        self,
        full_parse_success: bool,
        segment_parse_success: bool,
        text_bundle,
        segments,
        statement_selection,
        detected_features: dict[str, int],
        risk_features: list[str],
    ) -> dict[str, object]:
        return {
            "table_lineage": full_parse_success,
            "subquery_lineage": full_parse_success,
            "column_lineage": full_parse_success,
            "complex_sql_guard": True,
            "statement_clean": True,
            "full_parse": full_parse_success,
            "segment_parse": segment_parse_success,
            "literal_shield": True,
            "template_shield": True,
            "placeholder_count": len(text_bundle.placeholders),
            "segment_count": len(segments),
            "statement_count": statement_selection.statement_count,
            "skipped_statement_count": statement_selection.skipped_count,
            "selected_statement_kind": statement_selection.selected_kind,
            "dialect_feature_tagging": True,
            "dialect_features": detected_features,
            "dialect_feature_risks": risk_features,
        }

    def _confidence(
        self,
        full_parse_success: bool,
        segment_parse_success: bool,
        unsupported_features: list[str],
        segments,
        *,
        hard_preflight_error: bool = False,
        feature_confidence_cap: float | None = None,
    ) -> dict[str, float]:
        parse_confidence = 0.95 if full_parse_success else (0.5 if segment_parse_success else 0.0)
        if hard_preflight_error:
            parse_confidence = min(parse_confidence, 0.6)
            lineage_confidence = 0.35
        elif unsupported_features:
            lineage_confidence = 0.55 if full_parse_success else 0.35
        else:
            lineage_confidence = 0.85 if full_parse_success else (0.45 if segment_parse_success else 0.0)
        if feature_confidence_cap is not None:
            lineage_confidence = min(lineage_confidence, feature_confidence_cap)
        return {
            "parse": parse_confidence,
            "segment_parse": 0.8 if segment_parse_success else 0.0,
            "lineage": lineage_confidence,
        }

    def _dedupe_diagnostics(self, diagnostics: list[Diagnostic]) -> list[Diagnostic]:
        seen: set[tuple[str, str, str]] = set()
        result: list[Diagnostic] = []
        for diagnostic in diagnostics:
            key = (diagnostic.code, diagnostic.stage, diagnostic.message)
            if key in seen:
                continue
            seen.add(key)
            result.append(diagnostic)
        return result

    def _rebase_text_bundle(self, text_bundle, *, original_sql: str, offset_shift: int):
        if offset_shift <= 0 and text_bundle.original_sql == original_sql:
            return text_bundle

        locator = OffsetLocator(original_sql)
        placeholders = []
        for placeholder in text_bundle.placeholders:
            rebased_location = self._rebase_location(
                placeholder.location,
                locator=locator,
                offset_shift=offset_shift,
            )
            placeholders.append(placeholder.__class__(
                placeholder=placeholder.placeholder,
                kind=placeholder.kind,
                raw_text=placeholder.raw_text,
                location=rebased_location,
            ))

        offset_mapping = text_bundle.offset_mapping
        rebased_mapping = offset_mapping.__class__(
            original_length=len(original_sql),
            normalized_to_original=[offset + offset_shift for offset in offset_mapping.normalized_to_original],
            analysis_to_original=[offset + offset_shift for offset in offset_mapping.analysis_to_original],
        ) if offset_mapping is not None else None

        return text_bundle.__class__(
            original_sql=original_sql,
            normalized_sql=text_bundle.normalized_sql,
            analysis_sql=text_bundle.analysis_sql,
            placeholders=placeholders,
            offset_mapping=rebased_mapping,
        )

    def _rebase_diagnostics(self, diagnostics: list[Diagnostic], *, original_sql: str, offset_shift: int) -> list[Diagnostic]:
        if offset_shift <= 0:
            return diagnostics

        locator = OffsetLocator(original_sql)
        return [
            Diagnostic(
                code=diagnostic.code,
                severity=diagnostic.severity,
                message=diagnostic.message,
                stage=diagnostic.stage,
                location=self._rebase_location(diagnostic.location, locator=locator, offset_shift=offset_shift),
                confidence=diagnostic.confidence,
                extra=diagnostic.extra,
            )
            for diagnostic in diagnostics
        ]

    def _rebase_location(self, location, *, locator: OffsetLocator, offset_shift: int):
        if location is None:
            return None
        return locator.location(
            location.start_offset + offset_shift,
            location.end_offset + offset_shift,
        )


def analyze_complex_sql(
    sql: str,
    dialect: str = "spark",
    options: Mapping[str, object] | None = None,
) -> ComplexSqlAnalysisResult:
    return ComplexSqlAnalyzer().analyze(sql, dialect=dialect, options=options)
