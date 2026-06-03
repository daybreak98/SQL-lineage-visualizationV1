from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimpleColumnLineage:
    source_table: str
    source_column: str
    output_column: str

    @property
    def source_label(self) -> str:
        return f"{self.source_table}.{self.source_column}"
