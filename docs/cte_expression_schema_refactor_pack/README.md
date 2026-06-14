# CTE 复杂表达式列血缘穿透改造开发包

本开发包用于解决 SQL 血缘项目中 CTE 复杂表达式列血缘断链问题。

## 目标

当前 `build_cte_schemas` 已能处理简单列投影：

```sql
with order_base as (
  select o.user_id, o.order_no
  from dwd_order_di o
)
```

但对复杂表达式会断链：

```sql
with search_result as (
  select count(distinct a.search_request_uid) as search_times
  from search_base a
)
select search_times from search_result;
```

原因是 `name_resolver` 只擅长 `Column` / `Alias(Column)`，对 `Alias(Count(Distinct(Column)))` 这类表达式不会产出字段映射，导致：

```text
schema[search_result].search_times 缺失
rollup 无法从 search_result.search_times 继续穿透
```

## 改造原则

```text
只增强 build_cte_schemas；
不改 name_resolver；
不改 ExpressionAnalyzer；
不改 GraphBuilder；
不改前端；
Controller 原则上不改，除非需要透传 diagnostics。
```

## 包内容

| 路径 | 说明 |
|---|---|
| `docs/01_design.md` | 详细设计文档 |
| `docs/02_development_instructions.md` | 给 opencode 的开发说明 |
| `docs/03_regression_tests.md` | 回归测试清单 |
| `core_code/cte_schema_models.py` | 新增/参考领域模型 |
| `core_code/cte_scope_resolver.py` | CTE SELECT scope / alias 解析 |
| `core_code/expression_dependency_resolver.py` | ExpressionAnalyzer depends_on 到 ColumnRef 的解析 |
| `core_code/cte_schema_builder_patch.py` | build_cte_schemas 核心补丁逻辑 |
| `core_code/transform_type.py` | 表达式 transform_type 推断 |
| `tests/test_cte_expression_schema_cases.py` | pytest 回归测试样例 |
| `opencode_prompt.md` | 可直接复制给 opencode 的提示词 |

## 最重要的判断

ExpressionAnalyzer 只能告诉你：

```text
search_times depends_on search_request_uid
```

但它不能单独告诉你：

```text
search_request_uid 来自 search_base 还是 dim_user？
search_base 是 CTE 还是物理表？
```

所以本方案新增中间层：

```text
ExpressionAnalyzer depends_on
  → 当前 SELECT scope / alias_to_relation
  → metadata / cte_schemas 消歧
  → ColumnRef
  → CTE schema
```
