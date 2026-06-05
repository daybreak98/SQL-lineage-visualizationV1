from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.complex_sql_guard import analyze_complex_sql


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_CASES_ROOT = ROOT / "golden_cases"


def _case_ids() -> list[str]:
    return sorted(path.name for path in GOLDEN_CASES_ROOT.iterdir() if path.is_dir())


@pytest.mark.parametrize("case_id", _case_ids())
def test_golden_cases(case_id: str):
    case_dir = GOLDEN_CASES_ROOT / case_id
    sql = (case_dir / "input.sql").read_text(encoding="utf-8")
    metadata = json.loads((case_dir / "metadata.json").read_text(encoding="utf-8"))
    expected_diagnostics = json.loads((case_dir / "expected.diagnostics.json").read_text(encoding="utf-8"))
    expected_segments = json.loads((case_dir / "expected.segments.json").read_text(encoding="utf-8"))

    result = analyze_complex_sql(
        sql,
        dialect=metadata.get("dialect", "spark"),
        options=metadata.get("options", {}),
    )

    assert result.status.value in expected_diagnostics["allowed_status"]

    diagnostic_codes = {diagnostic.code for diagnostic in result.diagnostics}
    for required_code in expected_diagnostics.get("required_diagnostics", []):
        assert required_code in diagnostic_codes

    segment_types = {segment.segment_type for segment in result.segments}
    for required_type in expected_segments.get("required_segment_types", []):
        assert required_type in segment_types

