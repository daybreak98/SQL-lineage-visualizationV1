from __future__ import annotations

import re
from typing import List, Tuple

from .models import Diagnostic, ParseStatus, Severity, SourceLocation, SqlSegment
from .shields import OffsetLocator


class SqlSegmenter:
    """Best-effort segmenter based on token depth.

    It is not a full parser. Its purpose is to recover useful islands from long
    SQL when the full parser fails.
    """

    KEYWORDS = {
        "with": "cte_block",
        "select": "main_select",
        "from": "from_join",
        "where": "where",
        "group by": "group_by",
        "having": "having",
        "order by": "order_by",
        "union": "union_branch",
        "lateral view": "lateral_view",
    }

    def segment(self, sql: str) -> List[SqlSegment]:
        locator = OffsetLocator(sql)
        tokens = self._top_level_keyword_positions(sql)
        if not tokens:
            return [SqlSegment(
                segment_id="seg_0001",
                segment_type="statement",
                raw_text=sql,
                location=locator.location(0, len(sql)),
            )]

        segments: List[SqlSegment] = []
        for idx, (pos, keyword, seg_type) in enumerate(tokens):
            end = tokens[idx + 1][0] if idx + 1 < len(tokens) else len(sql)
            raw = sql[pos:end].strip()
            if not raw:
                continue
            start = pos + (len(sql[pos:end]) - len(sql[pos:end].lstrip()))
            segment = SqlSegment(
                segment_id=f"seg_{len(segments)+1:04d}",
                segment_type=seg_type,
                raw_text=raw,
                location=locator.location(start, end),
                parse_status=ParseStatus.NOT_ATTEMPTED,
            )
            segments.append(segment)
        return segments

    def _top_level_keyword_positions(self, sql: str) -> List[Tuple[int, str, str]]:
        lowered = sql.lower()
        n = len(sql)
        depth = 0
        i = 0
        positions: List[Tuple[int, str, str]] = []
        while i < n:
            ch = lowered[i]
            if ch == "(":
                depth += 1
                i += 1
                continue
            if ch == ")":
                depth = max(0, depth - 1)
                i += 1
                continue
            if depth == 0:
                for keyword in sorted(self.KEYWORDS, key=len, reverse=True):
                    if lowered.startswith(keyword, i) and self._word_boundary(lowered, i, i + len(keyword)):
                        # Keep lateral view even when nested at top from/join area.
                        positions.append((i, keyword, self.KEYWORDS[keyword]))
                        i += len(keyword)
                        break
                else:
                    i += 1
            else:
                # lateral view is often top-level but after FROM; when inside no scan.
                i += 1
        return self._dedupe_positions(positions)

    def _word_boundary(self, text: str, start: int, end: int) -> bool:
        before = text[start - 1] if start > 0 else " "
        after = text[end] if end < len(text) else " "
        return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")

    def _dedupe_positions(self, positions: List[Tuple[int, str, str]]) -> List[Tuple[int, str, str]]:
        if not positions:
            return []
        result: List[Tuple[int, str, str]] = []
        seen = set()
        for item in sorted(positions, key=lambda x: x[0]):
            if item[0] in seen:
                continue
            seen.add(item[0])
            result.append(item)
        return result
