"""Static contract checks for the production dirty-SQL lineage corpus."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_FUNCTION_FAMILIES: dict[str, tuple[str, ...]] = {
    "regular_expression": ("regexp_replace", "regexp_extract", "rlike"),
    "json": ("get_json_object", "from_json", "json_tuple"),
    "array_expansion": ("explode", "posexplode", "inline"),
    "window": (" over ",),
    "aggregate": ("sum(", "count(", "avg(", "max(", "min("),
    "conditional": ("case ", "if("),
    "datetime": ("date_", "to_date(", "unix_timestamp(", "from_unixtime("),
}

CTE_ALIAS_PATTERN = re.compile(
    r"(?:\bwith|,)\s*([a-zA-Z_][\w$]*)\s+as\s*\(", re.IGNORECASE
)
INLINE_ALIAS_PATTERN = re.compile(
    r"\)\s+(?:as\s+)?([a-zA-Z_][\w$]*)\s*(?:on\b|where\b|group\b|"
    r"order\b|join\b|(?:left|right|full|inner|outer|cross)(?:\s+outer)?\s+join\b|,|\)|$)",
    re.IGNORECASE | re.MULTILINE,
)
PHYSICAL_TABLE_PATTERN = re.compile(
    r"\b(?:from|join)\s+([a-zA-Z_][\w$]*(?:\.[a-zA-Z_][\w$]*){1,2})",
    re.IGNORECASE,
)
COMMENT_PATTERN = re.compile(r"--[^\n]*|/\*[\s\S]*?\*/")
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
REGEX_BACKSLASH_PATTERN = re.compile(r"\\{1,2}[dswDSW]|\\{1,2}u[0-9a-fA-F]{4}")


def _strip_sql_comments(sql: str) -> str:
    """Mask comment content while retaining line boundaries for structure patterns."""
    return COMMENT_PATTERN.sub(
        lambda match: re.sub(r"[^\r\n]", " ", match.group(0)), sql
    )


def _function_families(sql: str) -> dict[str, bool]:
    normalized_sql = sql.lower()
    return {
        family: any(marker in normalized_sql for marker in markers)
        for family, markers in REQUIRED_FUNCTION_FAMILIES.items()
    }


def inspect_case(path: Path) -> dict[str, object]:
    """Return deterministic static lineage-corpus evidence for one SQL case."""
    sql = path.read_text(encoding="utf-8")
    comments = COMMENT_PATTERN.findall(sql)
    structural_sql = _strip_sql_comments(sql)
    cte_aliases = sorted(set(CTE_ALIAS_PATTERN.findall(structural_sql)))
    inline_aliases = sorted(set(INLINE_ALIAS_PATTERN.findall(structural_sql)))
    physical_tables = sorted(set(PHYSICAL_TABLE_PATTERN.findall(structural_sql)))
    function_families = _function_families(structural_sql)
    chinese_comment_count = sum(bool(CHINESE_PATTERN.search(comment)) for comment in comments)
    regex_backslash_count = len(REGEX_BACKSLASH_PATTERN.findall(structural_sql))
    named_relation_count = len(cte_aliases) + len(inline_aliases) + len(physical_tables)
    has_dirty_sql_markers = bool(
        chinese_comment_count
        and regex_backslash_count
        and all(function_families.values())
    )

    result: dict[str, object] = {
        "file": path.name,
        "line_count": len(sql.splitlines()),
        "cte_alias_count": len(cte_aliases),
        "inline_or_scalar_alias_count": len(inline_aliases),
        "physical_table_reference_count": len(physical_tables),
        "named_relation_count": named_relation_count,
        "chinese_comment_count": chinese_comment_count,
        "regex_backslash_count": regex_backslash_count,
        "required_function_families": function_families,
        "has_dirty_sql_markers": has_dirty_sql_markers,
    }
    result["static_contract_passed"] = bool(
        result["line_count"] >= 300
        and named_relation_count >= 26
        and has_dirty_sql_markers
    )
    return result


def validate_corpus(corpus_dir: Path) -> list[dict[str, object]]:
    """Inspect each standalone SQL workload in lexical filename order."""
    return [inspect_case(path) for path in sorted(corpus_dir.glob("*.sql"))]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "测试用例"
        / "血缘压测_生产脏SQL_20260719",
    )
    parser.add_argument("--cases", nargs="*", help="Optional filename prefixes, e.g. 01 02")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = validate_corpus(args.corpus_dir)
    if args.cases:
        report = [item for item in report if str(item["file"]).startswith(tuple(args.cases))]

    output_path = args.corpus_dir / "validation_report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report and all(item["static_contract_passed"] for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
