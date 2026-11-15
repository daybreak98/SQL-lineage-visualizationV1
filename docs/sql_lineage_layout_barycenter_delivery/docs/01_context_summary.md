# 上下文总结：为什么要做血缘图布局规范化

## 背景

当前 SQL 血缘项目的最终目标不是只生成血缘明细，而是通过血缘图快速分析依赖关系。复杂 SQL 的血缘图可读性主要由“节点摆放”决定，而不是由边的曲线样式决定。

本轮讨论聚焦：

```text
如何通过语义分层、分支泳道、同层排序和字段端口排序，减少血缘图交叉？
```

## 参考 SQL 的典型结构

用户提供的 SQL 包含：

```text
order_90
no_user
user_type
hotel_info
ab_rule
product
search_list
order_detail
search_result
order_result
最终 SELECT 输出中文指标
```

其中：

- `search_result` 是搜索流量聚合结果；
- `order_result` 是订单聚合结果；
- 最终输出字段中，`S2D`、`S2O`、`搜索点击率_pv` 等主要依赖 `search_result`；
- `订单ADR` 主要依赖 `order_result`；
- `单UV收益`、`曝光与订单adr_gap` 同时依赖 `search_result` 和 `order_result`。

这类图如果按节点名称或 SQL 原始顺序简单排列，会导致大量交叉。

## 核心原则

```text
不要把血缘图当普通网络图布局。
应该把它当 SQL 语义分层 DAG 布局。
```

也就是：

```text
物理表
  -> 基础 CTE
    -> 明细增强 CTE
      -> 聚合 CTE
        -> 最终输出字段
```

## 本包要交付的能力

| 能力 | 作用 |
|---|---|
| SemanticLayerAssigner | 给节点分配 SQL 语义层级 rank 和角色 semantic_role |
| LaneAssigner | 给节点分配 search/order/ab/dim/shared 等泳道 |
| CrossingMinimizer | 使用 Barycenter / Median 减少同层交叉 |
| PortOrderOptimizer | 对节点内部字段排序，减少字段级边交叉 |
| GraphLayoutPlanner | 输出前端可消费的初始坐标和 layout_hint |

## 与已有工程文档的关系

已有文档已经强调：

1. GraphViewModel 与 GraphInteractionState 要拆分；
2. Stable Entity ID 是图谱折叠、定位和 diff 的基础；
3. 后端 GraphBuilder 只消费 LineageIR，不应污染 SQLGlot/SQLite 细节；
4. Golden Case 必须可回归。

本包是在这个基础上新增一个独立的 `GraphLayoutPlanner`，负责“布局语义规划”，不改动血缘事实本身。
