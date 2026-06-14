from __future__ import annotations

from dataclasses import dataclass, field
import re

from . import diagnostics as diag_codes
from .models import Diagnostic, Severity
from .normalizer import OffsetLocator


@dataclass
class FeatureDetectionResult:
    features: dict[str, int] = field(default_factory=dict)
    supported_features: list[str] = field(default_factory=list)
    requires_handlers: list[str] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    risk_features: list[str] = field(default_factory=list)
    confidence_cap: float | None = None


_FEATURE_SPECS = [
    (
        "map_access",
        re.compile(r"(?P<base>[A-Za-z_][\w.]*?)\s*\[\s*(?P<key>'[^']+'|\"[^\"]+\")\s*\]"),
        diag_codes.MAP_ACCESS_DETECTED,
        "Detected Hive/Spark map access expression.",
    ),
    (
        "json_func",
        re.compile(r"(?is)\b(get_json_object|json_tuple|from_json|json_map|json_parse)\s*\("),
        diag_codes.JSON_EXTRACTION_FUNCTION_DETECTED,
        "Detected JSON extraction function.",
    ),
    (
        "group_by_ordinal",
        re.compile(r"(?is)\bgroup\s+by\s+\d+(?:\s*,\s*\d+)*\b"),
        diag_codes.GROUP_BY_ORDINAL_DETECTED,
        "Detected GROUP BY ordinal expression.",
    ),
    (
        "chinese_backtick_alias",
        re.compile(r"`[^`]*[\u4e00-\u9fff][^`]*`"),
        diag_codes.QUOTED_CHINESE_ALIAS_DETECTED,
        "Detected quoted Chinese alias.",
    ),
    (
        "count_distinct",
        re.compile(r"(?is)\bcount\s*\(\s*distinct\b"),
        diag_codes.COUNT_DISTINCT_DETECTED,
        "Detected count(distinct ...) metric expression.",
    ),
    (
        "case_when",
        re.compile(r"(?is)\bcase\s+when\b"),
        diag_codes.CASE_WHEN_DETECTED,
        "Detected CASE WHEN expression.",
    ),
]

_RISK_FEATURES = {
    "group_by_ordinal": 0.72,
    "chinese_backtick_alias": 0.78,
}

_FEATURE_CLASSIFICATION = {
    "count_distinct": "supported",
    "case_when": "supported",
    "chinese_backtick_alias": "supported",
    "group_by_ordinal": "requires_handler",
    "json_func": "requires_handler",
    "map_access": "requires_handler",
    "lateral_view": "requires_handler",
    "dynamic_sql": "unsupported",
    "recursive_cte": "unsupported",
    "unresolved_macro": "unsupported",
    "severe_syntax_damage": "unsupported",
}


def detect_dialect_features(
    sql: str,
    *,
    original_sql: str | None = None,
    offset_shift: int = 0,
    stage: str = "feature_detect",
) -> FeatureDetectionResult:
    locator = OffsetLocator(original_sql or sql)
    features: dict[str, int] = {}
    diagnostics: list[Diagnostic] = []
    risk_features: list[str] = []
    supported: list[str] = []
    requires_handler: list[str] = []
    unsupported: list[str] = []
    confidence_cap: float | None = None

    for feature_name, regex, code, message in _FEATURE_SPECS:
        matches = list(regex.finditer(sql))
        if not matches:
            continue
        features[feature_name] = len(matches)

        classification = _FEATURE_CLASSIFICATION.get(feature_name, "unsupported")
        if classification == "supported":
            supported.append(feature_name)
        elif classification == "requires_handler":
            requires_handler.append(feature_name)
        else:
            unsupported.append(feature_name)

        if feature_name in _RISK_FEATURES:
            risk_features.append(feature_name)
            cap = _RISK_FEATURES[feature_name]
            confidence_cap = cap if confidence_cap is None else min(confidence_cap, cap)
        first = matches[0]
        diagnostics.append(Diagnostic(
            code=code,
            severity=Severity.INFO,
            message=message,
            stage=stage,
            location=locator.location(first.start() + offset_shift, first.end() + offset_shift),
            confidence=0.95,
            extra={
                "feature": feature_name,
                "count": len(matches),
                "sample": first.group(0)[:120],
            },
        ))

    return FeatureDetectionResult(
        features=features,
        supported_features=supported,
        requires_handlers=requires_handler,
        unsupported_features=unsupported,
        diagnostics=diagnostics,
        risk_features=sorted(set(risk_features)),
        confidence_cap=confidence_cap,
    )
