# C15 血缘图 Barycenter 布局与边重叠优化说明

## 本轮目标

减少复杂血缘图中边互相覆盖、交叉后难以阅读的问题。核心思路不是单纯调整线条样式，而是在后端为图增加稳定的布局语义，再由前端把这些语义渲染成像素位置和端口分流。

## 开发路径

1. 后端新增布局领域模型：
   - `LayoutNode`
   - `LayoutEdge`
   - `LayoutConfig`
   - `LayoutResult`

2. 后端新增布局服务：
   - `GraphLayoutPlanner`
   - `CrossingMinimizer`
   - `PortOrderOptimizer`
   - `SemanticLayerAssigner`
   - `LaneAssigner`

3. `graph_builder.merge_graphs()` 在合并 raw graph 后统一调用 `GraphLayoutPlanner`。

4. `GraphViewModel` 兼容扩展以下字段：
   - 节点：`rank`、`lane`、`semantic_role`、`order_in_rank`、`position`
   - 边：`source_port_order`、`target_port_order`
   - 图：`layout_hint`

5. 前端消费后端布局提示：
   - 如果所有节点都有 `rank`，优先按后端 rank 分层。
   - 如果所有节点都有 `order_in_rank`，优先按后端层内顺序排列。
   - 如果边有 `source_port_order` / `target_port_order`，优先用端口顺序分流，而不是只按节点 y 坐标排序。

## 初学者理解

原来的图只告诉前端“哪些节点相连”。前端需要自己猜节点应该放在哪一列、同一列谁在上谁在下，所以复杂 SQL 下容易出现大量边交叉。

本轮之后，后端会额外告诉前端：

- 这个节点属于第几层：`rank`
- 同一层里排第几个：`order_in_rank`
- 这条边应该从源节点第几个端口出去：`source_port_order`
- 这条边应该从目标节点第几个端口进入：`target_port_order`

这样前端不再盲猜布局，而是按后端稳定结果渲染，边会更有秩序地分散开。

## 依赖层级保护

语义分层只作为 rank 下限，不能覆盖真实依赖关系。例如两个 CTE 都可能被识别成 base/enrich，但只要存在 `cte_a -> cte_b`，最终布局就必须满足：

```text
rank(cte_a) < rank(cte_b)
```

本轮增加了依赖 rank 松弛逻辑：planner 会沿所有边反复推进目标节点 rank，保证任意有效边都从左侧层级指向右侧层级。这样可以避免依赖节点被放在同一列，保留血缘图的拓扑含义。

## 验证结果

- 后端布局与 C03 集成测试：`14 passed`
- 后端完整测试：`156 passed, 1 warning`
- 前端图相关测试：`33 passed`
- 前端完整测试：`101 passed, 1 skipped`
- 前端类型检查：通过
- 前端生产构建：通过
- API 抽样：返回 `semantic-layered-barycenter`，节点包含 `rank/order_in_rank`，边包含端口序号。

说明：第一次 `tsc --noEmit` 使用默认 Node 内存时出现 OOM，随后通过 `NODE_OPTIONS=--max-old-space-size=4096` 重跑通过。
