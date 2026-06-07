"""
Reference implementation: source_location_service.py patch

Features:
- Keep old output_column_names mode compatible.
- Add target_entities mode for output_column / physical_table / cte.
- Mask strings and comments before regex scanning.
- Return line/col + offsets + occurrences.

Integration note:
- Align return dataclass/Pydantic shape with the current project.
- This file is a reference implementation, not a blind drop-in replacement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable, Mapping, Optional

try:
    from .source_location_targets import SourceLocationTarget
except Exception:  # pragma: no cover
    SourceLocationTarget = Any  # type: ignore


@dataclass
class SourceLocation:
    entityId: str
    entityType: str
    rawText: str
    startLine: int
    startCol: int
    endLine: int
    endCol: int
    startOffset: int
    endOffset: int
    role: str
    rangeType: str = "exact"
    origin: str = "regex"
    confidenceLevel: str = "medium"


@dataclass
class SourceLocationGroup:
    primary: dict[str, Any]
    occurrences: list[dict[str, Any]]


TABLE_REF_PATTERN = re.compile(
    r"(?is)\b(from|join)\s+(`?[a-zA-Z_][\w$]*(?:\.`?[a-zA-Z_][\w$]*)*`?)"
)

CTE_DEF_PATTERN = re.compile(
    r"(?is)(?:\bwith\b|,)\s*(`?[a-zA-Z_][\w$]*`?)\s*(?:\([^)]*\)\s*)?\bas\s*\("
)

SKIP_TABLE_TOKENS = {"select", "values", "unnest", "lateral", "explode"}


def build_source_locations(
    sql: str,
    output_column_names: Optional[list[str]] = None,
    target_entities: Optional[list[SourceLocationTarget]] = None,
) -> dict[str, Any]:
    """Build source locations.

    New preferred mode:
        build_source_locations(sql, target_entities=targets)

    Backward-compatible mode:
        build_source_locations(sql, output_column_names=[...])
    """
    if target_entities is None:
        target_entities = _targets_from_output_columns(output_column_names or [])

    masked_sql = mask_sql_for_location_scan(sql)
    line_index = _build_line_index(sql)

    result: dict[str, list[SourceLocation]] = {}

    output_targets = [t for t in target_entities if _get(t, "entity_type") == "output_column"]
    table_targets = [t for t in target_entities if _get(t, "entity_type") == "physical_table"]
    cte_targets = [t for t in target_entities if _get(t, "entity_type") == "cte"]

    for loc in _locate_output_columns(sql, masked_sql, line_index, output_targets):
        result.setdefault(loc.entityId, []).append(loc)

    # CTE definitions should be collected before table references so callers can exclude CTE refs.
    cte_names = {_norm(_get(t, "name")) for t in cte_targets}
    for loc in _locate_cte_definitions(sql, masked_sql, line_index, cte_targets):
        result.setdefault(loc.entityId, []).append(loc)

    for loc in _locate_physical_tables(sql, masked_sql, line_index, table_targets, cte_names=cte_names):
        result.setdefault(loc.entityId, []).append(loc)

    return _group_locations(result)


def mask_sql_for_location_scan(sql: str) -> str:
    """Mask comments and string literals while preserving string length and offsets."""
    chars = list(sql)
    i = 0
    n = len(chars)
    while i < n:
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < n else ""

        # Single-line comment: -- ... \n
        if ch == "-" and nxt == "-":
            j = i
            while j < n and chars[j] != "\n":
                chars[j] = " "
                j += 1
            i = j
            continue

        # Block comment: /* ... */
        if ch == "/" and nxt == "*":
            j = i
            while j + 1 < n and not (chars[j] == "*" and chars[j + 1] == "/"):
                chars[j] = " " if chars[j] != "\n" else "\n"
                j += 1
            if j + 1 < n:
                chars[j] = " "
                chars[j + 1] = " "
                j += 2
            i = j
            continue

        # Single-quoted string, including escaped ''
        if ch == "'":
            chars[i] = " "
            j = i + 1
            while j < n:
                if chars[j] == "'":
                    chars[j] = " "
                    if j + 1 < n and chars[j + 1] == "'":
                        chars[j + 1] = " "
                        j += 2
                        continue
                    j += 1
                    break
                chars[j] = " " if chars[j] != "\n" else "\n"
                j += 1
            i = j
            continue

        i += 1
    return "".join(chars)


def _locate_output_columns(
    sql: str,
    masked_sql: str,
    line_index: list[int],
    targets: Iterable[SourceLocationTarget],
) -> Iterable[SourceLocation]:
    # Minimal compatibility with existing behavior: locate first token occurrence in SELECT list.
    # For better precision, integrate with existing SELECT-column regex logic from current service.
    for target in targets:
        name = _get(target, "name")
        if not name:
            continue
        # Prefer alias occurrence: AS name, fallback raw name token.
        patterns = [
            re.compile(rf"(?is)\bas\s+(`?{re.escape(name)}`?)\b"),
            re.compile(rf"(?is)\b(`?{re.escape(name)}`?)\b"),
        ]
        for pattern in patterns:
            m = pattern.search(masked_sql)
            if not m:
                continue
            start, end = _group_span_for_name(m)
            yield _make_location(
                sql=sql,
                line_index=line_index,
                entity_id=_get(target, "entity_id"),
                entity_type="output_column",
                start=start,
                end=end,
                role="select_output",
                range_type="exact",
            )
            break


def _locate_cte_definitions(
    sql: str,
    masked_sql: str,
    line_index: list[int],
    targets: Iterable[SourceLocationTarget],
) -> Iterable[SourceLocation]:
    target_by_name = {_norm(_get(t, "name")): t for t in targets}
    if not target_by_name:
        return []

    locations = []
    for m in CTE_DEF_PATTERN.finditer(masked_sql):
        raw_name = _strip_identifier(m.group(1))
        target = target_by_name.get(_norm(raw_name))
        if not target:
            continue
        start, end = m.span(1)
        locations.append(
            _make_location(
                sql=sql,
                line_index=line_index,
                entity_id=_get(target, "entity_id"),
                entity_type="cte",
                start=start,
                end=end,
                role="cte_definition",
                range_type="exact",
            )
        )
    return locations


def _locate_physical_tables(
    sql: str,
    masked_sql: str,
    line_index: list[int],
    targets: Iterable[SourceLocationTarget],
    cte_names: set[str],
) -> Iterable[SourceLocation]:
    target_by_last_name = {_norm(_last_part(_get(t, "name"))): t for t in targets}
    target_by_full_name = {_norm(_get(t, "name")): t for t in targets}
    locations = []

    for m in TABLE_REF_PATTERN.finditer(masked_sql):
        role = m.group(1).lower()
        raw_table = _strip_identifier(m.group(2))
        last = _last_part(raw_table)
        norm_last = _norm(last)
        norm_full = _norm(raw_table)

        if norm_last in SKIP_TABLE_TOKENS or norm_full in SKIP_TABLE_TOKENS:
            continue
        if norm_last in cte_names or norm_full in cte_names:
            continue

        target = target_by_full_name.get(norm_full) or target_by_last_name.get(norm_last)
        if not target:
            continue

        start, end = m.span(2)
        locations.append(
            _make_location(
                sql=sql,
                line_index=line_index,
                entity_id=_get(target, "entity_id"),
                entity_type="physical_table",
                start=start,
                end=end,
                role=role,
                range_type="exact",
            )
        )
    return locations


def _make_location(
    sql: str,
    line_index: list[int],
    entity_id: str,
    entity_type: str,
    start: int,
    end: int,
    role: str,
    range_type: str,
) -> SourceLocation:
    start_line, start_col = _offset_to_line_col(line_index, start)
    end_line, end_col = _offset_to_line_col(line_index, end)
    return SourceLocation(
        entityId=entity_id,
        entityType=entity_type,
        rawText=sql[start:end],
        startLine=start_line,
        startCol=start_col,
        endLine=end_line,
        endCol=end_col,
        startOffset=start,
        endOffset=end,
        role=role,
        rangeType=range_type,
        origin="regex",
        confidenceLevel="medium",
    )


def _group_locations(items: Mapping[str, list[SourceLocation]]) -> dict[str, Any]:
    grouped: dict[str, Any] = {}
    for entity_id, locations in items.items():
        if not locations:
            continue
        dicts = [asdict(x) for x in locations]
        grouped[entity_id] = {
            "primary": dicts[0],
            "occurrences": dicts,
        }
    return grouped


def _targets_from_output_columns(output_column_names: list[str]) -> list[Any]:
    @dataclass(frozen=True)
    class _CompatTarget:
        entity_id: str
        entity_type: str
        name: str
        match_role: str

    return [
        _CompatTarget(
            entity_id=f"output_column:{name}",
            entity_type="output_column",
            name=name,
            match_role="select_output",
        )
        for name in output_column_names
    ]


def _build_line_index(sql: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(sql):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _offset_to_line_col(line_index: list[int], offset: int) -> tuple[int, int]:
    # Monaco uses 1-based line/column.
    import bisect

    line_pos = bisect.bisect_right(line_index, offset) - 1
    line_no = line_pos + 1
    col_no = offset - line_index[line_pos] + 1
    return line_no, col_no


def _group_span_for_name(match: re.Match[str]) -> tuple[int, int]:
    # If pattern has captured identifier, use group 1; else whole match.
    if match.lastindex:
        return match.span(match.lastindex)
    return match.span(0)


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _strip_identifier(name: str) -> str:
    return name.strip().strip("`\"")


def _last_part(name: str) -> str:
    return _strip_identifier(name).split(".")[-1]


def _norm(name: str | None) -> str:
    return _strip_identifier(name or "").lower()
