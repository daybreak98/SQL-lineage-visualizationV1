# 给 opencode 的开发提示词

你现在要在 SQL 血缘项目中继续改造 `POST /api/sql/analyze` 的后端链路。

## 目标

把当前 CTE / 非 CTE 两套大分支改造成统一 Orchestrator 编排。

重点：

```text
合并 analyze_controller 的编排逻辑；
不要把 parse、structure、name_resolver、graph_builder、source_location_service 合并成巨型函数。
```

## 当前问题

当前链路大致是：

```text
parse_sql
→ if _looks_like_cte():
      analyze_cte_structure
      _extract_source_table_names
      _load_metadata
      resolve_column_lineage_names(..., is_cte_context=True)
      build_cte_structure_graph
      build_column_lineage_graph
  else:
      analyze_table_structure
      _extract_source_table_names
      _load_metadata
      resolve_column_lineage_names(...)
      build_table_structure_graph
      build_column_lineage_graph
→ merge_graphs
→ source_location_service
→ assemble_result
```

问题是：CTE 不是 SQL 类型，而是 SQL 的一个结构特征。后续复杂 SQL 会同时包含 CTE、物理表、Join、子查询、最终 Select，不应该用 `_looks_like_cte()` 决定整条管道。

## 目标链路

改造为：

```text
parse_sql
→ analyze_query_structure(tree)
→ load_metadata(structure.physical_table_names)
→ resolve_column_lineage_names(tree, metadata, context)
→ build_structure_graphs(structure)
→ build_column_lineage_graph(lineage)
→ merge_graphs("lineage", *graphs)
→ build_source_locations(sql, target_entities_from_graph)
→ assemble_result
```

## 必须新增或调整的文件

### 1. 新增 `query_structure_service.py`

实现：

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

核心函数：

```python
analyze_query_structure(tree) -> QueryStructureResult
extract_cte_names(tree) -> set[str]
extract_physical_table_names(tree, cte_names: set[str]) -> set[str]
extract_final_select_source_names(tree) -> set[str]
```

要求：

```text
1. physical_table_names 必须排除 cte_names。
2. final_select_source_names 只取最外层 SELECT 的 FROM/JOIN 来源。
3. 不要在这里做字段血缘。
```

### 2. 新增或改造 `LineageResolveContext`

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

`resolve_column_lineage_names()` 支持 `context` 参数，并保持旧调用兼容。

### 3. 改造 `analyze_controller.py`

不要再用 `_looks_like_cte()` 分成两套大流程。

参考伪代码：

```python
parse_result = parse_sql(sql, dialect, options)
tree = parse_result.tree

structure = analyze_query_structure(tree)
metadata = _load_metadata(structure.physical_table_names)

context = LineageResolveContext(
    cte_names=structure.cte_names,
    final_select_source_names=structure.final_select_source_names,
    physical_table_names=structure.physical_table_names,
    resolve_scope="final_select" if structure.has_cte else "full_query",
    allow_cte=structure.has_cte,
    allow_subquery=False,
)

lineage_result = resolve_column_lineage_names(
    tree=tree,
    metadata=metadata,
    context=context,
)

graphs = []
if structure.has_cte:
    cte_structure = analyze_cte_structure(tree)
    graphs.append(build_cte_structure_graph(cte_structure))
else:
    table_structure = analyze_table_structure(tree)
    graphs.append(build_table_structure_graph(table_structure))

graphs.append(build_column_lineage_graph(lineage_result.lineages))

graph = merge_graphs("lineage", *graphs)
validate_graph(graph)

target_entities = extract_source_location_targets_from_graph(graph)
source_locations = build_source_locations(sql, target_entities=target_entities)

return _assemble_result(...)
```

### 4. 改造 `source_location_service.py`

新增支持：

| entity type | 示例 |
|---|---|
| output_column | `output_column:order_no` |
| physical_table | `physical_table:dwd_order_di` |
| cte | `cte:order_base` |

要求：

```text
1. source_location_service 不要自己发明 entityId。
2. target_entities 应来自 graph nodes。
3. query_result:final 不生成 location。
4. 正则扫描前 mask 字符串、单行注释、多行注释。
5. 返回 startLine/startCol/endLine/endCol/startOffset/endOffset/rawText/rangeType/origin/confidenceLevel。
6. 同一 entityId 支持多个 occurrences。
7. 保持旧 output_column_names 入参兼容。
```

## 能力边界

本次只要求：

```text
CTE 结构图：physical_table → cte → query_result
CTE 最后一跳字段血缘：cte.col → output_column
```

本次不强制实现：

```text
physical_table.col → cte1.col → cte2.col → output_column
```

如果 API 有 capabilities，请明确：

```json
{
  "cte_structure_lineage": true,
  "cte_final_select_column_lineage": true,
  "cte_end_to_end_column_lineage": false
}
```

## 测试要求

新增或确认以下测试：

1. 非 CTE 单表不回归。
2. 非 CTE Join 不回归。
3. CTE 结构图存在。
4. CTE 最后一跳字段血缘存在。
5. CTE 名不要查 metadata。
6. CTE + Join 最终选择可解析。
7. SourceLocation 支持 physical_table。
8. SourceLocation 支持 cte。
9. SourceLocation 不匹配字符串和注释里的 from/join/with。
10. 同一物理表出现两次时 occurrences 数量正确。

## 约束

1. 不要删除已有 C00-C10 测试。
2. 不要把 `complex_sql_guard` 合并进 controller。
3. 不要让 `source_location_service` 承担血缘推导职责。
4. 不要让 metadata 加载 CTE 名。
5. 不要把 CTE 最后一跳血缘冒充完整端到端血缘。
