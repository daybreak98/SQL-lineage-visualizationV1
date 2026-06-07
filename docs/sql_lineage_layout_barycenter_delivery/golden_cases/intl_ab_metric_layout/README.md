# Golden Case：intl_ab_metric_layout

## 目的

验证复杂 AB 指标 SQL 的血缘图布局是否能把主链路分清楚：

```text
search_result -> 搜索类指标
order_result  -> 订单类指标
search_result + order_result -> 混合指标
```

## 关键 SQL 特征

- 多层 CTE；
- `search_list` / `order_detail` 明细增强；
- `search_result` / `order_result` 聚合 CTE；
- 最终 SELECT 输出大量中文指标；
- `单UV收益`、`曝光与订单adr_gap` 是跨搜索与订单的混合指标。

## 期望

布局结果应满足：

1. `search_result` 和 `order_result` 位于 rank=3；
2. 最终输出字段位于 rank=4；
3. 搜索指标靠近 `search_result`；
4. 订单指标靠近 `order_result`；
5. 混合指标位于搜索指标与订单指标之间；
6. 同一来源组内保留 SQL 原始顺序。
