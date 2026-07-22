# Production Dirty SQL Lineage Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver ten independent, production-style dirty SQL lineage cases and run each through the existing Spark lineage analysis path.

**Architecture:** Store static SQL cases under one dated test-data directory and keep their contract in a README. A repository-local Python validator performs deterministic static checks and then invokes `app.api.analyze_controller.analyze`, producing one JSON evidence report without changing the lineage engine.

**Tech Stack:** Spark SQL syntax, Python 3, pytest, existing FastAPI/Pydantic lineage models.

## Global Constraints

- Create exactly ten independent `.sql` files under `测试用例/血缘压测_生产脏SQL_20260719/`.
- Every SQL file must have at least 300 physical lines and at least 26 named relations.
- Every SQL file must contain Chinese comments, backslash regular expressions, CTEs, inline/scalar subqueries, joins, a set operation, windows, aggregates, conditionals, JSON, array expansion, and date/time functions.
- Use Spark dialect and one executable final query per file.
- Do not modify any Dialect Convert or formatting file.
- Preserve all pre-existing uncommitted workspace changes.

---

### Task 1: Add the corpus contract and failing static validator

**Files:**
- Create: `测试用例/血缘压测_生产脏SQL_20260719/README.md`
- Create: `backend/tests/integration/test_production_dirty_sql_corpus.py`
- Create: `tools/validate_production_dirty_sql_corpus.py`

**Interfaces:**
- Consumes: every `*.sql` below the corpus directory.
- Produces: `validate_corpus(corpus_dir: Path) -> list[dict[str, object]]` and `validation_report.json`.

- [ ] **Step 1: Write the failing test**

```python
def test_production_dirty_sql_corpus_meets_static_contract():
    report = validate_corpus(CORPUS_DIR)
    assert len(report) == 10
    assert all(item["line_count"] >= 300 for item in report)
    assert all(item["named_relation_count"] >= 26 for item in report)
    assert all(item["has_dirty_sql_markers"] for item in report)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_production_dirty_sql_corpus.py::test_production_dirty_sql_corpus_meets_static_contract -q`  
Expected: FAIL because the corpus does not yet exist.

- [ ] **Step 3: Implement the validator contract**

```python
def validate_corpus(corpus_dir: Path) -> list[dict[str, object]]:
    files = sorted(corpus_dir.glob("*.sql"))
    return [inspect_case(path) for path in files]
```

`inspect_case` must count physical lines, CTE aliases, inline/scalar aliases, physical table references, Chinese comments, regex backslashes, and required Spark function families.

- [ ] **Step 4: Run the static test after the corpus files are present**

Run: `pytest backend/tests/integration/test_production_dirty_sql_corpus.py::test_production_dirty_sql_corpus_meets_static_contract -q`  
Expected: PASS.

### Task 2: Generate cases 01–05 and document their lineage targets

**Files:**
- Create: `测试用例/血缘压测_生产脏SQL_20260719/01_营销漏斗归因_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/02_交易履约全链路_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/03_AB实验指标归因_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/04_风控反欺诈画像_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/05_流量渠道归因_脏SQL.sql`

**Interfaces:**
- Consumes: Spark SQL parser and `validate_corpus`.
- Produces: five standalone SELECT/CTE lineage workloads.

- [ ] **Step 1: Build each case with 27–30 relations**

Each case contains 14 source/cleanup CTEs, 10 enrichment/metric CTEs, at least two inline or scalar subqueries, and a final SELECT. Use unique domain-prefixed table names so cross-case lineage output is unambiguous.

- [ ] **Step 2: Include required difficult constructs in every case**

```sql
regexp_replace(coalesce(raw_text, ''), '\\s+', ' ') as normalized_text,
get_json_object(event_payload, '$.campaign.id') as campaign_id,
lateral view outer explode(split(coalesce(tag_text, ''), ',')) tag_lv as tag_name
```

Place Chinese comments and a comment containing `;` before at least five CTEs per file.

- [ ] **Step 3: Validate cases 01–05**

Run: `python tools/validate_production_dirty_sql_corpus.py --cases 01 02 03 04 05`  
Expected: five records with `static_contract_passed: true`.

### Task 3: Generate cases 06–10 and complete the README inventory

**Files:**
- Create: `测试用例/血缘压测_生产脏SQL_20260719/06_物流履约SLA_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/07_财务结算对账_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/08_会员留存价值分层_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/09_搜索推荐效果评估_脏SQL.sql`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/10_数据质量巡检汇总_脏SQL.sql`
- Modify: `测试用例/血缘压测_生产脏SQL_20260719/README.md`

**Interfaces:**
- Consumes: the same per-file static contract as tasks 1–2.
- Produces: ten-case README inventory with test purpose and expected lineage observations.

- [ ] **Step 1: Build the remaining five independent workloads**

Use the logistics, settlement, member lifecycle, search recommendation, and quality domains. Do not reuse a case's complete CTE chain or final output names.

- [ ] **Step 2: Document how to use each file**

The README table contains file name, business scenario, line count, named-relation count, difficult constructs, and three root-to-output lineage paths that a reviewer should observe.

- [ ] **Step 3: Run full static validation**

Run: `python tools/validate_production_dirty_sql_corpus.py`  
Expected: ten records, all static thresholds satisfied, and `validation_report.json` written in the corpus directory.

### Task 4: Run parser and graph-integrity lineage regression

**Files:**
- Modify: `tools/validate_production_dirty_sql_corpus.py`
- Modify: `backend/tests/integration/test_production_dirty_sql_corpus.py`
- Create: `测试用例/血缘压测_生产脏SQL_20260719/validation_report.json`

**Interfaces:**
- Consumes: `analyze(AnalyzeRequest(sql=..., dialect="spark"))`.
- Produces: per-case `status`, diagnostics, graph node/edge counts, dangling-edge count, self-loop count, and result path assertions.

- [ ] **Step 1: Add API-equivalent regression test**

```python
def test_production_dirty_sql_corpus_analyzes_without_graph_corruption():
    for path in sorted(CORPUS_DIR.glob("*.sql")):
        result = analyze(AnalyzeRequest(sql=path.read_text(encoding="utf-8"), dialect="spark"))
        node_ids = {node.id for node in result.graph_view_model.nodes}
        assert result.status != "failed", path.name
        assert all(edge.source in node_ids and edge.target in node_ids for edge in result.graph_view_model.edges)
        assert all(edge.source != edge.target for edge in result.graph_view_model.edges)
```

- [ ] **Step 2: Execute the production-corpus regression**

Run: `pytest backend/tests/integration/test_production_dirty_sql_corpus.py -q`  
Expected: PASS; partial results, if any, must be recorded in `validation_report.json` with diagnostic codes.

- [ ] **Step 3: Commit only corpus, validator, test, report, README, and plan changes**

Run: `git add -- "测试用例/血缘压测_生产脏SQL_20260719" tools/validate_production_dirty_sql_corpus.py backend/tests/integration/test_production_dirty_sql_corpus.py docs/superpowers/plans/2026-07-19-production-dirty-sql-lineage-corpus.md && git commit -m "test: add production dirty SQL lineage corpus"`  
Expected: a commit containing no Dialect Convert file and no pre-existing unrelated change.
