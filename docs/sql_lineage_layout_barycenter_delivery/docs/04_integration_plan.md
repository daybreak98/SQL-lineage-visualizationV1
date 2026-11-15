# 集成方案

## 1. 建议新增模块

```text
backend/services/graph_layout_planner.py
backend/services/graph_crossing_minimizer.py
backend/domain/graph_layout_models.py
```

如果当前项目已经有 `graph_builder.py`，则不要把算法直接塞进去，建议保持：

```text
GraphBuilder：LineageIR -> GraphViewModel raw nodes/edges
GraphLayoutPlanner：GraphViewModel raw -> GraphViewModel with layout hints
```

## 2. AnalysisOrchestrator 集成点

```python
class AnalysisOrchestrator:
    def analyze(self, request):
        parse_result = self.sql_parse_service.parse(request.sql)
        lineage_ir = self.lineage_engine.resolve(parse_result)
        graph = self.graph_builder.build(lineage_ir)
        graph = self.graph_layout_planner.plan(graph)
        return self.result_builder.build(lineage_ir=lineage_ir, graph=graph)
```

## 3. GraphViewModel 字段扩展

Node 建议新增：

```json
{
  "rank": 3,
  "order_in_rank": 0,
  "lane": "search_branch",
  "semantic_role": "aggregate_cte",
  "cluster_id": "cluster:search_branch",
  "position": {"x": 1440, "y": 120},
  "layout_locked": false
}
```

Graph 建议新增：

```json
{
  "layout_hint": {
    "algorithm": "semantic-layered-barycenter",
    "direction": "LR",
    "rank_gap": 360,
    "node_gap": 96,
    "crossing_minimization": "weighted_barycenter_sweep",
    "preserve_sql_order_within_group": true
  }
}
```

## 4. 前端接入边界

前端不要重新推断 SQL 语义，只做像素渲染：

```text
x = rank * rank_gap
y = lane_offset + order_in_rank * node_gap
```

如果用户拖拽：

```text
GraphInteractionState.node_positions[node_id] 覆盖后端 position
```

不要反写 GraphViewModel。

## 5. 兼容策略

如果旧接口没有 rank/lane：

```text
rank = 0
lane = default
order_in_rank = 原 nodes 顺序
```

这样不会破坏现有前端。

## 6. 回归测试

至少增加：

1. `search_result` 主导指标靠近 `search_result`；
2. `order_result` 主导指标靠近 `order_result`；
3. mixed 指标位于二者之间；
4. 组内保留 SQL 顺序；
5. 用户已有位置不被后端 layout 覆盖。
