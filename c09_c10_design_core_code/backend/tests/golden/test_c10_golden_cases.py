"""C10 golden case regression test reference.

Integration options:
1. Prefer calling your real analyze service directly if it is easy to import.
2. Or use FastAPI TestClient POST /api/sql/analyze.

This file includes assertion helpers. Adapt `run_analyze` to your project.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "golden_cases"


def run_analyze(sql: str, metadata: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    """Adapt this function to call the current project's analyzer.

    Example with FastAPI TestClient:

        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.post('/api/sql/analyze', json={'sql': sql, 'dialect': options.get('dialect', 'hive')})
        assert resp.status_code == 200
        return resp.json()

    This placeholder intentionally fails so opencode must wire it to the real service.
    """
    raise NotImplementedError("Wire run_analyze() to the project's analyze API/service.")


@pytest.mark.parametrize("case_dir", sorted(p for p in GOLDEN_ROOT.iterdir() if p.is_dir()))
def test_c10_golden_case(case_dir: Path):
    sql = (case_dir / "input.sql").read_text(encoding="utf-8")
    metadata = _read_json(case_dir / "metadata.json", default={})
    options = _read_json(case_dir / "options.json", default={"dialect": "hive"})
    expected = _read_json(case_dir / "expected.min.json")

    result = run_analyze(sql=sql, metadata=metadata, options=options)

    assert result.get("status") in expected.get("expected_status", ["success"])

    graph = result.get("graph_view_model", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    diagnostics = result.get("diagnostics", [])
    semantics = result.get("semantics_report", {})

    if "no_dangling_edges" in expected.get("invariants", []):
        assert_no_dangling_edges(nodes, edges)

    assert_must_have_nodes(nodes, expected.get("must_have_nodes", []))
    assert_must_have_edges(edges, expected.get("must_have_edges", []))
    assert_must_have_metrics(semantics.get("metrics", []), expected.get("must_have_metrics", []))
    assert_forbidden_diagnostics_absent(diagnostics, expected.get("forbidden_diagnostics", []))


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise AssertionError(f"Missing golden file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_dangling_edges(nodes: list[dict], edges: list[dict]) -> None:
    node_ids = {n.get("id") for n in nodes}
    dangling = [e for e in edges if e.get("source") not in node_ids or e.get("target") not in node_ids]
    assert not dangling, f"Dangling edges found: {dangling}"


def assert_must_have_nodes(nodes: list[dict], expected_nodes: list[dict]) -> None:
    for expected in expected_nodes:
        assert any(_matches_subset(node, expected) for node in nodes), f"Missing node subset: {expected}"


def assert_must_have_edges(edges: list[dict], expected_edges: list[dict]) -> None:
    for expected in expected_edges:
        assert any(_matches_subset(edge, expected) for edge in edges), f"Missing edge subset: {expected}"


def assert_must_have_metrics(metrics: list[dict], expected_metrics: list[dict]) -> None:
    by_name = {m.get("name"): m for m in metrics}
    for expected in expected_metrics:
        metric = by_name.get(expected["name"])
        assert metric is not None, f"Missing metric: {expected['name']}"
        for dep in expected.get("depends_on_contains", []):
            assert any(dep in item for item in metric.get("depends_on", [])), f"Metric {expected['name']} missing dep {dep}"
        for agg in expected.get("aggregate_functions_contains", []):
            assert agg in metric.get("aggregate_functions", []), f"Metric {expected['name']} missing aggregate {agg}"


def assert_forbidden_diagnostics_absent(diagnostics: list[dict], forbidden_codes: list[str]) -> None:
    codes = {d.get("code") for d in diagnostics}
    for code in forbidden_codes:
        assert code not in codes, f"Forbidden diagnostic appears: {code}"


def _matches_subset(actual: dict, expected_subset: dict) -> bool:
    for key, value in expected_subset.items():
        if actual.get(key) != value:
            return False
    return True
