import re
import time
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

    # ── Table locations (FROM/JOIN, exclude CTE names) ──
    if "physical_table" in entity_ids_by_type:
        for loc in _find_table_spans(sql, masked_sql, offset_map, cte_names, sql_len):
            entity_id = f"physical_table:{loc.rawText}"
            if entity_id in entity_ids_by_type["physical_table"]:
                _append_occurrence(locations, entity_id, loc)

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
    length = sum(1 for _ in sql)
    mask = bytearray(sql, "utf-8")
    offset_map: List[Optional[int]] = list(range(length))

    def replace_with_spaces(start: int, end: int) -> None:
        for _i in range(start, min(end, length)):
            mask[_i] = 0x20
            offset_map[_i] = None

    for m in re.finditer(r"/\*[\s\S]*?\*/", sql):
        replace_with_spaces(m.start(), m.end())
    for m in re.finditer(r"--[^\n]*", sql):
        replace_with_spaces(m.start(), m.end())

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
                    i += 1
                else:
                    replace_with_spaces(string_start, i + 1)
                    in_string = False
        i += 1
    if in_string:
        replace_with_spaces(string_start, length)

    return mask.decode("utf-8"), offset_map


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
            name = m.group(1).split(".")[-1].strip("`")
            if name.lower() not in {"on", "as", "where", "join", "left", "right", "inner",
                                     "outer", "full", "cross", "select", "group", "order",
                                     "having", "union", "limit", "with"}:
                if name.lower() not in {cte.lower() for cte in cte_names}:
                    tbl_start = after + m.start(1)
                    tbl_end = after + m.end(1)
                    if all(offset_map[idx] is not None for idx in range(tbl_start, tbl_end)):
                        sl, sc = _line_col(original_sql, tbl_start)
                        el, ec = _line_col(original_sql, tbl_end)
                        results.append(SourceLocation(
                            entityId=f"physical_table:{name}", entityType="physical_table",
                            rawText=name, rangeType="exact",
                            occurrences=[Occurrence(line=sl, col=sc, end_line=el, end_col=ec,
                                                      offset=tbl_start, end_offset=tbl_end)]))
            i = after + m.end()
        else:
            i = after
    return results


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
