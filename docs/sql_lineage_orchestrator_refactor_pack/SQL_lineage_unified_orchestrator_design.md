# SQL 血缘项目：CTE / 非 CTE 链路进一步统一改造设计文档

## 1. 背景

当前 `POST /api/sql/analyze` 的链路已经比早期版本更合理：

```text
parse_sql
→ complex_sql_guard
→ extract_output_fields_from_tree
→ CTE / 非 CTE 分支
→ structure graph
→ name_resolver
→ column lineage graph
→ source_location_service
→ assemble_result
```

opencode 已经做了一个重要改进：**CTE 分支也开始接入 metadata、name_resolver、column_lineage_graph 和 source_location_service**。

这一步是正确的，因为它解决了早期 CTE 只有结构依赖图、没有最终输出字段血缘的问题。

但当前链路仍然有一个结构性问题：

```text
仍然以 _looks_like_cte() 作为大分支开关。
```

这会导致后续复杂 SQL 持续分裂成两套逻辑。

---

## 2. 核心结论

### 2.1 当前方向是否合理

合理，但只算阶段性改造。

当前方案可以保留：

```text
CTE SQL:
  analyze_cte_structure
  load metadata
  resolve_column_lineage_names(..., CTE context)
  build_cte_structure_graph
  build_column_lineage_graph

非 CTE SQL:
  analyze_table_structure
  load metadata
  resolve_column_lineage_names(...)
  build_table_structure_graph
  build_column_lineage_graph
```

但它不应该成为长期架构。

### 2.2 是否需要进一步合并

需要。

但合并目标不是把所有 Service 合并成一个巨型函数，而是：

```text
合并 Controller / Orchestrator 的编排逻辑；
保留 Service 层的职责拆分。
```

最终目标：

```text
parse_sql
→ analyze_query_structure
→ load_metadata(physical_tables)
→ resolve_column_lineage_names(context)
→ build_structure_graphs
→ build_column_lineage_graph
→ merge_graphs
→ build_source_locations(graph nodes)
→ assemble_result
```

---

## 3. 为什么不能继续用 CTE / 非 CTE 双分支

### 3.1 CTE 不是 SQL 类型，而是 SQL 特征

错误理解：

```text
SQL = CTE SQL 或 非 CTE SQL
```

正确理解：

```text
SQL 可能同时包含：
- CTE 定义
- CTE 引用
- 物理表引用
- 子查询
- Join
- 最终 Select
- Union
```

例如：

```sql
with order_base as (
    select order_id, user_id
    from dwd_order_di
)
select
    ob.order_id,
    u.user_name
from order_base ob
join dim_user u on ob.user_id = u.user_id
```

它同时包含：

| 元素 | 示例 |
|---|---|
| CTE 定义 | `order_base as (...)` |
| CTE 内物理表 | `dwd_order_di` |
| 最终查询 CTE 引用 | `from order_base ob` |
| 最终查询物理表 Join | `join dim_user u` |
| 最终输出字段 | `ob.order_id`, `u.user_name` |

因此不应该用 `_looks_like_cte()` 决定整条链路。

---

## 4. 推荐目标架构

## 4.1 统一主流程

```text
POST /api/sql/analyze
  │
  ▼
① parse_sql(sql, dialect, options)
  ├─ complex_sql_guard
  ├─ extract_output_fields_from_tree(tree)
  └─ ParseServiceResult(tree, output_fields, diagnostics)
  │
  ▼
② analyze_query_structure(tree)
  ├─ cte_names
  ├─ physical_table_names
  ├─ final_select_source_names
  ├─ has_cte
  ├─ has_subquery
  ├─ structure_nodes
  ├─ structure_edges
  └─ diagnostics
  │
  ▼
③ load_metadata(structure.physical_table_names)
  └─ 注意：只加载物理表，不加载 CTE 名
  │
  ▼
④ resolve_column_lineage_names(tree, metadata, context)
  ├─ context.cte_names
  ├─ context.final_select_source_names
  ├─ context.physical_table_names
  ├─ context.resolve_scope
  └─ SimpleColumnLineage[] + diagnostics
  │
  ▼
⑤ build graphs
  ├─ if has_cte: build_cte_structure_graph()
  ├─ if no cte or direct physical table final query: build_table_structure_graph()
  └─ always: build_column_lineage_graph()
  │
  ▼
⑥ merge_graphs("lineage", *graphs) + validate_graph()
  │
  ▼
⑦ source_location_service.build_source_locations(sql, target_entities_from_graph)
  └─ output_column / physical_table / cte
  │
  ▼
⑧ assemble_result()
```

## 4.2 保留的 Service 边界

| 模块 | 是否合并 | 原因 |
|---|---:|---|
| `sql_parse_service.py` | 不合并 | parse 是独立阶段 |
| `complex_sql_guard` | 不合并 | 防御性 SQL 解析引擎应该保持独立 |
| `cte_structure_service.py` | 暂不合并 | CTE 结构依赖逻辑有独立价值 |
| `table_structure_service.py` | 暂不合并 | 物理表结构图逻辑简单稳定 |
| `name_resolver.py` | 不合并 | 字段归属、别名解析、metadata 消歧是核心领域逻辑 |
| `graph_builder.py` | 不合并 | 图组装必须独立 |
| `source_location_service.py` | 不合并 | SQL 文本定位必须独立于血缘推导 |

需要合并的是：

```text
analyze_controller 里的 CTE/非 CTE 两套编排逻辑。
```

---

## 5. 核心新增模型

## 5.1 QueryStructureResult

用于统一承载 SQL 结构信息。

```python
@dataclass
class QueryStructureResult:
    has_cte: bool
    has_subquery: bool
    cte_names: set[str]
    physical_table_names: set[str]
    final_select_source_names: set[str]
    diagnostics: list[Any]
```

职责：

| 字段 | 说明 |
|---|---|
| `has_cte` | SQL 是否包含 WITH CTE |
| `has_subquery` | SQL 是否包含子查询 |
| `cte_names` | CTE 定义名集合 |
| `physical_table_names` | 物理表集合，必须排除 CTE 名 |
| `final_select_source_names` | 最外层 SELECT 的 FROM/JOIN 来源名 |
| `diagnostics` | 结构分析阶段产生的诊断 |

## 5.2 LineageResolveContext

替代 `is_cte_context=True`。

```python
@dataclass
class LineageResolveContext:
    cte_names: set[str]
    final_select_source_names: set[str]
    physical_table_names: set[str]
    resolve_scope: Literal["full_query", "final_select"]
    allow_cte: bool = False
    allow_subquery: bool = False
```

为什么不能长期使用布尔值：

```text
is_cte_context=True 只能表达“是否 CTE”；
但 name_resolver 实际需要知道：
- 哪些名字是 CTE
- 哪些名字是物理表
- 当前解析范围是 full query 还是 final select
- 是否允许子查询
- 是否允许 CTE 引用
```

---

## 6. 字段血缘能力边界

当前阶段不要直接宣称支持完整 CTE 端到端字段血缘。

### 6.1 当前推荐支持能力

```text
CTE 结构级血缘：
physical_table → cte → query_result

CTE 最后一跳字段血缘：
cte_alias.column → output_column
```

示例：

```sql
with order_base as (
    select order_id, user_id
    from dwd_order_di
)
select order_id as order_no
from order_base
```

当前可接受输出：

```text
structure:
dwd_order_di → order_base → query_result:final

column lineage:
order_base.order_id → output_column:order_no
```

暂不强制要求：

```text
dwd_order_di.order_id → order_base.order_id → output_column:order_no
```

### 6.2 API capability 建议

```json
{
  "capabilities": {
    "cte_structure_lineage": true,
    "cte_final_select_column_lineage": true,
    "cte_end_to_end_column_lineage": false
  }
}
```

---

## 7. SourceLocation 改造边界

### 7.1 入参改造

旧方式：

```python
build_source_locations(sql, output_column_names)
```

新方式：

```python
build_source_locations(sql, target_entities)
```

其中 `target_entities` 来自最终 graph nodes，而不是 source_location_service 自己发明。

### 7.2 支持节点类型

| 节点类型 | entity_id 示例 | SQL 文本位置 |
|---|---|---|
| 输出列 | `output_column:order_no` | SELECT 列 |
| 物理表 | `physical_table:dwd_order_di` | FROM/JOIN 后表名 |
| CTE | `cte:order_base` | WITH 定义名 |
| Query Result | `query_result:final` | 无，不生成 |

### 7.3 返回字段建议

```json
{
  "entityId": "physical_table:dwd_order_di",
  "entityType": "physical_table",
  "rawText": "dwd_order_di",
  "startLine": 3,
  "startCol": 6,
  "endLine": 3,
  "endCol": 18,
  "startOffset": 42,
  "endOffset": 54,
  "role": "from",
  "rangeType": "exact",
  "origin": "regex",
  "confidenceLevel": "medium"
}
```

### 7.4 必须规避误匹配

正则扫描前必须 mask：

```text
字符串字面量
单行注释
多行注释
```

否则会误匹配：

```sql
select 'from fake_table' as txt
-- join fake_table
/* from another_fake */
from real_table
```

---

## 8. 关键实现步骤

## Step 1：新增 `query_structure_service.py`

目标：

```text
从 AST 中统一提取：
- CTE 名
- 物理表名
- 最外层 SELECT 的来源名
- 是否包含子查询
```

输出：`QueryStructureResult`。

## Step 2：新增 `LineageResolveContext`

目标：替换 `is_cte_context=True`。

## Step 3：改造 `name_resolver.py`

目标：

```text
resolve_column_lineage_names(..., context=None)
```

要求：

```text
1. 保持旧调用兼容。
2. 当 context.resolve_scope == "final_select" 时，只解析最终 SELECT 输出字段。
3. metadata 消歧只能使用 physical_table_names。
4. final_select_source_names 中如果包含 CTE，则允许生成 cte.column → output_column。
```

## Step 4：改造 `analyze_controller.py`

目标：去掉大段 `_looks_like_cte()` 分支。

新流程：

```python
parse_result = parse_sql(...)
structure = analyze_query_structure(parse_result.tree)
metadata = _load_metadata(structure.physical_table_names)
lineage = resolve_column_lineage_names(tree, metadata, context)
graphs = build_graphs_by_structure(structure, lineage)
graph = merge_graphs("lineage", *graphs)
source_locations = build_source_locations(sql, extract_targets_from_graph(graph))
return assemble_result(...)
```

## Step 5：改造 `source_location_service.py`

目标：支持 `output_column / physical_table / cte`。

要求：

```text
1. source_location_service 不自己发明 entityId。
2. target_entities 必须来自 graph nodes。
3. query_result:final 不生成位置。
4. 同一个 entityId 支持多个 occurrences。
5. 返回 offset + line/col。
```

## Step 6：补充回归测试

必须覆盖：

```text
非 CTE 单表
非 CTE Join
CTE 结构图
CTE 最后一跳字段血缘
CTE 名不查 metadata
CTE + Join 最终选择
SourceLocation: physical_table
SourceLocation: cte
SourceLocation: 注释/字符串不误匹配
```

---

## 9. 验收标准

| 编号 | 验收项 | 标准 |
|---|---|---|
| A1 | 原有 C00-C10 测试 | 全部通过 |
| A2 | Controller 分支 | 不再以 `_looks_like_cte()` 作为两套大流程分支 |
| A3 | Metadata 加载 | 只加载物理表，不加载 CTE 名 |
| A4 | CTE 结构图 | `physical_table → cte → query_result` 保留 |
| A5 | CTE 最后一跳字段血缘 | `cte.col → output_column` 可生成 |
| A6 | 非 CTE 字段血缘 | 单表 / Join 原有能力不回归 |
| A7 | SourceLocation | output_column / physical_table / cte 可定位 |
| A8 | SourceLocation 防误匹配 | 字符串和注释中的 from/join/with 不匹配 |
| A9 | Capability | 明确标记 `cte_end_to_end_column_lineage=false` |
| A10 | 代码边界 | 不把 parse/name_resolver/graph/source_location 合并成巨型函数 |

---

## 10. 不建议做的事情

### 10.1 不建议把 `cte_structure_service.py` 和 `table_structure_service.py` 立刻合并

短期收益不大，风险较高。

可以后续演进为：

```text
query_structure_service.py
  → structure graph builder
```

但当前阶段建议先只统一 controller 编排。

### 10.2 不建议立即做完整 CTE 端到端字段血缘

完整链路：

```text
physical_table.column
→ cte1.column
→ cte2.column
→ output_column
```

需要：

```text
每个 CTE 内部 select item 的字段血缘
CTE 输出字段 schema
CTE alias 到内部字段映射
跨 CTE rollup
```

这应该放到后续 `lineage_rollup_service` 完成，不应混入本次改造。

### 10.3 不建议 source_location_service 直接重新解析 SQL 语义

它只负责文本定位，不负责判断血缘。

---

## 11. 最终建议

本次进一步改造的核心不是“功能变多”，而是把后端分析链路变成稳定可扩展的形态：

```text
统一结构分析
统一元数据加载
统一字段血缘解析入口
统一图谱合并
统一 SourceLocation 目标生成
```

保留模块职责，合并编排逻辑。

这是后续继续做复杂 SQL、CTE 内字段 rollup、表达式血缘、口径分析、SourceLocation 精准联动的前提。
