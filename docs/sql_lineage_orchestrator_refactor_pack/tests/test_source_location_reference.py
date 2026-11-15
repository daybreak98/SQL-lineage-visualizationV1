"""
Reference tests for SourceLocation extension.
Adapt imports to current project.
"""

from dataclasses import dataclass

# from app.services.source_location_service import build_source_locations
# from app.services.source_location_targets import SourceLocationTarget


@dataclass(frozen=True)
class SourceLocationTarget:
    entity_id: str
    entity_type: str
    name: str
    match_role: str


def test_source_location_physical_table_from():
    from core_code.source_location_service_patch import build_source_locations

    sql = "select order_id from dwd_order_di"
    targets = [
        SourceLocationTarget("physical_table:dwd_order_di", "physical_table", "dwd_order_di", "table_reference")
    ]
    locs = build_source_locations(sql, target_entities=targets)
    assert "physical_table:dwd_order_di" in locs
    assert locs["physical_table:dwd_order_di"]["primary"]["rawText"] == "dwd_order_di"


def test_source_location_physical_table_join():
    from core_code.source_location_service_patch import build_source_locations

    sql = "select * from dwd_order_di o join dim_user u on o.user_id = u.user_id"
    targets = [
        SourceLocationTarget("physical_table:dim_user", "physical_table", "dim_user", "table_reference")
    ]
    locs = build_source_locations(sql, target_entities=targets)
    assert "physical_table:dim_user" in locs
    assert locs["physical_table:dim_user"]["primary"]["role"] == "join"


def test_source_location_cte_definition():
    from core_code.source_location_service_patch import build_source_locations

    sql = """
    with order_base as (
        select order_id from dwd_order_di
    )
    select order_id from order_base
    """
    targets = [
        SourceLocationTarget("cte:order_base", "cte", "order_base", "cte_definition")
    ]
    locs = build_source_locations(sql, target_entities=targets)
    assert "cte:order_base" in locs
    assert locs["cte:order_base"]["primary"]["rawText"].strip() == "order_base"


def test_source_location_should_ignore_strings_and_comments():
    from core_code.source_location_service_patch import build_source_locations

    sql = """
    select 'from fake_table' as txt
    -- join fake_table
    /* from another_fake */
    from real_table
    """
    targets = [
        SourceLocationTarget("physical_table:fake_table", "physical_table", "fake_table", "table_reference"),
        SourceLocationTarget("physical_table:real_table", "physical_table", "real_table", "table_reference"),
    ]
    locs = build_source_locations(sql, target_entities=targets)
    assert "physical_table:fake_table" not in locs
    assert "physical_table:real_table" in locs


def test_source_location_same_table_multiple_occurrences():
    from core_code.source_location_service_patch import build_source_locations

    sql = """
    select a.order_id, b.order_id
    from dwd_order_di a
    join dwd_order_di b on a.parent_id = b.order_id
    """
    targets = [
        SourceLocationTarget("physical_table:dwd_order_di", "physical_table", "dwd_order_di", "table_reference")
    ]
    locs = build_source_locations(sql, target_entities=targets)
    assert "physical_table:dwd_order_di" in locs
    assert len(locs["physical_table:dwd_order_di"]["occurrences"]) == 2
