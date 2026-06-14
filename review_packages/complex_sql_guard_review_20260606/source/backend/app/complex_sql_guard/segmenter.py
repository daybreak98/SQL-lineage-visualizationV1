from __future__ import annotations

import re

from .models import ParseStatus, SqlSegment
from .normalizer import OffsetLocator, map_span_to_original


class SqlSegmenter:
    _CLAUSE_KEYWORDS = [
        ("lateral view", "lateral_view"),
        ("group by", "group_by"),
        ("order by", "order_by"),
        ("union all", "union_branch"),
        ("union", "union_branch"),
        ("having", "having"),
        ("where", "where"),
        ("from", "from_join"),
        ("select", "main_select"),
        ("with", "cte_block"),
    ]
    _JOIN_KEYWORDS = [
        ("left outer join", "join_block"),
        ("right outer join", "join_block"),
        ("full outer join", "join_block"),
        ("left semi join", "join_block"),
        ("left anti join", "join_block"),
        ("inner join", "join_block"),
        ("left join", "join_block"),
        ("right join", "join_block"),
        ("full join", "join_block"),
        ("cross join", "join_block"),
        ("join", "join_block"),
    ]

    def __init__(self, max_segments: int = 500) -> None:
        self.max_segments = max_segments

    def segment(
        self,
        sql: str,
        *,
        original_sql: str | None = None,
        offset_mapping=None,
    ) -> list[SqlSegment]:
        if not sql.strip():
            return []

        clause_tokens = self._top_level_keyword_positions(sql, self._CLAUSE_KEYWORDS)
        if not clause_tokens:
            return [self._make_segment(sql, 0, len(sql), "statement", None, original_sql, offset_mapping, 1)]

        original_text = original_sql or sql
        locator = OffsetLocator(original_text)
        segments: list[SqlSegment] = []
        next_id = 1

        def append_segment(start: int, end: int, segment_type: str, parent_id: str | None = None) -> SqlSegment | None:
            nonlocal next_id
            if len(segments) >= self.max_segments:
                return None
            segment = self._make_segment(
                sql,
                start,
                end,
                segment_type,
                parent_id,
                original_text,
                offset_mapping,
                next_id,
                locator=locator,
            )
            if segment is None:
                return None
            next_id += 1
            segments.append(segment)
            return segment

        main_select_position = next((pos for pos, _keyword, seg_type in clause_tokens if seg_type == "main_select"), len(sql))
        if clause_tokens and clause_tokens[0][2] == "cte_block":
            cte_segment = append_segment(clause_tokens[0][0], main_select_position, "cte_block")
            if cte_segment is not None:
                for start, end in self._extract_cte_items(sql[clause_tokens[0][0]:main_select_position], clause_tokens[0][0]):
                    append_segment(start, end, "cte_item", cte_segment.segment_id)

        boundary_tokens = [(pos, keyword, seg_type) for pos, keyword, seg_type in clause_tokens if seg_type != "cte_block"]
        for index, (position, keyword, segment_type) in enumerate(boundary_tokens):
            end = boundary_tokens[index + 1][0] if index + 1 < len(boundary_tokens) else len(sql)
            segment = append_segment(position, end, segment_type)
            if segment is None:
                continue

            if segment_type == "main_select":
                from_position = next(
                    (pos for pos, _kw, seg_type in boundary_tokens[index + 1:] if seg_type == "from_join"),
                    end,
                )
                append_segment(position + len(keyword), from_position, "select_list", segment.segment_id)

            if segment_type == "from_join":
                for child in self._segment_from_clause(sql[position:end], position):
                    child_segment = append_segment(child[0], child[1], child[2], segment.segment_id)
                    if child_segment is not None and child[2] == "join_block":
                        join_condition = self._extract_join_condition(sql[child[0]:child[1]], child[0])
                        if join_condition is not None:
                            append_segment(join_condition[0], join_condition[1], "join_condition", child_segment.segment_id)

        return segments[: self.max_segments]

    def _segment_from_clause(self, clause_sql: str, base_offset: int) -> list[tuple[int, int, str]]:
        join_tokens = self._top_level_keyword_positions(clause_sql, self._JOIN_KEYWORDS)
        if not join_tokens:
            return [(base_offset + len("from"), base_offset + len(clause_sql), "from_source")]

        segments: list[tuple[int, int, str]] = []
        first_join_start = join_tokens[0][0]
        segments.append((base_offset + len("from"), base_offset + first_join_start, "from_source"))

        for index, (position, _keyword, _segment_type) in enumerate(join_tokens):
            end = join_tokens[index + 1][0] if index + 1 < len(join_tokens) else len(clause_sql)
            segments.append((base_offset + position, base_offset + end, "join_block"))
        return segments

    def _extract_cte_items(self, cte_sql: str, base_offset: int) -> list[tuple[int, int]]:
        items: list[tuple[int, int]] = []
        work_sql = cte_sql.strip()
        if not work_sql.lower().startswith("with"):
            return items

        relative_offset = cte_sql.lower().find("with") + len("with")
        index = relative_offset
        pattern = re.compile(r"\s*([a-zA-Z0-9_.`]+(?:\s*\([^)]*\))?)\s+as\s*\(", re.IGNORECASE)

        while index < len(cte_sql):
            match = pattern.match(cte_sql, index)
            if not match:
                break
            open_paren = match.end() - 1
            close_paren = self._find_matching_paren(cte_sql, open_paren)
            if close_paren < 0:
                break
            items.append((base_offset + match.start(), base_offset + close_paren + 1))
            index = close_paren + 1
            while index < len(cte_sql) and cte_sql[index] in " \t\r\n,":
                index += 1
        return items

    def _extract_join_condition(self, join_sql: str, base_offset: int) -> tuple[int, int] | None:
        on_tokens = self._top_level_keyword_positions(join_sql, [("on", "join_condition")])
        if not on_tokens:
            return None
        start = on_tokens[0][0]
        return base_offset + start, base_offset + len(join_sql)

    def _make_segment(
        self,
        sql: str,
        start: int,
        end: int,
        segment_type: str,
        parent_id: str | None,
        original_text: str | None,
        offset_mapping,
        sequence: int,
        *,
        locator: OffsetLocator | None = None,
    ) -> SqlSegment | None:
        raw_slice = sql[start:end]
        trimmed = raw_slice.strip()
        if not trimmed:
            return None

        left_trim = len(raw_slice) - len(raw_slice.lstrip())
        right_trim = len(raw_slice) - len(raw_slice.rstrip())
        trimmed_start = start + left_trim
        trimmed_end = max(trimmed_start, end - right_trim)

        if locator is None:
            locator = OffsetLocator(original_text or sql)
        original_start = trimmed_start
        original_end = trimmed_end
        if offset_mapping is not None and getattr(offset_mapping, "analysis_to_original", None):
            original_start, original_end = map_span_to_original(
                offset_mapping.analysis_to_original,
                trimmed_start,
                trimmed_end,
                offset_mapping.original_length,
            )

        return SqlSegment(
            segment_id=f"seg_{sequence:04d}",
            segment_type=segment_type,
            raw_text=trimmed,
            start_offset=original_start,
            end_offset=original_end,
            parent_segment_id=parent_id,
            parse_status=ParseStatus.NOT_ATTEMPTED,
            location=locator.location(original_start, original_end),
        )

    def _find_matching_paren(self, text: str, open_paren_index: int) -> int:
        depth = 0
        in_single = False
        in_double = False
        in_backtick = False
        index = open_paren_index
        while index < len(text):
            char = text[index]
            if char == "'" and not in_double and not in_backtick:
                in_single = not in_single
                index += 1
                continue
            if char == '"' and not in_single and not in_backtick:
                in_double = not in_double
                index += 1
                continue
            if char == "`" and not in_single and not in_double:
                in_backtick = not in_backtick
                index += 1
                continue
            if in_single or in_double or in_backtick:
                index += 1
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return -1

    def _top_level_keyword_positions(
        self,
        sql: str,
        keyword_specs: list[tuple[str, str]],
    ) -> list[tuple[int, str, str]]:
        lowered = sql.lower()
        ordered_keywords = sorted(keyword_specs, key=lambda item: len(item[0]), reverse=True)
        positions: list[tuple[int, str, str]] = []
        depth = 0
        in_single = False
        in_double = False
        in_backtick = False
        index = 0

        while index < len(sql):
            char = sql[index]
            if char == "\\" and (in_single or in_double):
                index += 2
                continue
            if char == "'" and not in_double and not in_backtick:
                in_single = not in_single
                index += 1
                continue
            if char == '"' and not in_single and not in_backtick:
                in_double = not in_double
                index += 1
                continue
            if char == "`" and not in_single and not in_double:
                in_backtick = not in_backtick
                index += 1
                continue
            if in_single or in_double or in_backtick:
                index += 1
                continue

            if char == "(":
                depth += 1
                index += 1
                continue
            if char == ")":
                depth = max(0, depth - 1)
                index += 1
                continue

            if depth == 0:
                matched = False
                for keyword, segment_type in ordered_keywords:
                    end = index + len(keyword)
                    if lowered.startswith(keyword, index) and self._word_boundary(lowered, index, end):
                        if positions and positions[-1][0] == index:
                            matched = True
                            break
                        positions.append((index, keyword, segment_type))
                        index = end
                        matched = True
                        break
                if matched:
                    continue

            index += 1

        return positions

    def _word_boundary(self, text: str, start: int, end: int) -> bool:
        before = text[start - 1] if start > 0 else " "
        after = text[end] if end < len(text) else " "
        return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")

