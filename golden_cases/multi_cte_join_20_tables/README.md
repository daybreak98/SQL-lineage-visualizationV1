case_id: `multi_cte_join_20_tables`
difficulty: `S3`
dialect: `spark`
covered_features: long CTE chain, 20-table joins, complexity-risk detection
expected_behavior: very large join topology stays parseable and emits complexity diagnostics without crashing
allowed_partial: `false`
known_limitations: this case validates defensive parsing and segmentation, not final lineage correctness

