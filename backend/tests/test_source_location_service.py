from app.domain import diagnostics_model as diag_codes
from app.services.source_location_service import build_source_locations


def test_alias_output_column_has_exact_source_location():
    result = build_source_locations("select a as aa from t", ["aa"])

    location = result.locations["output_column:aa"]
    assert location["line"] == 1
    assert location["col"] == 8
    assert location["raw"] == "a as aa"
    assert location["rangeType"] == "exact"


def test_multiline_select_items_use_one_based_line_and_column():
    sql = """select
  order_no,
  user_id as uid,
  sum(order_amount) as gmv
from dwd_order_di"""

    result = build_source_locations(sql, ["order_no", "uid", "gmv"])

    assert result.locations["output_column:order_no"]["line"] == 2
    assert result.locations["output_column:order_no"]["col"] == 3
    assert result.locations["output_column:uid"]["line"] == 3
    assert result.locations["output_column:gmv"]["line"] == 4
    assert result.locations["output_column:gmv"]["raw"] == "sum(order_amount) as gmv"


def test_select_star_expanded_columns_share_approximate_star_location():
    result = build_source_locations("select * from dwd_order_di", ["order_no", "user_id"])

    assert result.locations["output_column:order_no"]["raw"] == "*"
    assert result.locations["output_column:user_id"]["rangeType"] == "approximate"
    assert any(diagnostic.code == diag_codes.SOURCE_LOCATION_APPROXIMATE for diagnostic in result.diagnostics)


def test_cte_query_uses_final_select_list_not_inner_cte_select():
    sql = """with order_base as (
  select user_id from dwd_order_di
)
select
  user_id
from order_base"""

    result = build_source_locations(sql, ["user_id"])

    assert result.locations["output_column:user_id"]["line"] == 5
    assert result.locations["output_column:user_id"]["raw"] == "user_id"


# ── C08+ extended: table and CTE source locations ────────────


def test_from_table_has_physical_table_location():
    result = build_source_locations(
        "select a from dwd_order_di",
        target_entities=[
            {"entityId": "physical_table:dwd_order_di", "entityType": "physical_table"},
            {"entityId": "output_column:a", "entityType": "output_column"},
        ],
    )

    loc = result.locations.get("physical_table:dwd_order_di")
    assert loc is not None, result.locations.keys()
    assert loc["rawText"] == "dwd_order_di"
    assert loc["entityType"] == "physical_table"
    assert loc["rangeType"] == "exact"


def test_join_table_has_physical_table_location():
    result = build_source_locations(
        "select u.name from orders o join dim_user u on o.uid = u.id",
        target_entities=[
            {"entityId": "physical_table:orders", "entityType": "physical_table"},
            {"entityId": "physical_table:dim_user", "entityType": "physical_table"},
        ],
    )

    orders = result.locations.get("physical_table:orders")
    users = result.locations.get("physical_table:dim_user")
    assert orders is not None
    assert users is not None
    assert orders["rawText"] == "orders"
    assert users["rawText"] == "dim_user"


def test_cte_has_cte_location():
    result = build_source_locations(
        "with order_base as (select a from t) select a from order_base",
        target_entities=[
            {"entityId": "cte:order_base", "entityType": "cte"},
        ],
    )

    loc = result.locations.get("cte:order_base")
    assert loc is not None, result.locations.keys()
    assert loc["rawText"] == "order_base"
    assert loc["entityType"] == "cte"


def test_from_cte_name_not_misidentified_as_physical_table():
    result = build_source_locations(
        "with order_base as (select a from t) select a from order_base",
        target_entities=[
            {"entityId": "physical_table:order_base", "entityType": "physical_table"},
        ],
    )

    assert "physical_table:order_base" not in result.locations


def test_string_literal_table_name_not_matched():
    result = build_source_locations(
        "select 'from fake_table' as col from real_table",
        target_entities=[
            {"entityId": "physical_table:fake_table", "entityType": "physical_table"},
            {"entityId": "physical_table:real_table", "entityType": "physical_table"},
        ],
    )

    assert "physical_table:fake_table" not in result.locations
    assert "physical_table:real_table" in result.locations


def test_comment_table_name_not_matched():
    result = build_source_locations(
        "-- join fake_table\nselect a from real_table",
        target_entities=[
            {"entityId": "physical_table:fake_table", "entityType": "physical_table"},
            {"entityId": "physical_table:real_table", "entityType": "physical_table"},
        ],
    )

    assert "physical_table:fake_table" not in result.locations
    assert "physical_table:real_table" in result.locations


def test_same_table_appears_twice_has_two_occurrences():
    result = build_source_locations(
        "select a from t join t as t2 on t.id = t2.id",
        target_entities=[
            {"entityId": "physical_table:t", "entityType": "physical_table"},
        ],
    )

    loc = result.locations.get("physical_table:t")
    assert loc is not None
    assert "occurrences" in loc
    assert len(loc["occurrences"]) == 2


def test_source_location_has_all_required_fields():
    result = build_source_locations(
        "select a from dwd_order_di",
        target_entities=[
            {"entityId": "physical_table:dwd_order_di", "entityType": "physical_table"},
            {"entityId": "output_column:a", "entityType": "output_column"},
        ],
    )

    loc = result.locations["physical_table:dwd_order_di"]
    assert "startLine" in loc
    assert "startCol" in loc
    assert "endLine" in loc
    assert "endCol" in loc
    assert "startOffset" in loc
    assert "endOffset" in loc
    assert "rawText" in loc
    assert "entityType" in loc
    assert "rangeType" in loc
    assert "origin" in loc
    assert "confidenceLevel" in loc
    assert "occurrences" in loc


def test_old_call_style_still_works():
    """backward compat: build_source_locations(sql, [col_names])"""
    result = build_source_locations("select a as aa from t", ["aa"])

    assert "output_column:aa" in result.locations
    assert result.locations["output_column:aa"]["line"] == 1
