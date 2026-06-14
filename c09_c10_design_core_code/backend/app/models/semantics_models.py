"""C09 semantics response models reference.

If the project already has Pydantic response models, merge these fields into the existing model file.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MetricSemantics(BaseModel):
    name: str
    entity_id: str | None = None
    expression: str
    depends_on: list[str] = Field(default_factory=list)
    aggregate_functions: list[str] = Field(default_factory=list)
    operators: list[str] = Field(default_factory=list)
    function_names: list[str] = Field(default_factory=list)
    description: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence_level: Literal["high", "medium", "low"] = "high"


class SemanticsReport(BaseModel):
    metrics: list[MetricSemantics] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    result_grain: str | None = None
    notes: list[str] = Field(default_factory=list)


# Existing AnalysisResult should add:
# semantics_report: SemanticsReport = Field(default_factory=SemanticsReport)
