import re
import time
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.domain import diagnostics_model as diag_codes
from app.models import Diagnostic


@dataclass
class Occurrence:
    line: int
    col: int
    end_line: int
    end_col: int
    offset: int
    end_offset: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "line": self.line,
            "col": self.col,
            "endLine": self.end_line,
            "endCol": self.end_col,
            "startOffset": self.offset,
            "endOffset": self.end_offset,
        }


@dataclass
class SourceLocation:
    entityId: str
    entityType: str
    rawText: str
    rangeType: str
    origin: str = "regex"
    confidenceLevel: str = "high"
    occurrences: List[Occurrence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        primary = self.occurrences[0].to_dict() if self.occurrences else {}
        return {
            "entityId": self.entityId,
            "entityType": self.entityType,
            "startLine": primary.get("line", 0),
            "startCol": primary.get("col", 0),
            "endLine": primary.get("endLine", 0),
            "endCol": primary.get("endCol", 0),
            "startOffset": primary.get("startOffset", 0),
            "endOffset": primary.get("endOffset", 0),
            "rawText": self.rawText,
            "raw": self.rawText,
            "rangeType": self.rangeType,
            "origin": self.origin,
            "confidenceLevel": self.confidenceLevel,
            "line": primary.get("line", 0),
            "col": primary.get("col", 0),
            "occurrences": [o.to_dict() for o in self.occurrences],
        }


@dataclass
class SourceLocationResult:
    locations: Dict[str, Dict[str, object]] = field(default_factory=dict)
    diagnostics: List[Diagnostic] = field(default_factory=list)
    elapsed_ms: int = 0
    stage_statuses: List[Dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class SelectItemSpan:
    raw: str
    start: int
    end: int
    output_name: str
    approximate: bool = False


def build_source_locations(
    sql: str,
    target_entities: Optional[List[Dict[str, str]]] = None,
    output_column_names: Optional[List[str]] = None,
) -> SourceLocationResult:
    started = time.time()
    diagnostics: List[Diagnostic] = []
    locations: Dict[str, Dict[str, object]] = {}

    masked_sql, offset_map = _mask_comments_and_strings(sql)
    sql_len = sum(1 for _ in sql)

    entities = _normalize_targets(target_entities, output_column_names)
    entity_ids_by_type: Dict[str, Set[str]] = {}
    for e in entities:
        entity_ids_by_type.setdefault(e["entityType"], set()).add(e["entityId"])

    # ── CTE locations ──
    cte_names: Set[str] = set()
    # Always extract CTE names for table filtering, even if no cte targets requested
    for loc in _find_cte_spans(sql, masked_sql, offset_map, sql_len):
        cte_names.add(loc.rawText)
        entity_id = f"cte:{loc.rawText}"
        if "cte" in entity_ids_by_type and entity_id in entity_ids_by_type["cte"]:
            locations[entity_id] = loc.to_dict()

    # ── Inline / scalar / predicate subquery locations ──
    if "subquery" in entity_ids_by_type:
        for entity_id in entity_ids_by_type["subquery"]:
            location = _find_subquery_location(sql, masked_sql, entity_id)
            if location is not None:
                locations[entity_id] = location.to_dict()

    # ── Table locations (FROM/JOIN, exclude CTE names) ──
    if "physical_table" in entity_ids_by_type:
        tbl_set = entity_ids_by_type["physical_table"]
        for loc in _find_table_spans(sql, masked_sql, offset_map, cte_names, sql_len):
            full_name = loc.rawText
            short_name = full_name.split(".")[-1] if "." in full_name else full_name
            # Try full name first, then short name
            entity_id_full = f"physical_table:{full_name}"
            entity_id_short = f"physical_table:{short_name}"
            if entity_id_full in tbl_set:
                _append_occurrence(locations, entity_id_full, loc)
            elif entity_id_short in tbl_set:
                _append_occurrence(locations, entity_id_short, loc)

    # ── Output column locations (SELECT) ──
    if "output_column" in entity_ids_by_type:
        col_spans = _final_select_item_spans(sql)
        col_set = entity_ids_by_type["output_column"]
        for span in col_spans:
            if span.output_name == "*":
                for entity_id in entity_ids_by_type.get("output_column", set()):
                    col_name = entity_id.split(":", 1)[1] if ":" in entity_id else entity_id
                    if col_name == "*":
                        continue
                    _add_column_location(locations, sql, span, col_name, "approximate")
                if entity_ids_by_type.get("output_column"):
                    diagnostics.append(Diagnostic(
                        code=diag_codes.SOURCE_LOCATION_APPROXIMATE, level="info",
                        message="SELECT * expanded columns share the source location of the star token."))
                continue
            entity_id = f"output_column:{span.output_name}"
            if entity_id in col_set:
                _add_column_location(
                    locations, sql, span, span.output_name,
                    "exact" if not span.approximate else "approximate")

    # ── Physical column locations (source columns in SELECT) ──
    if "physical_column" in entity_ids_by_type:
        col_set = entity_ids_by_type["physical_column"]
        alias_bindings_by_table = _table_alias_bindings(masked_sql)
        qualified_references, unqualified_references = _physical_column_reference_index(masked_sql)
        line_starts = [0] + [match.end() for match in re.finditer(r"\n", sql)]
        target_count_by_column: Dict[str, int] = {}
        for entity_id in col_set:
            column_name = entity_id.rsplit(".", 1)[-1].lower().strip("`")
            target_count_by_column[column_name] = target_count_by_column.get(column_name, 0) + 1
        for ent_id in col_set:
            relation_and_column = ent_id.split(":", 1)[-1]
            if "." not in relation_and_column:
                continue
            table_name, column_name = relation_and_column.rsplit(".", 1)
            location = _find_physical_column_location(
                sql,
                ent_id,
                table_name,
                column_name,
                alias_bindings_by_table,
                qualified_references,
                unqualified_references,
                line_starts,
                allow_unqualified=(
                    target_count_by_column.get(column_name.lower().strip("`"), 0) == 1
                ),
            )
            if location is not None:
                locations[ent_id] = location.to_dict()

    elapsed_ms = int((time.time() - started) * 1000)
    return SourceLocationResult(
        locations=locations, diagnostics=diagnostics, elapsed_ms=elapsed_ms,
        stage_statuses=[{"stage": "source_location", "status": "success",
                         "elapsed_ms": elapsed_ms, "diagnostic_codes": [d.code for d in diagnostics],
                         "message": "Source locations resolved."}])


def _normalize_targets(
    target_entities: Optional[List[Dict[str, str]]],
    output_column_names: Optional[List[str]],
) -> List[Dict[str, str]]:
    if target_entities and isinstance(target_entities[0], dict):
        return target_entities
    names: List[str] = []
    if target_entities and isinstance(target_entities[0], str):
        names = [str(e) for e in target_entities]
    elif output_column_names:
        names = output_column_names
    return [{"entityId": f"output_column:{name}", "entityType": "output_column"} for name in names]


# ── Masking ──

def _mask_comments_and_strings(sql: str) -> Tuple[str, List[Optional[int]]]:
    length = len(sql)
    chars = list(sql)  # character-level, safe for multi-byte
    offset_map: List[Optional[int]] = list(range(length))

    def replace_with_spaces(start: int, end: int) -> None:
        for _i in range(start, min(end, length)):
            chars[_i] = " "
            offset_map[_i] = None

    # Multi-line comments /* ... */
    for m in re.finditer(r"/\*[\s\S]*?\*/", sql):
        replace_with_spaces(m.start(), m.end())
    # Single-line comments -- ...
    for m in re.finditer(r"--[^\n]*", sql):
        replace_with_spaces(m.start(), m.end())

    # Single-quoted strings
    in_string = False
    string_start = 0
    i = 0
    while i < length:
        ch = sql[i]
        if offset_map[i] is None:
            i += 1
            continue
        if not in_string:
            if ch == "'":
                in_string = True
                string_start = i
        else:
            if ch == "'":
                if i + 1 < length and sql[i + 1] == "'":
                    i += 1  # escaped quote
                else:
                    replace_with_spaces(string_start, i + 1)
                    in_string = False
        i += 1
    if in_string:
        replace_with_spaces(string_start, length)

    return "".join(chars), offset_map


# ── CTE extraction ──

def _find_cte_spans(
    original_sql: str, masked_sql: str,
    offset_map: List[Optional[int]], sql_len: int,
) -> List[SourceLocation]:
    results: List[SourceLocation] = []
    with_match = _find_keyword_span(masked_sql, 0, r"\bwith\b")
    if with_match is None:
        return results

    depth = 0
    segment_start: Optional[int] = None
    idx = with_match.end
    limit = sql_len

    idx = with_match.end()
    limit = sql_len

    while idx < limit:
        ch = masked_sql[idx]
        if segment_start is None:
            segment_start = idx
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif ch == "," and depth == 0:
            if segment_start is not None and idx > segment_start:
                _extract_cte_name(original_sql, masked_sql, offset_map, segment_start, idx, results)
            segment_start = None
        elif depth == 0 and _is_keyword_at(masked_sql, idx, "as", sql_len) and masked_sql[idx + 2:idx + 3] in (" ", "\t", "("):
            if segment_start is not None and idx > segment_start:
                _extract_cte_name(original_sql, masked_sql, offset_map, segment_start, idx, results)
            segment_start = None
        idx += 1

    return results


def _extract_cte_name(
    original_sql: str, masked_sql: str, offset_map: List[Optional[int]],
    start: int, end: int, results: List[SourceLocation],
) -> None:
    segment = masked_sql[start:end].strip()
    m = re.match(r"(\w+(?:\.\w+)*)", segment)
    if m:
        name = m.group(1).split(".")[-1]
        name_start = start + m.start(1)
        name_end = start + m.end(1)
        sl, sc = _line_col(original_sql, name_start)
        el, ec = _line_col(original_sql, name_end)
        results.append(SourceLocation(
            entityId=f"cte:{name}", entityType="cte", rawText=name, rangeType="exact",
            occurrences=[Occurrence(line=sl, col=sc, end_line=el, end_col=ec, offset=name_start, end_offset=name_end)]))
    # Note: blank line intentionally left


# ── Table extraction ──

def _find_table_spans(
    original_sql: str, masked_sql: str, offset_map: List[Optional[int]],
    cte_names: Set[str], sql_len: int,
) -> List[SourceLocation]:
    results: List[SourceLocation] = []
    keywords = ["from", "join"]
    i = 0

    while i < sql_len:
        matched_kw: Optional[str] = None
        for kw in keywords:
            if _is_keyword_at(masked_sql, i, kw, sql_len):
                matched_kw = kw
                break
        if matched_kw is None:
            i += 1
            continue

        after = i + sum(1 for _ in matched_kw)
        while after < sql_len and masked_sql[after] in (" ", "\t", "\n"):
            after += 1

        m = re.match(r"(`[^`]+`|\w+(?:\.\w+)*)", masked_sql[after:])
        if m:
            full_name = m.group(1).strip("`")
            short_name = full_name.split(".")[-1]
            if short_name.lower() not in {"on", "as", "where", "join", "left", "right", "inner",
                                     "outer", "full", "cross", "select", "group", "order",
                                     "having", "union", "limit", "with"}:
                if short_name.lower() not in {cte.lower() for cte in cte_names}:
                    tbl_start = after + m.start(1)
                    tbl_end = after + m.end(1)
                    if all(offset_map[idx] is not None for idx in range(tbl_start, tbl_end)):
                        sl, sc = _line_col(original_sql, tbl_start)
                        el, ec = _line_col(original_sql, tbl_end)
                        results.append(SourceLocation(
                            entityId=f"physical_table:{short_name}", entityType="physical_table",
                            rawText=full_name, rangeType="exact",
                            occurrences=[Occurrence(line=sl, col=sc, end_line=el, end_col=ec,
                                                      offset=tbl_start, end_offset=tbl_end)]))
            i = after + m.end()
        else:
            i = after
    return results


def _find_subquery_location(
    original_sql: str,
    masked_sql: str,
    entity_id: str,
) -> SourceLocation | None:
    name = entity_id.split(":", 1)[1] if ":" in entity_id else entity_id
    generated = re.fullmatch(r"(exists_subquery|in_subquery|subquery)_(\d+)", name)
    if generated is not None:
        kind, raw_index = generated.groups()
        index = int(raw_index) - 1
        if kind == "exists_subquery":
            pattern = r"\bexists\s*\(\s*select\b"
            token = "exists"
        elif kind == "in_subquery":
            pattern = r"\bin\s*\(\s*select\b"
            token = "in"
        else:
            pattern = r"\(\s*select\b"
            token = "select"
        matches = list(re.finditer(pattern, masked_sql, flags=re.IGNORECASE))
        if 0 <= index < len(matches):
            match = matches[index]
            token_match = re.search(token, match.group(0), flags=re.IGNORECASE)
            token_start = match.start() + (token_match.start() if token_match else 0)
            token_end = token_start + len(token)
            return _source_location_from_span(
                original_sql,
                entity_id,
                "subquery",
                token_start,
                token_end,
                "approximate",
            )
        return None

    escaped_name = re.escape(name)
    alias_pattern = re.compile(
        rf"\)\s+(?:as\s+)?(?P<alias>`{escaped_name}`|\b{escaped_name}\b)",
        flags=re.IGNORECASE,
    )
    alias_match = alias_pattern.search(masked_sql)
    if alias_match is None:
        return None
    return _source_location_from_span(
        original_sql,
        entity_id,
        "subquery",
        alias_match.start("alias"),
        alias_match.end("alias"),
        "exact",
    )


def _table_alias_bindings(masked_sql: str) -> Dict[str, List[Tuple[str, int, int]]]:
    identifier = r"(?:`[^`]+`|[A-Za-z_][\w$]*)"
    qualified_identifier = rf"{identifier}(?:\s*\.\s*{identifier})*"
    pattern = re.compile(
        rf"\b(?:from|join)\s+(?P<table>{qualified_identifier})"
        rf"(?:\s+(?:as\s+)?(?P<alias>{identifier}))?",
        flags=re.IGNORECASE,
    )
    reserved = {
        "on", "where", "join", "left", "right", "inner", "outer", "full",
        "cross", "group", "order", "having", "union", "limit", "lateral",
    }
    depth_at = [0] * (len(masked_sql) + 1)
    depth = 0
    for index, char in enumerate(masked_sql):
        depth_at[index] = depth
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        depth_at[index + 1] = depth

    selects_by_depth: Dict[int, List[int]] = {}
    unions_by_depth: Dict[int, List[int]] = {}
    closes_by_depth: Dict[int, List[int]] = {}
    for token in re.finditer(r"\bselect\b|\bunion\b|\)", masked_sql, flags=re.IGNORECASE):
        token_depth = depth_at[token.start()]
        value = token.group().lower()
        if value == "select":
            selects_by_depth.setdefault(token_depth, []).append(token.start())
        elif value == "union":
            unions_by_depth.setdefault(token_depth, []).append(token.start())
        else:
            closes_by_depth.setdefault(token_depth, []).append(token.start())

    bindings: Dict[str, List[Tuple[str, int, int]]] = {}
    for match in pattern.finditer(masked_sql):
        table_name = _normalize_qualified_identifier(match.group("table"))
        alias = _clean_identifier(match.group("alias") or "")
        if not table_name or not alias or alias.lower() in reserved:
            continue
        query_depth = depth_at[match.start()]
        select_positions = selects_by_depth.get(query_depth, [])
        select_index = bisect_right(select_positions, match.start()) - 1
        scope_start = select_positions[select_index] if select_index >= 0 else match.start()
        possible_ends: List[int] = []
        for positions in (unions_by_depth.get(query_depth, []), closes_by_depth.get(query_depth, [])):
            end_index = bisect_left(positions, match.end())
            if end_index < len(positions):
                possible_ends.append(positions[end_index])
        scope_end = min(possible_ends, default=len(masked_sql))
        binding = (alias, scope_start, scope_end)
        bindings.setdefault(table_name.lower(), []).append(binding)
        bindings.setdefault(table_name.split(".")[-1].lower(), []).append(binding)
    return bindings


def _find_physical_column_location(
    original_sql: str,
    entity_id: str,
    table_name: str,
    column_name: str,
    alias_bindings_by_table: Dict[str, List[Tuple[str, int, int]]],
    qualified_references: Dict[Tuple[str, str], List[Tuple[int, int]]],
    unqualified_references: Dict[str, List[Tuple[int, int]]],
    line_starts: List[int],
    *,
    allow_unqualified: bool,
) -> SourceLocation | None:
    normalized_table = _normalize_qualified_identifier(table_name)
    short_table = normalized_table.split(".")[-1]
    normalized_column = _clean_identifier(column_name).lower()
    spans: Set[Tuple[int, int]] = set()
    for qualifier in (normalized_table, short_table):
        spans.update(qualified_references.get((qualifier.lower(), normalized_column), []))
    bindings = {
        *alias_bindings_by_table.get(normalized_table.lower(), []),
        *alias_bindings_by_table.get(short_table.lower(), []),
    }
    for alias, scope_start, scope_end in bindings:
        for span in qualified_references.get((alias.lower(), normalized_column), []):
            if scope_start <= span[0] < scope_end:
                spans.add(span)

    range_type = "exact"
    if not spans and allow_unqualified:
        spans.update(unqualified_references.get(normalized_column, []))
        range_type = "approximate"
    if not spans:
        return None

    occurrences: List[Occurrence] = []
    ordered_spans = sorted(spans)
    for start, end in ordered_spans:
        start_line, start_col = _line_col_from_starts(line_starts, start)
        end_line, end_col = _line_col_from_starts(line_starts, end)
        occurrences.append(Occurrence(
            line=start_line,
            col=start_col,
            end_line=end_line,
            end_col=end_col,
            offset=start,
            end_offset=end,
        ))
    first_start, first_end = ordered_spans[0]
    return SourceLocation(
        entityId=entity_id,
        entityType="physical_column",
        rawText=original_sql[first_start:first_end],
        rangeType=range_type,
        occurrences=occurrences,
    )


def _physical_column_reference_index(
    masked_sql: str,
) -> Tuple[
    Dict[Tuple[str, str], List[Tuple[int, int]]],
    Dict[str, List[Tuple[int, int]]],
]:
    """Index column references once so large SQL does not rescan per graph entity."""
    identifier = r"(?:`[^`\r\n]+`|[A-Za-z_][\w$]*)"
    qualified_pattern = re.compile(
        rf"(?<![\w$])(?P<qualifier>{identifier}(?:\s*\.\s*{identifier})*)"
        rf"\s*\.\s*(?P<column>{identifier})(?![\w$])",
        flags=re.IGNORECASE,
    )
    qualified: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
    for match in qualified_pattern.finditer(masked_sql):
        qualifier = _normalize_qualified_identifier(match.group("qualifier")).lower()
        column = _clean_identifier(match.group("column")).lower()
        qualified.setdefault((qualifier, column), []).append(match.span("column"))

    unqualified: Dict[str, List[Tuple[int, int]]] = {}
    for match in re.finditer(identifier, masked_sql):
        start, end = match.span()
        before = start - 1
        while before >= 0 and masked_sql[before].isspace():
            before -= 1
        after = end
        while after < len(masked_sql) and masked_sql[after].isspace():
            after += 1
        if ((before >= 0 and masked_sql[before] == ".")
                or (after < len(masked_sql) and masked_sql[after] == ".")):
            continue
        name = _clean_identifier(match.group()).lower()
        unqualified.setdefault(name, []).append((start, end))
    return qualified, unqualified


def _normalize_qualified_identifier(identifier: str) -> str:
    return ".".join(
        _clean_identifier(part)
        for part in re.split(r"\s*\.\s*", identifier)
        if _clean_identifier(part)
    )


def _source_location_from_span(
    sql: str,
    entity_id: str,
    entity_type: str,
    start: int,
    end: int,
    range_type: str,
) -> SourceLocation:
    start_line, start_col = _line_col(sql, start)
    end_line, end_col = _line_col(sql, end)
    return SourceLocation(
        entityId=entity_id,
        entityType=entity_type,
        rawText=sql[start:end],
        rangeType=range_type,
        occurrences=[Occurrence(
            line=start_line,
            col=start_col,
            end_line=end_line,
            end_col=end_col,
            offset=start,
            end_offset=end,
        )],
    )


# ── Keyword helpers ──

def _find_keyword_span(sql: str, start: int, pattern: str) -> Optional[Any]:
    return re.search(pattern, sql[start:], flags=re.IGNORECASE)


def _is_keyword_at(sql: str, pos: int, kw: str, sql_limit: int) -> bool:
    end = pos + sum(1 for _ in kw)
    if end > sql_limit:
        return False
    if sql[pos:end].lower() != kw:
        return False
    before_ok = pos == 0 or not sql[pos - 1].isalnum() and sql[pos - 1] != "_"
    after_ok = end == sql_limit or not sql[end].isalnum() and sql[end] != "_"
    return before_ok and after_ok


# ── Occurrence merging ──

def _append_occurrence(
    locations: Dict[str, Dict[str, object]],
    entity_id: str, location: SourceLocation,
) -> None:
    if entity_id not in locations:
        locations[entity_id] = location.to_dict()
    else:
        existing_occ = locations[entity_id].get("occurrences", [])
        new_occ = location.to_dict().get("occurrences", [])
        locations[entity_id]["occurrences"] = list(existing_occ) + list(new_occ)
        if locations[entity_id].get("rangeType") != "exact" and location.rangeType == "exact":
            primary = location.to_dict()
            locations[entity_id]["startLine"] = primary.get("startLine", 0)
            locations[entity_id]["startCol"] = primary.get("startCol", 0)
            locations[entity_id]["rangeType"] = "exact"


# ── Column location helpers ──

def _add_column_location(
    locations: Dict[str, Dict[str, object]],
    sql: str, span: SelectItemSpan,
    entity_name: str, range_type: str,
) -> None:
    entity_id = f"output_column:{entity_name}"
    loc = _column_location(sql, span, entity_name, range_type)
    _append_occurrence(locations, entity_id, loc)


def _column_location(sql: str, span: SelectItemSpan, entity_name: str, range_type: str) -> SourceLocation:
    sl, sc = _line_col(sql, span.start)
    el, ec = _line_col(sql, span.end)
    return SourceLocation(
        entityId=f"output_column:{entity_name}", entityType="output_column",
        rawText=span.raw.strip(),
        rangeType="approximate" if span.approximate else range_type,
        occurrences=[Occurrence(line=sl, col=sc, end_line=el, end_col=ec, offset=span.start, end_offset=span.end)])


# ── SELECT column extraction (legacy, unchanged) ──

def _final_select_item_spans(sql: str) -> List[SelectItemSpan]:
    select_start = _find_final_select(sql)
    if select_start is None:
        return []
    select_list_start = select_start + sum(1 for _ in "select")
    from_start = _find_matching_from(sql, select_list_start)
    if from_start is None:
        from_start = sum(1 for _ in sql)
    return [_span_from_raw(sql, start, end)
            for start, end in _split_top_level(sql, select_list_start, from_start)
            if sql[start:end].strip()]


def _find_final_select(sql: str) -> Optional[int]:
    last_select: Optional[int] = None
    depth = 0
    for match in re.finditer(r"\bselect\b|\(|\)", sql, flags=re.IGNORECASE):
        token = match.group(0).lower()
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(depth - 1, 0)
        elif token == "select" and depth == 0:
            last_select = match.start()
    return last_select


def _find_matching_from(sql: str, start: int) -> Optional[int]:
    depth = 0
    for match in re.finditer(r"\bfrom\b|\(|\)", sql[start:], flags=re.IGNORECASE):
        token = match.group(0).lower()
        absolute = start + match.start()
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(depth - 1, 0)
        elif token == "from" and depth == 0:
            return absolute
    return None


def _split_top_level(sql: str, start: int, end: int) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    depth = 0
    item_start = start
    index = start
    while index < end:
        char = sql[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        elif char == "," and depth == 0:
            spans.append(_trim_span(sql, item_start, index))
            item_start = index + 1
        index += 1
    spans.append(_trim_span(sql, item_start, end))
    return spans


def _trim_span(sql: str, start: int, end: int) -> Tuple[int, int]:
    while start < end and sql[start].isspace():
        start += 1
    while end > start and sql[end - 1].isspace():
        end -= 1
    return start, end


def _span_from_raw(sql: str, start: int, end: int) -> SelectItemSpan:
    raw = sql[start:end]
    output_name, approximate = _output_name(raw)
    return SelectItemSpan(raw=raw, start=start, end=end, output_name=output_name, approximate=approximate)


def _output_name(raw: str) -> Tuple[str, bool]:
    text = raw.strip()
    if text == "*":
        return "*", True
    qualified_star = re.search(r"(?:`[^`]+`|[A-Za-z_][\w]*)\s*\.\s*\*$", text)
    if qualified_star:
        return "*", True
    alias_match = re.search(r"\bas\s+(`[^`]+`|[A-Za-z_][\w]*)\s*$", text, flags=re.IGNORECASE)
    if alias_match:
        return _clean_identifier(alias_match.group(1)), False
    simple_column = re.search(r"(`[^`]+`|[A-Za-z_][\w]*)(?:\s*)$", text)
    if simple_column and _looks_like_direct_column(text):
        return _clean_identifier(simple_column.group(1)), False
    fallback = re.sub(r"\W+", "_", text).strip("_") or "expression"
    return fallback[:64], True


def _looks_like_direct_column(text: str) -> bool:
    return re.fullmatch(
        r"(?:`[^`]+`|[A-Za-z_][\w]*)(?:\s*\.\s*(?:`[^`]+`|[A-Za-z_][\w]*))*", text.strip()) is not None


def _clean_identifier(identifier: str) -> str:
    return identifier.strip().strip("`")


def _line_col(sql: str, offset: int) -> Tuple[int, int]:
    safe_offset = max(0, min(offset, sum(1 for _ in sql)))
    line = sql.count("\n", 0, safe_offset) + 1
    line_start = sql.rfind("\n", 0, safe_offset) + 1
    col = safe_offset - line_start + 1
    return line, col


def _line_col_from_starts(line_starts: List[int], offset: int) -> Tuple[int, int]:
    line_index = max(0, bisect_right(line_starts, offset) - 1)
    return line_index + 1, offset - line_starts[line_index] + 1
