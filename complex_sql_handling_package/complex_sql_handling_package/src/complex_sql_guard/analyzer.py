from __future__ import annotations

from typing import Dict, List

from .dialect import get_dialect_profile
from .models import AnalysisStatus, ComplexSqlAnalysisResult, Diagnostic, ParseStatus, Severity
from .parser_adapter import ParserAdapter, SqlglotParserAdapter
from .preflight import PreflightChecker, PreflightOptions
from .segmenter import SqlSegmenter
from .shields import DirtySqlPreprocessor, ShieldOptions


class ComplexSqlAnalyzer:
    """Complex SQL defensive analysis orchestrator.

    This module should be placed before ScopeResolver/NameResolver/LineageEngine.
    It turns fragile production SQL into a safer analysis bundle and never mutates
    original_sql.
    """

    def __init__(
        self,
        parser: ParserAdapter | None = None,
        preflight: PreflightChecker | None = None,
        preprocessor: DirtySqlPreprocessor | None = None,
        segmenter: SqlSegmenter | None = None,
    ) -> None:
        self.parser = parser or SqlglotParserAdapter()
        self.preflight = preflight or PreflightChecker()
        self.preprocessor = preprocessor or DirtySqlPreprocessor()
        self.segmenter = segmenter or SqlSegmenter()

    def analyze(self, sql: str, dialect: str = "spark") -> ComplexSqlAnalysisResult:
        profile = get_dialect_profile(dialect)
        diagnostics: List[Diagnostic] = []

        preflight_report = self.preflight.check(sql)
        diagnostics.extend(preflight_report.diagnostics)

        text_bundle, preprocess_diags = self.preprocessor.preprocess(sql)
        diagnostics.extend(preprocess_diags)

        segments = self.segmenter.segment(text_bundle.analysis_sql)

        parse_attempts = []
        # Attempt original first. If production templates are present, this may fail.
        parse_attempts.append(self.parser.parse(text_bundle.original_sql, profile.parser_dialect, "original_sql"))
        if parse_attempts[-1].status != ParseStatus.SUCCESS:
            parse_attempts.append(self.parser.parse(text_bundle.normalized_sql, profile.parser_dialect, "normalized_sql"))
        if parse_attempts[-1].status != ParseStatus.SUCCESS:
            parse_attempts.append(self.parser.parse(text_bundle.analysis_sql, profile.parser_dialect, "analysis_sql"))

        for attempt in parse_attempts:
            diagnostics.extend(attempt.diagnostics)

        full_parse_success = any(a.status == ParseStatus.SUCCESS for a in parse_attempts)
        segment_parse_success = False

        if not full_parse_success:
            for segment in segments:
                # Very small or placeholder-only segments do not need parser attempts.
                if not segment.raw_text.strip():
                    continue
                attempt = self.parser.parse(segment.raw_text, profile.parser_dialect, segment.segment_id)
                segment.parse_status = attempt.status
                segment.diagnostics.extend(attempt.diagnostics)
                diagnostics.extend(attempt.diagnostics)
                if attempt.status == ParseStatus.SUCCESS:
                    segment_parse_success = True

        if full_parse_success:
            status = AnalysisStatus.SUCCESS
        elif segments:
            status = AnalysisStatus.PARTIAL
            diagnostics.append(Diagnostic(
                code="PARTIAL_PARSE_RESULT",
                severity=Severity.WARNING,
                message="Full SQL parse failed or was unavailable; segment-level result is returned.",
                stage="analyze",
                confidence=0.8,
            ))
        else:
            status = AnalysisStatus.FAILED

        capabilities: Dict[str, object] = {
            "full_parse": full_parse_success,
            "segment_parse": segment_parse_success or bool(segments),
            "literal_shield": True,
            "template_shield": True,
            "lineage_ready": full_parse_success or bool(segments),
            "placeholder_count": len(text_bundle.placeholders),
            "segment_count": len(segments),
        }
        confidence = {
            "parse": 1.0 if full_parse_success else 0.45,
            "segment": 0.9 if segments else 0.0,
            "lineage_ready": 0.85 if full_parse_success else (0.6 if segments else 0.0),
        }

        return ComplexSqlAnalysisResult(
            status=status,
            dialect=profile.name,
            text_bundle=text_bundle,
            preflight_report=preflight_report,
            segments=segments,
            parse_attempts=parse_attempts,
            diagnostics=diagnostics,
            capabilities=capabilities,
            confidence=confidence,
        )
