from __future__ import annotations

from app.domain.graph_layout_models import LayoutEdge, LayoutNode, edge_weight


class PortOrderOptimizer:
    def optimize(
        self,
        node: LayoutNode,
        field_to_targets: dict[str, list[str]],
        target_positions: dict[str, int],
        original_field_order: list[str] | None = None,
    ) -> list[str]:
        original = original_field_order or node.fields or list(field_to_targets)
        original_index = {field: index for index, field in enumerate(original)}
        scored: list[tuple[float, int, str]] = []
        for field in original:
            positions = [target_positions[target] for target in field_to_targets.get(field, []) if target in target_positions]
            score = sum(positions) / len(positions) if positions else float(original_index[field])
            scored.append((score, original_index[field], field))
        ordered = [field for _, _, field in sorted(scored, key=lambda item: (item[0], item[1], item[2]))]
        node.field_order = ordered
        return ordered

    def optimize_from_edges(
        self,
        node: LayoutNode,
        edges: list[LayoutEdge],
        target_positions: dict[str, int],
        field_edge_key: str = "source_field",
    ) -> list[str]:
        field_to_targets: dict[str, list[str]] = {}
        for edge in edges:
            if edge.source != node.id:
                continue
            field = edge.data.get(field_edge_key)
            if not field:
                continue
            repeats = max(1, int(round(edge_weight(edge))))
            field_to_targets.setdefault(str(field), []).extend([edge.target] * repeats)
        return self.optimize(node, field_to_targets, target_positions)
