case_id: `spark_template_variable`
difficulty: `S1`
dialect: `spark`
covered_features: `${...}` template shielding and original-parse fallback
expected_behavior: raw template SQL should recover through shielded analysis SQL instead of failing outright
allowed_partial: `true`
known_limitations: original parser failure is expected and remains visible through diagnostics

