from app.services.expression_analyzer import ExpressionAnalyzer


def test_c09_extracts_sum_count_distinct_and_division_dependencies():
    sql = """
    select
      sum(order_amount) as gmv,
      count(distinct order_no) as order_cnt,
      sum(order_amount) / count(distinct order_no) as adr
    from dwd_order_di
    """

    def resolve(col):
        return f"dwd_order_di.{col.name}"

    metrics = ExpressionAnalyzer(dialect="hive", resolve_column=resolve).analyze_sql(sql)
    by_name = {m.name: m for m in metrics}

    assert "gmv" in by_name
    assert "order_cnt" in by_name
    assert "adr" in by_name

    assert "dwd_order_di.order_amount" in by_name["gmv"].depends_on
    assert "SUM" in by_name["gmv"].aggregate_functions

    assert "dwd_order_di.order_no" in by_name["order_cnt"].depends_on
    assert "COUNT_DISTINCT" in by_name["order_cnt"].aggregate_functions

    assert "dwd_order_di.order_amount" in by_name["adr"].depends_on
    assert "dwd_order_di.order_no" in by_name["adr"].depends_on
    assert "DIV" in by_name["adr"].operators


def test_c09_direct_column_projection_does_not_create_metric():
    sql = "select order_no as id from dwd_order_di"
    metrics = ExpressionAnalyzer(dialect="hive").analyze_sql(sql)
    assert metrics == []
