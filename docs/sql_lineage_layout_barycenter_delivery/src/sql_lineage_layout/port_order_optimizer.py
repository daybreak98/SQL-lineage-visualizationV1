from __future__ import annotations

from .models import LayoutEdge, LayoutNode, edge_weight


class PortOrderOptimizer:
    """Optimize internal field order of a compound node.

    Field-level lineage often crosses inside large CTE/table nodes. This helper
    orders fields by the barycenter of their downstream output positions.
    """

    def optimize(
        self,
        node: LayoutNode,
        field_to_targets: dict[str, list[str]],
        target_positions: dict[str, int],
        original_field_order: list[str] | None = None,
    ) -> list[str]:
        original = original_field_order or node.fields or list(field_to_targets.keys())
        original_index = {field: idx for idx, field in enumerate(original)}

        scored: list[tuple[float, int, str]] = []
        for field in original:
            targets = field_to_targets.get(field, [])
            positions = [target_positions[t] for t in targets if t in target_positions]
            if positions:
                score = sum(positions) / len(positions)
            else:
                score = float(original_index[field])
            scored.append((score, original_index[field], field))

        ordered = [field for _, _, field in sorted(scored, key=lambda x: (x[0], x[1], x[2]))]
        node.field_order = ordered
        return ordered

    def optimize_from_edges(
        self,
        node: LayoutNode,
        edges: list[LayoutEdge],
        target_positions: dict[str, int],
        field_edge_key: str = "source_field",
    ) -> list[str]:
        """Build field_to_targets mapping from edge metadata.

        Expected edge data example:
            {"source_field": "show_uv"}
        """
        field_to_weighted_targets: dict[str, list[str]] = {}
        for edge in edges:
            if edge.source != node.id:
                continue
            field = edge.data.get(field_edge_key)
            if not field:
                continue
            repeats = max(1, int(round(edge_weight(edge))))
            field_to_weighted_targets.setdefault(str(field), []).extend([edge.target] * repeats)
        return self.optimize(node, field_to_weighted_targets, target_positions)
