case_id: `complex_regex_json`
difficulty: `S2`
dialect: `spark`
covered_features: `regexp_extract`, `get_json_object`, template literal shielding, CTE fallback compatibility
expected_behavior: regex and JSONPath literals are shielded without losing segment structure
allowed_partial: `true`
known_limitations: only defensive diagnostics are asserted; downstream column lineage is not frozen here

