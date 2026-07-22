from app.complex_sql_guard.script_cleaner import select_analysis_statement


def test_selects_last_query_from_multi_statement_script():
    sql = """
set hive.exec.dynamic.partition=true;
add jar hdfs:///tmp/demo.jar;
use dwd;
select user_id, order_no from order_base;
"""

    selection = select_analysis_statement(sql)

    assert selection.analysis_sql == "select user_id, order_no from order_base"
    assert selection.selected_kind == "query_statement"
    assert selection.statement_count == 4
    assert selection.skipped_count == 3


def test_extracts_source_query_from_insert_shell():
    sql = """
set x=y;
insert overwrite table app.order_metric partition(dt='20260101')
select
  user_id,
  sum(order_amount) as gmv
from dwd_order_di
group by user_id;
"""

    selection = select_analysis_statement(sql)

    assert selection.analysis_sql.lower().startswith("select")
    assert "from dwd_order_di" in selection.analysis_sql
    assert selection.selected_kind == "insert_source_query"
    assert selection.selected_target == "insert_source_0001"


def test_leading_comments_do_not_hide_analyzable_queries():
    selection = select_analysis_statement(
        """
        -- first validation
        select id from first_table;

        /* final validation */
        select id from final_table;
        """
    )

    assert "final_table" in selection.analysis_sql
    assert selection.selected_kind == "query_statement"
    assert selection.selected_target == "statement_0001"
    assert not any(
        diagnostic.code == "UNKNOWN_STATEMENT_TYPE"
        for diagnostic in selection.diagnostics
    )


def test_semicolons_inside_comments_do_not_split_the_query():
    selection = select_analysis_statement(
        """
        /* validation notes; this is still one statement; */
        select id from final_table;
        """
    )

    assert selection.selected_kind == "query_statement"
    assert selection.statement_count == 1
    assert "final_table" in selection.analysis_sql
