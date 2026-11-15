from pathlib import Path

from app.api.analyze_controller import analyze
from app.models import AnalyzeRequest


CORPUS_DIR = Path(__file__).resolve().parents[3] / "\u6d4b\u8bd5\u7528\u4f8b"


def test_real_sql_corpus_has_no_failed_analysis_or_invalid_graphs():
    sql_files = sorted(CORPUS_DIR.rglob("*.sql"))
    non_empty_files = [path for path in sql_files if path.stat().st_size > 0]
    failures: list[str] = []

    assert len(sql_files) >= 50
    assert len(non_empty_files) >= 45

    for path in non_empty_files:
        result = analyze(AnalyzeRequest(sql=path.read_text(encoding="utf-8"), dialect="spark"))
        graph = result.graph_view_model
        node_ids = [node["id"] for node in graph.nodes]
        node_id_set = set(node_ids)

        if result.status == "failed":
            failures.append(f"{path.relative_to(CORPUS_DIR)}: analysis failed")
        if len(node_ids) != len(node_id_set):
            failures.append(f"{path.relative_to(CORPUS_DIR)}: duplicate node ids")

        for edge in graph.edges:
            edge_id = edge.get("id", "<missing-id>")
            if edge.get("source") not in node_id_set or edge.get("target") not in node_id_set:
                failures.append(f"{path.relative_to(CORPUS_DIR)}: dangling edge {edge_id}")
            if edge.get("source") == edge.get("target"):
                failures.append(f"{path.relative_to(CORPUS_DIR)}: self-loop {edge_id}")
            if str(edge.get("source", "")).startswith("physical_column:subquery:"):
                failures.append(f"{path.relative_to(CORPUS_DIR)}: synthetic source {edge_id}")

    assert not failures, "\n".join(failures)
