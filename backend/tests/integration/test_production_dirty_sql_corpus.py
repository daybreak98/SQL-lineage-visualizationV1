from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
from tools.validate_production_dirty_sql_corpus import inspect_case, validate_corpus


CORPUS_DIR = REPOSITORY_ROOT / "测试用例" / "血缘压测_生产脏SQL_20260719"


def test_production_dirty_sql_corpus_meets_static_contract():
    report = validate_corpus(CORPUS_DIR)

    assert len(report) == 10
    assert all(item["line_count"] >= 300 for item in report)
    assert all(item["named_relation_count"] >= 26 for item in report)
    assert all(item["has_dirty_sql_markers"] for item in report)


def test_static_inspection_ignores_comment_sql_and_counts_left_outer_join_alias(
    tmp_path: Path,
):
    case_path = tmp_path / "comment_noise.sql"
    case_path.write_text(
        """-- 中文注释：FROM ignored.lineage_table regexp_replace(raw, '\\\\s+', ' ')
/* 中文块注释：JOIN ignored.block_table get_json_object(payload, '$.id') */
WITH source_rows AS (
    SELECT id
    FROM mart.real_source
),
joined_rows AS (
    SELECT source_rows.id
    FROM (SELECT id FROM mart.inline_source) inline_rows
    LEFT OUTER JOIN mart.real_lookup lookup_rows
        ON inline_rows.id = lookup_rows.id
)
SELECT * FROM joined_rows
""",
        encoding="utf-8",
    )

    result = inspect_case(case_path)

    assert result["physical_table_reference_count"] == 3
    assert result["inline_or_scalar_alias_count"] == 1
    assert result["regex_backslash_count"] == 0
    assert result["required_function_families"]["regular_expression"] is False
    assert result["chinese_comment_count"] == 2
