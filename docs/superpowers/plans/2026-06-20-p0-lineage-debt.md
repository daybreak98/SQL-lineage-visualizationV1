# P0 Lineage Debt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Lateral View output columns resolve to their real upstream input columns through one production implementation.

**Architecture:** Keep AST recognition in `lateral_view_dependency_extractor.py` and alias/domain conversion in `derived_relation_schema_builder.py`. Preserve the existing complex-SQL guard diagnostics until broader Lateral View coverage is implemented.

**Tech Stack:** Python 3.11, SQLGlot, pytest.

---

### Task 1: Lock the expected lineage behavior

**Files:**
- Modify: `backend/tests/test_derived_relation_schema_builder.py`
- Create: `backend/tests/test_lateral_view_dependency_extractor.py`

- [x] Add a schema test asserting `amount_item` depends on `ods_order_log.refund_amount`.
- [x] Add an extractor test asserting the AST output alias and source alias/column.
- [x] Run both tests and verify they fail against the current implementation.

### Task 2: Consolidate Lateral View extraction

**Files:**
- Modify: `backend/app/services/lateral_view_dependency_extractor.py`
- Modify: `backend/app/services/derived_relation_schema_builder.py`
- Modify: `backend/app/domain/cte_rollup_models.py`

- [x] Make the extractor return one dependency per output/source-column pair.
- [x] Resolve source aliases with `build_scope_from_cte_body`.
- [x] Replace the two private Lateral View passes with one application step.
- [x] Add `lateral_view` to the transform type contract.
- [x] Run the focused tests and verify they pass.

### Task 3: Remove obsolete debt and update documentation

**Files:**
- Delete: `backend/app/services/lineage_rollup_service.py`
- Modify: `docs/待优化/architecture_debt.md`

- [x] Remove the unused placeholder module.
- [x] Reclassify completed P0 items and correct the PortOrderOptimizer analysis.
- [x] Run import searches to confirm no stale runtime references remain.

### Task 4: Verify the backend

- [x] Run focused Lateral View and derived-schema tests.
- [x] Run the complete backend pytest suite.
- [x] Call `/api/sql/analyze` with the Lateral View sample and verify unsupported-feature reporting remains present.
