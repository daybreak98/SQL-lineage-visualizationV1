# Production Dirty SQL Lineage Corpus Design

## 1. Goal

Create a manual regression corpus for SQL lineage analysis. It contains ten independent Spark-compatible SQL files that resemble difficult production ETL queries while remaining intentionally analyzable.

This work is limited to lineage test data, its manifest, and validation tooling. No Dialect Convert page, conversion API, formatting API, or related test is in scope.

## 2. Acceptance Criteria

Every SQL file must independently satisfy all of the following:

- at least 300 physical lines;
- at least 26 named relations, counted as physical source tables, CTEs, and aliased inline/scalar subqueries;
- at least eight physical source tables;
- one final query statement suitable for submission to `/api/sql/analyze`;
- Chinese line and block comments, including comments that contain semicolons;
- string literals with regular-expression backslashes such as `\\d`, `\\s`, and `\\u4e00-\\u9fa5`;
- joins, nested CTEs, inline subqueries, a set operation, window functions, aggregate expressions, conditional expressions, JSON extraction, array expansion, and date/time expressions;
- no invented metadata dependency: table and column names are fictional but internally coherent.

The corpus must also include a README and a machine-readable validation report. The report records line count, physical-table count, named-relation count, dirty-SQL markers, parser result, and graph-integrity result for every case.

## 3. File Layout

```text
测试用例/血缘压测_生产脏SQL_20260719/
  README.md
  01_营销漏斗归因_脏SQL.sql
  02_交易履约全链路_脏SQL.sql
  03_AB实验指标归因_脏SQL.sql
  04_风控反欺诈画像_脏SQL.sql
  05_流量渠道归因_脏SQL.sql
  06_物流履约SLA_脏SQL.sql
  07_财务结算对账_脏SQL.sql
  08_会员留存价值分层_脏SQL.sql
  09_搜索推荐效果评估_脏SQL.sql
  10_数据质量巡检汇总_脏SQL.sql
  validation_report.json
```

A small repository-local validator will create `validation_report.json`; it does not change application code or test behavior.

## 4. Case Design

All files use a shared structural shape so their scale is comparable: 14-18 source CTEs, 8-10 transformation CTEs, 2-4 inline/scalar subqueries, and a final projection. Each file uses a distinct domain and primary lineage challenge.

| Case | Domain | Primary lineage challenge |
| --- | --- | --- |
| 01 | Marketing funnel | session-to-order attribution and campaign JSON fields |
| 02 | Order fulfillment | order, payment, shipment, refund, and SLA rollups |
| 03 | A/B experiment | exposure bucketing, cohort joins, and metric definitions |
| 04 | Fraud control | device/account graph signals and rule-hit aggregation |
| 05 | Traffic attribution | URL parsing, UTM regular expressions, and multi-touch paths |
| 06 | Logistics SLA | route stages, exception events, and time-window calculations |
| 07 | Financial settlement | payment channels, fee allocation, reconciliation, and currency conversion |
| 08 | Member lifecycle | behavior cohorts, retention windows, and customer value tiers |
| 09 | Search recommendation | query normalization, exposure/click/order funnel, and ranking windows |
| 10 | Data quality | source reconciliation, null/duplicate checks, and anomaly summaries |

## 5. Dirty SQL Rules

The corpus simulates production readability and stability problems without intentionally creating invalid syntax:

- use Chinese business comments, mixed English abbreviations, and block comments before CTEs;
- include semicolons within comments only, never inside executable expressions;
- include `regexp_extract`, `regexp_replace`, `rlike`, and escaped backslashes in literals;
- mix uppercase and lowercase keywords, long aliases, redundant null handling, and nested formatting;
- use valid Spark constructs such as `get_json_object`, `lateral view explode`, `collect_set`, `row_number`, `lag`, `date_sub`, and `from_unixtime`.

The corpus excludes unsupported proprietary UDFs, malformed SQL, external table DDL, and multiple executable statements, because the purpose is lineage coverage rather than parser-failure fuzzing.

## 6. Validation Design

The validator has two layers:

1. Static checks read each `.sql` file and enforce the per-file line, relation, source-table, Chinese-comment, regex, and complex-function thresholds.
2. API-equivalent parser checks call the existing analysis entry point with Spark dialect and verify that the response is not `failed`, all graph edges reference existing nodes, and no column-lineage edge is self-referential.

If a query is parsed only partially, the report preserves the diagnostic codes and marks the case as requiring review instead of silently treating it as successful.

## 7. Documentation and Review

`README.md` gives a one-row inventory for each case and explains how to submit a file in the workbench. `validation_report.json` is the evidence artifact for review.

The generated corpus is test data only. It must not modify the current uncommitted lineage-engine changes or any Dialect Convert files.
