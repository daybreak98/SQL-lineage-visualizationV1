# C10 Golden Case 回归与交付冻结

## 目标

把 C00-C08 的主链路能力，以及当前表达式退化字段依赖能力，冻结成可持续迭代的测试基线。

## 必须冻结的核心路径

```text
Health
Analyze failed / partial / success
SQL parse
output_fields
single table lineage
join alias lineage
CTE structure graph
metadata import / query
select * expansion
unknown / ambiguous diagnostics
source location
expression degraded column dependencies
```

## Golden Case 文件

```text
backend/tests/golden_cases/
  c02_output_fields.sql
  c03_single_table.sql
  c04_join_alias.sql
  c05_cte_metric.sql
  c06_metadata.json
  c07_select_star.sql
  c07_unknown_column.sql
  c07_ambiguous_column.sql
  c09_expression_metric.sql
```

## 后端测试要求

```text
pytest backend/tests
```

至少覆盖：

```text
API contract test
Graph edge integrity test
Diagnostics test
Metadata repository test
Golden SQL expected nodes / edges test
```

Graph edge integrity 必须检查：

```text
每条 edge.source 存在
每条 edge.target 存在
node id 不重复
edge id 不重复
```

## 前端手工回归清单

```text
1. 打开页面，Health 在线。
2. 输入错误 SQL，Analyze 后进入 failed。
3. 输入 select a from t，画布出现单表字段血缘。
4. 输入 Join SQL，字段归属正确。
5. 输入 CTE SQL，默认显示 subquery_dependency。
6. 导入 metadata JSON，select * 可展开。
7. 输入 unknown 字段，出现 UNKNOWN_COLUMN。
8. 输入 ambiguous 字段，出现 AMBIGUOUS_COLUMN。
9. 点击节点 Locate SQL，编辑器跳转。
10. 输入聚合表达式 SQL，Column 视图展示退化字段依赖。
```

## 表达式边界

当前只冻结表达式退化字段依赖：

```text
source physical columns -> output columns -> Query Result
```

不冻结完整表达式语义：

```text
expression nodes
expression_dependency edges
semantics_report.metrics
口径详情面板
```

## 交付冻结标准

C10 通过后，后续开发必须保证：

```text
1. Golden Case 测试持续通过。
2. 图节点和边不会出现悬空引用。
3. 新能力不能破坏普通字段血缘。
4. 表达式退化字段依赖不能回退为空图。
```
