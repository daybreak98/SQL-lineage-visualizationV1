case_id: `hive_lateral_view_explode`
difficulty: `S2`
dialect: `hive`
covered_features: `lateral view`, `explode`, row-expanding diagnostics
expected_behavior: parser succeeds defensively and emits unsupported-feature diagnostics instead of crashing
allowed_partial: `true`
known_limitations: current lineage resolver still downgrades lateral view to defensive mode

