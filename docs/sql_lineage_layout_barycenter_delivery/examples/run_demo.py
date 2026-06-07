import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sql_lineage_layout.demo_case import build_intl_ab_metric_demo
from src.sql_lineage_layout.layout_planner import GraphLayoutPlanner
from src.sql_lineage_layout.models import LayoutConfig


if __name__ == "__main__":
    nodes, edges = build_intl_ab_metric_demo()
    planner = GraphLayoutPlanner(LayoutConfig(iterations=4, score_method="barycenter"))
    result = planner.plan(nodes, edges)
    graph = planner.to_graph_view_model(result)
    print(json.dumps(graph, ensure_ascii=False, indent=2))
