# 给 opencode 的开发提示词

你需要在 SQL 血缘项目中修复 CTE 复杂表达式列血缘断链问题。

## 问题

当前 `build_cte_schemas` 可以处理简单列投影：

```sql
with order_base as (
  select o.user_id, o.order_no
  from dwd_order_di o
)
```

但无法处理复杂表达式：

```sql
with search_result as (
  select count(distinct a.search_request_uid) as search_times
  from search_base a
)
select search_times from search_result;
```

原因：`name_resolver` 对 `Alias(Count(Distinct(Column)))` 不生成 lineage，导致 `schema[search_result].search_times` 缺失，rollup 无法继续穿透。

## 目标

只增强 `build_cte_schemas`：在原有 name_resolver 之后追加 ExpressionAnalyzer 结果，把复杂表达式输出列写入 CTE schema。

## 重要原则

1. 不改 `name_resolver.py`。
2. 不改 `ExpressionAnalyzer`。
3. 不改 `GraphBuilder`。
4. 不改前端。
5. Controller 原则上不改；如果 build_cte_schemas 新增 diagnostics 后无法透传，可以做最小透传。
6. ExpressionAnalyzer 的 `depends_on` 不能直接写入 schema，必须先经过当前 SELECT scope 的 alias 解析和字段消歧。
7. name_resolver 的结果优先，ExpressionAnalyzer 只补 name_resolver 未覆盖的输出列。
8. 裸字段多表歧义时不猜，返回 `AMBIGUOUS_COLUMN`。
9. `count(*)` 不生成 `unknown.*`。

## 需要实现的核心函数

参考开发包 `core_code`：

```text
cte_schema_models.py
cte_scope_resolver.py
expression_dependency_resolver.py
transform_type.py
cte_schema_builder_patch.py
```

核心链路：

```text
build_cte_schemas
  → for each CTE in definition order
  → extract_select_scope(inner_select, cte_names)
  → name_resolver(inner_select) → schema simple dependencies
  → ExpressionAnalyzer().analyze_select(inner_select)
  → resolve metric.depends_on by scope + cte_schemas + metadata
  → merge into schema only if output column not already covered
```

## 字段解析规则

### 限定字段

```text
a.search_request_uid
```

先用 `a` 查当前 SELECT scope：

```text
a → search_base
```

再判断 `search_base` 是 CTE 还是物理表。

### 裸字段

```text
search_request_uid
```

如果当前 SELECT 只有一个输入关系，可以归属该关系。

如果多个输入关系，必须用 metadata / cte_schema 消歧。

如果多个关系都有该字段，返回 `AMBIGUOUS_COLUMN`，不要猜。

### count(*)

```text
transform_type = aggregate
dependency_type = relation_rowset
input_columns = []
```

不要生成 `unknown.*`。

## 必须增加的测试

1. `count(distinct a.search_request_uid) as search_times`
2. `price * quantity as gmv`
3. `case when order_status = 'DONE' then amount else 0 end as valid_amount`
4. `count(distinct o.user_id)` 限定字段正确归属 alias 对应 CTE/table
5. `count(distinct user_id)` 多表歧义返回 `AMBIGUOUS_COLUMN`
6. `count(*) as order_cnt` 不生成 `unknown.*`
7. `1 as is_valid` 无字段依赖，transform_type = constant
8. 原有简单列 CTE 用例不回归

## 验收标准

```text
pytest 全量通过；
旧 CTE 简单列血缘不回归；
复杂表达式输出列能进入 CTE schema；
rollup 可以利用这些 schema 继续穿透；
歧义字段不生成错误血缘；
diagnostics 能进入最终结果或至少进入 schema build result。
```
