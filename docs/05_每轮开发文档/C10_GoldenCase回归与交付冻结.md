# C10｜Golden Case 回归与交付冻结

## 1. 本轮目标

把 C00-C09 的能力冻结成可持续迭代的基线。

```text
后端能力：核心 SQL 回归测试稳定
前端效果：关键交互路径不回退
学习重点：回归测试、快照、交付清单
```

---

## 2. 必须冻结的核心路径

```text
Health
Analyze placeholder / failed / partial / success
SQL parse
output_fields
single table lineage
join alias lineage
CTE structure graph
metadata import / query
select * expansion
unknown / ambiguous diagnostics
source location
expression detail
```

---

## 3. Golden Case 文件建议

```text
测试用例/golden_cases/
  c03_single_table.sql
  c04_join_alias.sql
  c05_cte_metric.sql
  c06_metadata.json
  c07_select_star.sql
  c08_source_location.sql
  c09_expression_metric.sql
```

---

## 4. 后端测试要求

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

---

## 5. 前端手工回归清单

```text
1. 打开页面，Health 在线
2. 输入错误 SQL，Analyze 后 failed
3. 输入 select a from t，画布出现单表字段血缘
4. 输入 Join SQL，字段归属正确
5. 输入 CTE SQL，默认显示 subquery_dependency
6. 导入 metadata JSON，字段注释可查
7. 输入 select *，可展开或给出诊断
8. 点击节点 Locate SQL，编辑器跳转
9. 点击表达式字段，DetailPanel 展示依赖
```

---

## 6. 交付冻结标准

C10 通过后，才能进入 P1 扩展：

```text
更复杂 CTE
更复杂子查询
Monaco completion / hover
SQL format
SQL diff
history snapshots
AI review
DataHub / OpenLineage
```

---

## 7. 给 OpenCode 的单轮提示词

```text
请只实现 C10：C00-C09 的 Golden Case 回归与交付冻结。
不要新增大功能，重点补齐测试、修复不稳定契约、检查 graph edge integrity、整理回归 SQL 和元数据样例。
所有测试通过后，输出当前能力清单、已知限制和下一阶段建议。
```
