# 给本地 Codex / opencode 的开发提示词

你将基于当前 SQL 血缘可视化项目实现“语义分层布局 + Barycenter / Median 同层排序”，目标是减少血缘图节点交叉，让复杂 SQL 的依赖走向更清晰。

## 背景

项目是 SQL 血缘解析工作台，后端以 Python + SQLGlot + SQLite 为核心，前端有 Monaco Editor 和血缘画布。已有 GraphBuilder / GraphViewModel 的基础能力。本次不是修改边样式，而是改进节点初始摆放。

## 目标

新增一个独立的布局规划模块：

```text
GraphLayoutPlanner
```

输入现有 GraphViewModel 的 nodes/edges，输出带布局语义的 GraphViewModel：

```json
{
  "rank": 3,
  "lane": "search_branch",
  "semantic_role": "aggregate_cte",
  "order_in_rank": 0,
  "position": {"x": 1080, "y": 240}
}
```

## 核心要求

1. 不要改变血缘事实，只补充布局字段。
2. 不要把逻辑写在 Controller 层。
3. 不要让前端自己猜 `search_result` / `order_result` 的语义。
4. 后端负责 rank/lane/order_in_rank，前端负责 x/y 渲染和拖拽覆盖。
5. 保持与旧 GraphViewModel 兼容。

## 推荐模块

```text
backend/domain/graph_layout_models.py
backend/services/graph_crossing_minimizer.py
backend/services/graph_layout_planner.py
backend/services/graph_port_order_optimizer.py
```

可直接参考本包 `src/sql_lineage_layout/` 中的实现。

## 算法要求

### 1. rank 固定分层

```text
physical_table -> 0
base_cte -> 1
enrich_cte -> 2
aggregate_cte -> 3
output_column -> 4
```

### 2. 同层排序

实现 Weighted Barycenter：

```text
score(node) = sum(position(neighbor) * edge_weight) / sum(edge_weight)
```

实现 Median 作为可选项：

```text
score(node) = median(position(neighbor))
```

### 3. 多轮 sweep

```text
left -> right
right -> left
重复 2~4 轮
```

### 4. 保留 SQL 顺序

排序 key 中必须保留 `sql_order` 作为 tie-breaker。

### 5. 字段端口排序

节点内部字段按其下游输出字段位置的 barycenter 排序。

## 验收用例

基于 `golden_cases/intl_ab_metric_layout/input.sql`，最终输出字段应大致聚集为：

```text
search_result 指标：S2D、S2O、搜索点击率_pv、搜索预定率_pv、搜索无结果率、无库存流量占比、TOP 命中率、曝光ADR
mixed 指标：单UV收益、曝光与订单adr_gap
order_result 指标：订单ADR
```

## 测试要求

新增单测：

1. `test_weighted_barycenter_orders_outputs_by_source`
2. `test_median_is_robust_to_outlier_dependency`
3. `test_sweep_preserves_sql_order_as_tie_breaker`
4. `test_port_order_follows_downstream_output_order`
5. `test_layout_planner_outputs_rank_lane_position`

## 不做

1. 不改线条样式；
2. 不做完整 ELK / Dagre 替换；
3. 不做前端持久化布局；
4. 不重新设计 GraphViewModel 契约，只做兼容扩展；
5. 不修改血缘解析结果本身。
