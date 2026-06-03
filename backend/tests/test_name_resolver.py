from app.domain import diagnostics_model as diag_codes
from app.services.name_resolver import resolve_column_lineage_names


def test_join_aliases_resolve_to_physical_tables():
    result = resolve_column_lineage_names(
        "select u.country_name, o.order_no "
        "from dim_user_df u "
        "join dwd_order_di o on u.user_id = o.user_id"
    )

    assert result.status == "success"
    assert result.alias_to_table == {
        "u": "dim_user_df",
        "o": "dwd_order_di",
    }
    assert [
        (lineage.source_label, lineage.output_column)
        for lineage in result.lineages
    ] == [
        ("dim_user_df.country_name", "country_name"),
        ("dwd_order_di.order_no", "order_no"),
    ]


def test_single_table_alias_resolves_qualified_column():
    result = resolve_column_lineage_names("select o.order_no from dwd_order_di o")

    assert result.status == "success"
    assert result.alias_to_table == {"o": "dwd_order_di"}
    assert result.lineages[0].source_label == "dwd_order_di.order_no"


def test_unknown_table_alias_returns_diagnostic_without_fake_lineage():
    result = resolve_column_lineage_names("select x.a from t")

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == diag_codes.UNKNOWN_TABLE_ALIAS


def test_unqualified_column_in_join_returns_ambiguous_without_fake_lineage():
    result = resolve_column_lineage_names(
        "select a from t1 join t2 on t1.id = t2.id"
    )

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == diag_codes.AMBIGUOUS_COLUMN


def test_mixed_join_fields_keep_known_lineage_and_report_ambiguous_field():
    result = resolve_column_lineage_names(
        "select u.country_name, a "
        "from dim_user_df u "
        "join dwd_order_di o on u.user_id = o.user_id"
    )

    assert result.status == "partial"
    assert [(lineage.source_label, lineage.output_column) for lineage in result.lineages] == [
        ("dim_user_df.country_name", "country_name")
    ]
    assert result.diagnostics[0].code == diag_codes.AMBIGUOUS_COLUMN


def test_cte_remains_out_of_scope_for_c04():
    result = resolve_column_lineage_names(
        "with c as (select a from t) select a from c"
    )

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == diag_codes.UNSUPPORTED_COMPLEX_QUERY
    assert "cte" in result.unsupported_features


# -- migrated from test_simple_lineage_service --


from app.domain.lineage_model import SimpleColumnLineage
from app.services.graph_builder import build_column_lineage_graph


def test_select_a_from_t():
    result = resolve_column_lineage_names("select a from t")

    assert result.status == "success"
    assert len(result.lineages) == 1
    assert result.lineages[0].source_table == "t"
    assert result.lineages[0].source_column == "a"
    assert result.lineages[0].output_column == "a"


def test_select_a_as_aa():
    result = resolve_column_lineage_names("select a as aa from t")

    assert result.status == "success"
    assert result.lineages[0].source_label == "t.a"
    assert result.lineages[0].output_column == "aa"


def test_select_qualified_column():
    result = resolve_column_lineage_names("select t.a from t")

    assert result.status == "success"
    assert result.lineages[0].source_label == "t.a"
    assert result.lineages[0].output_column == "a"


def test_select_columns_from_db_table():
    result = resolve_column_lineage_names("select a, b from db.table")

    assert result.status == "success"
    assert [lineage.source_label for lineage in result.lineages] == [
        "db.table.a",
        "db.table.b",
    ]


def test_select_star():
    result = resolve_column_lineage_names("select * from t")

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == diag_codes.SELECT_STAR_METADATA_REQUIRED
    assert "select_star" in result.unsupported_features


def test_unqualified_column_in_join_ambiguous():
    result = resolve_column_lineage_names(
        "select a from t join u on t.id = u.id"
    )

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == diag_codes.AMBIGUOUS_COLUMN


def test_complex_expression_skipped_with_diagnostic():
    result = resolve_column_lineage_names("select count(a) as cnt from t")

    assert result.status == "partial"
    assert result.lineages == []
    assert any(d.code == diag_codes.UNSUPPORTED_COMPLEX_QUERY for d in result.diagnostics)


def test_graph_builder_from_name_resolver():
    result = resolve_column_lineage_names("select a, b as bb from t")
    graph = build_column_lineage_graph(result.lineages)
    data = graph.to_dict()

    node_ids = {node["id"] for node in data["nodes"]}
    assert node_ids == {
        "physical_column:t.a",
        "output_column:a",
        "physical_column:t.b",
        "output_column:bb",
    }
    assert {
        (edge["source"], edge["target"])
        for edge in data["edges"]
    } == {
        ("physical_column:t.a", "output_column:a"),
        ("physical_column:t.b", "output_column:bb"),
    }
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in data["edges"])
