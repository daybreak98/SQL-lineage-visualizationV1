case_id: `parse_error_partial_fallback`
difficulty: `S2`
dialect: `spark`
covered_features: broken CTE item, segment parse fallback, partial result diagnostics
expected_behavior: a single broken CTE should not collapse the whole statement; recoverable segments still parse
allowed_partial: `true`
known_limitations: downstream lineage is intentionally skipped because no full tree exists

