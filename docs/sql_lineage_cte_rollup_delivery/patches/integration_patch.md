# 集成补丁说明

## 1. 新增文件

```text
services/cte_column_rollup_service.py
services/derived_relation_schema_builder.py
services/expression_dependency_extractor.py
models/column_dependency.py
```

可以先把本包 `src/lineage_cte_rollup/*.py` 内容复制到项目对应目录，再按项目命名调整 import。

## 2. Orchestrator 修改点

原链路可能类似：

```python
parse_result = parse_sql(sql, dialect, options)
lineage = resolve_column_lineage_names(parse_result.tree, ...)
graph = build_graph(lineage)
```

建议改成：

```python
parse_result = parse_sql(sql, dialect, options)

scope = scope_resolver.resolve(parse_result.tree)

cte_schema_result = derived_relation_schema_builder.build_from_ordered_ctes(
    ordered_ctes=scope.ordered_ctes,
)

immediate_dependencies = dependency_resolver.resolve_select_dependencies(
    select_node=scope.final_select,
    output_relation_name="final",
    derived_schemas=cte_schema_result.schemas,
)

rollup_result = cte_column_rollup_service.rollup(immediate_dependencies)

graph = graph_builder.build(
    root_lineage=rollup_result.root_dependencies,
    immediate_lineage=immediate_dependencies,
    lineage_paths=rollup_result.lineage_paths,
)
```

## 3. API 响应建议

原响应：

```json
{
  "column_lineage": []
}
```

兼容增强：

```json
{
  "column_lineage": [],
  "immediate_column_lineage": [],
  "root_column_lineage": [],
  "lineage_paths": [],
  "diagnostics": []
}
```

如果短期不想改前端：

```text
column_lineage 继续放 root_column_lineage 的扁平结果
immediate_column_lineage / lineage_paths 作为新增可选字段
```

## 4. NameResolver 修改点

NameResolver 需要支持：

```python
resolve_select_dependencies(select_node, output_relation_name, derived_schemas)
```

其中：

- 遇到 `from search_result a`，如果 `search_result` 在 `derived_schemas` 中，则 alias `a` 的 relation_kind 是 `cte`。
- 遇到物理表，则 relation_kind 是 `table`。
- 遇到字段 `a.show_uv`，输出 `ColumnRef("search_result", "show_uv", "cte", table_alias="a")`。
- 遇到无表别名字段，使用当前 scope 和元数据消歧；无法消歧则返回 diagnostic。

## 5. GraphBuilder 修改点

GraphBuilder 不要自己递归 CTE。它只消费已经准备好的结果：

```python
build_graph(root_dependencies, lineage_paths=None, view_mode="root")
```

建议图谱模式：

| view_mode | 说明 |
|---|---|
| `root` | 默认，只展示物理根表字段到最终输出字段 |
| `path` | 展示 CTE 中间路径 |
| `immediate` | 只展示最终 SELECT 一跳血缘，便于调试 |

## 6. 关键回归点

必须覆盖：

```text
output:单UV收益 ← order_result.total_order_commission + search_result.show_uv
output:S2D ← search_result.click_uv + search_result.show_uv
output:订单ADR ← order_result.order_adr ← order_detail.init_gmv + order_detail.room_night
```
