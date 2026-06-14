# Golden Case: intl_ab_metric_cte_001

## 用例目标

验证复杂 AB 指标 SQL 下的 CTE 递归列级血缘穿透。

## 覆盖能力

- 多层 CTE
- CTE join CTE
- 聚合指标
- 比率表达式
- `count distinct case when ... then ... end`
- `select *` 子查询
- map access / array function / nvl / split
- 中文别名输出字段

## 建议验收字段

```text
单UV收益
S2D
S2O
搜索点击率_pv
搜索预定率_pv
订单ADR
曝光ADR
曝光与订单adr_gap
```

## 当前 expected 文件说明

`expected_root_lineage_sample.json` 是烟测级样例，不是全量列级血缘枚举。

第一版实现时，只要这些关键输出字段的根字段集合稳定识别，即可证明：

```text
final select → search_result/order_result → search_list/order_detail → 物理表
```

这条递归链路已经打通。
