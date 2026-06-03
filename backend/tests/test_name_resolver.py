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
