# 设计方案：Semantic Layered DAG Layout

## 1. 总体链路

```text
LineageIR / GraphViewModel
  -> GraphSemanticNormalizer
  -> SemanticLayerAssigner
  -> LaneAssigner
  -> CrossingMinimizer
  -> PortOrderOptimizer
  -> PositionAssigner
  -> GraphViewModel with layout
```

## 2. 分层规则 rank

| 节点类型 | rank | 示例 |
|---|---:|---|
| physical_table | 0 | `default.mdw_order_v3_international` |
| base_cte | 1 | `no_user`, `user_type`, `hotel_info`, `ab_rule` |
| enrich_cte | 2 | `search_list`, `order_detail`, `product` |
| aggregate_cte | 3 | `search_result`, `order_result`, `order_90` |
| output_column | 4 | `S2D`, `单UV收益`, `订单ADR` |

rank 是强约束，布局算法不允许随意改变。算法只决定同一 rank 内部的上下顺序。

## 3. 泳道规则 lane

建议第一版支持：

| lane | 说明 |
|---|---|
| search_branch | 搜索流量链路 |
| order_branch | 订单链路 |
| ab_branch | AB 分流链路 |
| dimension_branch | 维度增强链路 |
| shared_branch | 公共依赖链路 |
| mixed_branch | 同时服务多条主链路的节点 |

更严谨的 lane 不靠名称硬编码，而根据节点最终影响的 output_column 集合聚类。

## 4. 输出字段排序策略

最终输出字段不建议完全按 SQL 原始顺序摆放，而是：

```text
先按来源分组，再在组内保留 SQL 顺序。
```

示例：

```text
search_result 主导：
  S2D
  S2O
  搜索点击率_pv
  搜索预定率_pv
  搜索无结果率
  无库存流量占比
  TOP 命中率
  曝光ADR

mixed：
  单UV收益
  曝光与订单adr_gap

order_result 主导：
  订单ADR
```

## 5. 为什么不直接用 dagre / elk

通用布局库可以负责像素坐标，但不应该负责 SQL 语义判断。更好的边界是：

```text
后端：输出 rank/lane/order_in_rank/semantic_role
前端：按这些提示计算 x/y，必要时再交给 dagre/elk 微调
用户：拖拽后只覆盖前端 GraphInteractionState，不反写后端血缘事实
```

## 6. 默认折叠策略

复杂 SQL 默认不要展开所有字段：

| 视图 | 展示内容 |
|---|---|
| 全局骨架视图 | 表、CTE、聚合 CTE、输出字段组 |
| 字段聚焦视图 | 点击一个输出字段后只展开它的上游路径 |
| 调试视图 | 展开所有字段和中间依赖 |

布局算法应该优先保证骨架视图清楚，再逐步支持字段级展开。
