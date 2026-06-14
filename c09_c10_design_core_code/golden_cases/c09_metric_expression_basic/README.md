# c09_metric_expression_basic

## 目标

验证 C09 的表达式依赖与 semantics_report.metrics。

## 覆盖点

```text
sum(order_amount) as gmv
count(distinct order_no) as order_cnt
sum(order_amount) / count(distinct order_no) as adr
```

## 必须保证

```text
1. gmv 依赖 order_amount。
2. order_cnt 依赖 order_no。
3. adr 同时依赖 order_amount 和 order_no。
4. expression_dependency / expression_to_output 不悬空。
5. C08 的 output_column -> query_result:final 链路仍然存在。
```
