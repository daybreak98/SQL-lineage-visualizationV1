from app.services.graph_builder import build_column_lineage_graph
from app.services.simple_lineage_service import analyze_simple_column_lineage


def test_select_a_from_t_extracts_direct_column_lineage():
    result = analyze_simple_column_lineage("select a from t")

    assert result.status == "success"
    assert result.confidence_level == "high"
    assert len(result.lineages) == 1
    assert result.lineages[0].source_table == "t"
    assert result.lineages[0].source_column == "a"
    assert result.lineages[0].output_column == "a"


def test_select_a_as_aa_extracts_alias_lineage():
    result = analyze_simple_column_lineage("select a as aa from t")

    assert result.status == "success"
    assert result.lineages[0].source_label == "t.a"
    assert result.lineages[0].output_column == "aa"


def test_select_qualified_column_extracts_lineage():
    result = analyze_simple_column_lineage("select t.a from t")

    assert result.status == "success"
    assert result.lineages[0].source_label == "t.a"
    assert result.lineages[0].output_column == "a"


def test_select_columns_from_db_table_keeps_qualified_table_name():
    result = analyze_simple_column_lineage("select a, b from db.table")

    assert result.status == "success"
    assert [lineage.source_label for lineage in result.lineages] == [
        "db.table.a",
        "db.table.b",
    ]


def test_select_star_returns_partial_with_diagnostic():
    result = analyze_simple_column_lineage("select * from t")

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == "UNSUPPORTED_SELECT_STAR"
    assert "select_star" in result.unsupported_features


def test_join_returns_partial_with_unsupported_complex_query():
    result = analyze_simple_column_lineage(
        "select t.a from t join u on t.id = u.id"
    )

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == "UNSUPPORTED_COMPLEX_QUERY"
    assert "join" in result.unsupported_features


def test_complex_expression_returns_partial():
    result = analyze_simple_column_lineage("select count(a) as cnt from t")

    assert result.status == "partial"
    assert result.lineages == []
    assert result.diagnostics[0].code == "UNSUPPORTED_COMPLEX_QUERY"


def test_graph_builder_creates_nodes_edges_and_no_dangling_edges():
    lineage = analyze_simple_column_lineage("select a, b as bb from t")
    graph = build_column_lineage_graph(lineage.lineages)
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
