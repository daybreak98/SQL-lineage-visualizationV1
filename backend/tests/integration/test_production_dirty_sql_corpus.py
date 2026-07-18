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
    assert all(item["has_cte"] for item in report)
    assert all(item["has_inline_or_scalar_subquery"] for item in report)
    assert all(item["has_join"] for item in report)
    assert all(item["has_set_operation"] for item in report)
    assert all(item["is_spark_sql"] for item in report)
    assert all(item["has_single_final_query"] for item in report)


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


def test_static_inspection_enforces_single_spark_query_structure(tmp_path: Path):
    valid_case = tmp_path / "single_query.sql"
    valid_case.write_text(
        """-- 注释中的分号; 不能拆分语句
WITH source_rows AS (
    SELECT id, ';' AS literal_semicolon
    FROM mart.real_source
),
joined_rows AS (
    SELECT source_rows.id
    FROM (SELECT id FROM mart.inline_source) inline_rows
    INNER JOIN mart.real_lookup lookup_rows
        ON inline_rows.id = lookup_rows.id
),
combined_rows AS (
    SELECT id FROM joined_rows
    UNION ALL
    SELECT id FROM source_rows
)
SELECT explode(array(id)) AS id
FROM combined_rows;
""",
        encoding="utf-8",
    )
    multiple_statements_case = tmp_path / "multiple_queries.sql"
    multiple_statements_case.write_text(
        "SELECT 1 AS first_query; SELECT 2 AS second_query;",
        encoding="utf-8",
    )

    valid_result = inspect_case(valid_case)
    multiple_result = inspect_case(multiple_statements_case)

    assert valid_result["has_cte"] is True
    assert valid_result["has_inline_or_scalar_subquery"] is True
    assert valid_result["has_join"] is True
    assert valid_result["has_set_operation"] is True
    assert valid_result["is_spark_sql"] is True
    assert valid_result["executable_statement_count"] == 1
    assert valid_result["has_single_final_query"] is True
    assert multiple_result["executable_statement_count"] == 2
    assert multiple_result["has_single_final_query"] is False
