# C05｜CTE / 子查询结构依赖与默认视图

## 1. 本轮目标

支持数仓 SQL 最常见的 CTE 结构，并让前端 Analyze 后默认展示结构依赖图。

```text
后端能力：识别 CTE / 子查询 / Query Result 的结构依赖
前端效果：默认 renderMode = subquery_dependency
学习重点：不要把 CTE 伪装成物理表；结构依赖从字段关系汇总
```

---

## 2. 支持范围

优先支持：

```sql
with order_base as (...),
metric_base as (
  select country_name, count(order_no) as order_cnt
  from order_base
  group by country_name
)
select country_name, order_cnt from metric_base
```

本轮要求：

```text
order_base → metric_base → Query Result
```

能展示结构依赖即可，不要求所有字段穿透 100% 准确。

---

## 3. 允许创建

```text
backend/app/services/cte_structure_service.py
backend/app/services/lineage_rollup_service.py
backend/tests/test_cte_structure_service.py
backend/tests/integration/test_analyze_api_c05.py
```

---

## 4. 节点类型

推荐：

```text
cte:order_base
cte:metric_base
query_result:final
physical_table:dwd_order_di
```

边类型：

```text
cte_dependency
table_to_cte
cte_to_result
```

要求：

1. CTE 节点不能使用 `physical_table` 类型。
2. Query Result 必须存在。
3. 表级边如果没有列级证据，至少标记 confidence=low 或 partial。

---

## 5. 前端对接文档

Analyze 成功后：

```text
1. 默认进入 subquery_dependency 视图
2. 不默认展示字段级复杂全图
3. 用户选择某个 output field 后，再进入字段路径视图
```

前端状态：

```text
result.graph_view_model.view_mode == "subquery_dependency"
```

---

## 6. 测试验收

后端：

```text
CTE SQL 中 graph_view_model.view_mode == subquery_dependency
nodes 包含 cte:order_base、cte:metric_base、query_result:final
edges 包含 order_base -> metric_base、metric_base -> final
```

前端：

```text
输入 CTE SQL
点击 Analyze
画布默认显示 CTE 结构依赖，而不是密密麻麻字段全图
```

---

## 7. 禁止越界

不要做：

```text
完整复杂子查询字段穿透
SourceLocation
SemanticsReport
历史快照
```

---

## 8. 给 OpenCode 的单轮提示词

```text
请只实现 C05：CTE / 子查询结构依赖图。
Analyze 成功后 graph_view_model.view_mode 默认返回 subquery_dependency。
必须区分 cte、physical_table、query_result，不允许把 CTE 伪装成物理表。
前端验收是 CTE SQL 默认显示结构依赖图。
不要做 SourceLocation、Semantics、SQLite。
```
