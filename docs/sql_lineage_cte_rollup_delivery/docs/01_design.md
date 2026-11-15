# CTE 递归列级血缘穿透设计方案

## 1. 目标

将当前字段血缘从：

```text
search_result.show_uv → output:S2D
order_result.total_order_commission → output:单UV收益
```

升级为：

```text
default.dwd_ihotel_flow_app_searchlist_di.orig_device_id → search_result.show_uv → output:单UV收益
mdw_order_v3_international.init_commission_after → order_detail.order_commission → order_result.total_order_commission → output:单UV收益
```

也就是支持：

```text
final output column
  ← final select input columns
  ← CTE output columns
  ← CTE 内部表达式依赖字段
  ← 物理根表字段
```

## 2. 为什么不能只用 SimpleColumnLineage while 展开

旧模型通常是：

```python
SimpleColumnLineage(
    source_table="search_result",
    source_column="show_uv",
    output_column="S2D",
)
```

这个模型只能表达：

```text
一个输出字段 ← 一个输入字段
```

但真实 SQL 中：

```sql
cast(b.total_order_commission / a.show_uv as decimal(20,2)) as `单UV收益`
```

一个输出字段依赖两个 CTE 字段：

```text
output:单UV收益
  ← order_result.total_order_commission
  ← search_result.show_uv
```

继续展开后又变成多个物理根字段：

```text
output:单UV收益
  ← mdw_order_v3_international.init_commission_after
  ← mdw_order_v3_international.coupon_info
  ← mdw_order_v3_international.ext_plat_certificate
  ← mdw_order_v3_international.batch_series
  ← default.dwd_ihotel_flow_app_searchlist_di.orig_device_id
  ← default.dwd_ihotel_flow_app_searchlist_di.is_display
  ← default.dwd_ihotel_flow_app_searchlist_di.hotel_seq
```

所以内部必须支持：

```text
一个输出字段 ← 多个输入字段
```

## 3. 改造后的后端链路

```text
AnalyzeController
  ↓
AnalysisOrchestrator
  ↓
parse_sql
  ↓
ScopeResolver
  ↓
DerivedRelationSchemaBuilder
  ├─ CTE schema
  ├─ subquery schema
  └─ select * 展开结果
  ↓
NameResolver / ExpressionDependencyExtractor
  ↓
immediate ColumnDependency[]
  ↓
CteColumnRollupService
  ↓
root ColumnDependency[] + lineage_paths[]
  ↓
GraphBuilder
  ↓
AnalysisResult
```

## 4. 新增核心概念

### 4.1 ColumnRef

表示一个字段引用，可以是物理表字段、CTE 字段、子查询字段、未知字段。

```python
ColumnRef(
    relation_name="search_result",
    column_name="show_uv",
    relation_kind="cte",
)
```

### 4.2 ColumnDependency

表示一个输出字段依赖哪些输入字段。

```python
ColumnDependency(
    output=ColumnRef("final", "单UV收益", "output"),
    inputs=[
        ColumnRef("order_result", "total_order_commission", "cte"),
        ColumnRef("search_result", "show_uv", "cte"),
    ],
    transform_type="expression",
)
```

### 4.3 DerivedRelationSchema

表示 CTE / 子查询 / 派生表的输出字段 schema。

```python
DerivedRelationSchema(
    relation_name="search_result",
    output_columns={
        "show_uv": ColumnDependency(...),
        "click_uv": ColumnDependency(...),
    }
)
```

## 5. 递归穿透算法

使用 DFS，不使用 while 单链。

```text
expand(output_column):
  if input 是物理表字段:
      return input
  if input 是 CTE 字段:
      找到 CTE schema 中该字段的 ColumnDependency
      对它的 inputs 继续 expand
  if input 是子查询字段:
      同 CTE
  if 找不到 schema:
      保留当前字段，并返回 diagnostic
```

## 6. 对外响应建议

保留三份产物：

```json
{
  "immediate_column_lineage": [],
  "root_column_lineage": [],
  "lineage_paths": []
}
```

- `immediate_column_lineage`：最终 SELECT 的一跳血缘。
- `root_column_lineage`：穿透到物理根表后的血缘。
- `lineage_paths`：完整路径，用于调试和图谱展开。

## 7. 降级原则

| 场景 | 处理方式 |
|---|---|
| CTE 字段找不到 | 保留当前 CTE 字段，诊断 `UNKNOWN_DERIVED_COLUMN` |
| 递归 CTE 或循环依赖 | 停止递归，诊断 `CYCLIC_DERIVED_RELATION` |
| 表达式依赖抽取失败 | 保留表达式级节点，诊断 `LOW_CONFIDENCE_LINEAGE` |
| `select *` 无元数据 | 返回 partial，诊断 `STAR_EXPANSION_REQUIRES_METADATA` |
| 字段歧义 | 不猜测来源，诊断 `AMBIGUOUS_COLUMN` |

## 8. 与现有代码的边界

建议：

```text
Controller 不改或少改
Orchestrator 负责串联新服务
NameResolver 增加可选 derived_schemas 入参
GraphBuilder 默认消费 root_lineage，也允许切换 immediate/path 视图
```

不建议：

```text
不要在 Controller 层直接 rollup
不要把 CTE 特判散落在 graph_builder
不要让 SimpleColumnLineage 承担多输入表达式血缘
```
