from __future__ import annotations

from dataclasses import dataclass

from .models import SourceLocation


@dataclass(frozen=True)
class NormalizedSqlResult:
    text: str
    char_to_original: list[int]


class OffsetLocator:
    def __init__(self, text: str) -> None:
        self.text = text
        self._line_starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self._line_starts.append(index + 1)

    def location(self, start_offset: int, end_offset: int) -> SourceLocation:
        import bisect

        safe_start = max(0, min(start_offset, len(self.text)))
        safe_end = max(safe_start, min(end_offset, len(self.text)))

        start_line_idx = bisect.bisect_right(self._line_starts, safe_start) - 1
        end_anchor = max(safe_end - 1, safe_start)
        end_line_idx = bisect.bisect_right(self._line_starts, end_anchor) - 1

        start_line_start = self._line_starts[start_line_idx]
        end_line_start = self._line_starts[end_line_idx]

        return SourceLocation(
            start_offset=safe_start,
            end_offset=safe_end,
            start_line=start_line_idx + 1,
            start_col=safe_start - start_line_start + 1,
            end_line=end_line_idx + 1,
            end_col=safe_end - end_line_start + 1,
        )


def normalize_sql_reversible(sql: str) -> NormalizedSqlResult:
    normalized_chars: list[str] = []
    char_to_original: list[int] = []

    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "\r":
            if index + 1 < len(sql) and sql[index + 1] == "\n":
                normalized_chars.append("\n")
                char_to_original.append(index)
                index += 2
                continue
            normalized_chars.append("\n")
            char_to_original.append(index)
            index += 1
            continue
        if char == "\u00a0":
            normalized_chars.append(" ")
            char_to_original.append(index)
            index += 1
            continue
        normalized_chars.append(char)
        char_to_original.append(index)
        index += 1

    return NormalizedSqlResult(text="".join(normalized_chars), char_to_original=char_to_original)


def map_offset(char_to_original: list[int], offset: int, original_length: int) -> int:
    if not char_to_original:
        return max(0, min(offset, original_length))
    if offset <= 0:
        return 0
    if offset >= len(char_to_original):
        return original_length
    return char_to_original[offset]


def map_span_to_original(
    char_to_original: list[int],
    start_offset: int,
    end_offset: int,
    original_length: int,
) -> tuple[int, int]:
    return (
        map_offset(char_to_original, start_offset, original_length),
        map_offset(char_to_original, end_offset, original_length),
    )

