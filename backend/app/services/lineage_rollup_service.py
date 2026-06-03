from __future__ import annotations

from app.services.cte_structure_service import CteStructureResult, StructureEdge


def rollup_structure_edges(structure: CteStructureResult) -> list[StructureEdge]:
    """Placeholder hook for later column-to-structure rollups.

    C05 only needs already-extracted structure edges. Keeping this tiny function
    makes the C05 file list explicit without pretending we have full rollup logic.
    """
    return structure.edges
