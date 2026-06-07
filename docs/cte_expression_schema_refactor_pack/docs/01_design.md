# CTE 复杂表达式列血缘穿透改造设计文档

## 1. 背景问题

当前 CTE 列血缘穿透依赖 `build_cte_schemas` 生成每个 CTE 输出字段到上游字段的映射。

对于简单列投影：

```sql
with order_base as (
  select
    o.user_id,
    o.order_no
  from dwd_order_di o
)
select user_id, order_no from order_base;
```

`name_resolver` 可以生成：

```text
dwd_order_di.user_id  → order_base.user_id
dwd_order_di.order_no → order_base.order_no
```

于是 CTE schema 可用，rollup 可以继续穿透。

但是对于复杂表达式：

```sql
with search_result as (
  select
    count(distinct a.search_request_uid) as search_times
  from search_base a
)
select search_times from search_result;
```

select item 是：

```text
Alias(Count(Distinct(Column)))
```

不是：

```text
Column
Alias(Column)
```

因此 `_simple_column_from_select_item()` 返回 `None`，`name_resolver` 不会为 `search_times` 生成 lineage，导致：

```text
schema[search_result].search_times 缺失
rollup 知道 search_result 是 CTE，但不知道 search_times 如何继续向上游穿透
```

## 2. 改造目标

在 `build_cte_schemas` 中接入 `ExpressionAnalyzer`，补齐复杂表达式输出列的依赖字段。

目标能力：

| 表达式 | 输出列 | 依赖字段 |
|---|---|---|
| `count(distinct a.search_request_uid) as search_times` | `search_times` | `search_base.search_request_uid` |
| `price * quantity as gmv` | `gmv` | `order_base.price`, `order_base.quantity` |
| `case when status = 1 then amount else 0 end as valid_amount` | `valid_amount` | `order_base.status`, `order_base.amount` |
| `count(*) as order_cnt` | `order_cnt` | relation rowset dependency，不生成 `unknown.*` |
| `1 as flag` | `flag` | 无字段依赖，transform_type = constant |

## 3. 非目标

本轮不做以下事项：

```text
不重写 name_resolver；
不重写 ExpressionAnalyzer；
不把表达式分析直接塞进 GraphBuilder；
不改变前端 GraphViewModel；
不承诺所有复杂 SQL 都精确穿透；
不处理动态 SQL / correlated subquery / lateral view 的完整字段级血缘。
```

## 4. 核心设计

### 4.1 总体链路

```text
build_cte_schemas(tree, metadata, cte_names)
  ↓
for each CTE in definition order:
  ↓
extract inner_select
  ↓
extract_select_scope(inner_select, cte_names)
  ├─ alias_to_relation
  ├─ visible_relations
  └─ relation_kind: cte / table / subquery / unknown
  ↓
name_resolver(inner_select)
  └─ 生成简单列 ColumnDependency
  ↓
ExpressionAnalyzer.analyze_select(inner_select)
  └─ 生成 ExpressionMetric(name, expression, depends_on, aggregate_functions)
  ↓
for each metric not already covered by name_resolver:
  ↓
resolve depends_on by scope + metadata + existing cte_schemas
  ↓
add ColumnDependency(output_column=metric.name, input_columns=ColumnRef[])
  ↓
cte_schemas[cte_name] = schema
```

### 4.2 为什么不能直接使用 ExpressionAnalyzer.depends_on

ExpressionAnalyzer 产出可能是：

```text
search_request_uid
a.search_request_uid
search_base.search_request_uid
```

但这些只是表达式里的字段引用，不等于可用于 rollup 的稳定来源。

必须经过当前 CTE body 的 SELECT scope 解析：

```sql
from search_base a
```

得到：

```text
a → search_base
search_base → search_base
```

然后才能判断：

```text
search_base 是已定义 CTE？还是物理表？
```

最终形成：

```text
ColumnRef(relation_name="search_base", column_name="search_request_uid", relation_kind="cte")
```

或：

```text
ColumnRef(relation_name="dwd_order_di", column_name="order_no", relation_kind="table")
```

### 4.3 name_resolver 与 ExpressionAnalyzer 的优先级

合并规则：

| 情况 | 处理 |
|---|---|
| name_resolver 已生成该输出列 | 保留 name_resolver 结果，最多补充 expression 信息 |
| name_resolver 未生成，ExpressionAnalyzer 有依赖 | 新增 ColumnDependency |
| 两边都有但依赖不一致 | 不覆盖，记录 diagnostic |
| ExpressionAnalyzer 没有字段依赖 | 根据表达式类型处理：constant / count_star / system_function |

原因：`name_resolver` 对简单列和别名解析更精确，ExpressionAnalyzer 用于补复杂表达式缺口。

## 5. Scope 解析规则

### 5.1 限定字段

```sql
select count(distinct a.search_request_uid) as search_times
from search_base a
```

ExpressionAnalyzer 返回：

```text
a.search_request_uid
```

处理：

```text
a → search_base
search_base in cte_names ? relation_kind=cte : table
```

### 5.2 裸字段 + 单输入关系

```sql
select count(distinct search_request_uid) as search_times
from search_base
```

只有一个可见关系，允许解析为：

```text
search_base.search_request_uid
```

### 5.3 裸字段 + 多输入关系 + metadata 可消歧

```sql
select count(distinct user_id) as user_cnt
from order_base o
join user_profile p on o.user_id = p.user_id
```

如果 metadata / cte_schema 显示只有 `order_base` 有 `user_id`，则归属 `order_base.user_id`。

### 5.4 裸字段 + 多输入关系 + 多方都有该字段

不能猜，返回：

```text
AMBIGUOUS_COLUMN
```

### 5.5 裸字段 + 无法确认来源

返回：

```text
UNKNOWN_COLUMN 或 LOW_CONFIDENCE_LINEAGE
```

不生成错误的 `unknown.column` 血缘，除非当前项目已有约定需要保留 unknown 节点。

## 6. 特殊表达式处理

| 表达式 | 处理 |
|---|---|
| `count(*)` | `transform_type=aggregate`，`dependency_type=relation_rowset`，不生成 `unknown.*` |
| `1 as flag` | `transform_type=constant`，无字段依赖 |
| `current_date as dt` | `transform_type=system_function`，无字段依赖 |
| `coalesce(a,b)` | `transform_type=function`，依赖 `a,b` |
| `sum(price * cnt)` | `transform_type=aggregate_expression`，依赖 `price,cnt` |
| `row_number() over(partition by user_id order by dt)` | `transform_type=window`，依赖 partition/order 字段；如果 ExpressionAnalyzer 暂不支持，返回 partial |

## 7. Diagnostics 要求

至少新增或复用以下诊断：

```text
AMBIGUOUS_COLUMN
UNKNOWN_COLUMN
LOW_CONFIDENCE_LINEAGE
UNSUPPORTED_COMPLEX_QUERY
PARTIAL_LINEAGE_RESULT
```

要求：

```text
复杂表达式能补齐则不报 unsupported；
能抽取表达式但无法归属字段时返回 warning；
不要静默生成不可信血缘；
diagnostics 应透传到最终 AnalysisResult。
```

## 8. 验收标准

最低验收：

```text
1. 简单列 CTE 旧能力不回归。
2. count(distinct a.col) 能写入 CTE schema。
3. price * quantity 能写入 CTE schema。
4. case when 表达式能写入多个依赖字段。
5. 裸字段多表歧义不猜。
6. count(*) 不生成 unknown.*。
7. rollup 可以基于表达式 schema 继续穿透。
```
