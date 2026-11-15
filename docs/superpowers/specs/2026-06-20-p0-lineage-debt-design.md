# P0 Lineage Debt Design

## Goal

Eliminate the correctness risk caused by three separate Lateral View dependency
implementations and remove the obsolete structure-rollup placeholder.

## Scope

- Keep `lateral_view_dependency_extractor.py` as the single AST extraction
  boundary.
- Map every Lateral View output alias column to the physical columns referenced
  by its row-expanding expression.
- Resolve table aliases through the existing CTE-body scope resolver.
- Let the derived schema overwrite the incorrect same-name projection produced
  by the generic name resolver.
- Preserve current defensive diagnostics, unsupported-feature reporting, and
  existing API status policy for Lateral View SQL.
- Delete `lineage_rollup_service.py`, which has no runtime or test callers.

## Non-goals

- Claiming complete support for every Hive/Spark Lateral View form.
- Integrating `PortOrderOptimizer`.
- Splitting large orchestration or frontend files.

## Data Flow

1. SQLGlot parses `LATERAL VIEW EXPLODE(...) e AS amount_item`.
2. The extractor returns `amount_item -> b.refund_amount`.
3. `build_scope_from_cte_body` resolves alias `b` to `ods_order_log`.
4. `DerivedRelationSchema` stores
   `amount_item -> ods_order_log.refund_amount` with transform type
   `lateral_view`.

## Verification

- Unit test the AST extractor.
- Unit test the resulting derived CTE schema.
- Keep the existing API diagnostic test proving defensive `partial` behavior.
- Run the complete backend test suite.
