# CTE 递归列级血缘穿透改造交付包

本压缩包面向 `SQL 血缘解析工作台` 的后端改造，目标是让当前“一跳字段血缘”升级为：

```text
最终输出字段
  ← search_result/order_result 字段
  ← search_list/order_detail/ab_rule 等 CTE 字段
  ← 物理根表字段
```

## 交付内容

```text
sql_lineage_cte_rollup_delivery/
  README.md
  docs/
    01_design.md                         # 设计方案
    02_sql_case_lineage_analysis.md       # 基于上传 SQL 的血缘重点拆解
    03_opencode_prompt.md                 # 可直接交给 opencode 的开发提示词
  src/lineage_cte_rollup/
    models.py                             # 核心领域模型
    lineage_adapter.py                    # 兼容旧 SimpleColumnLineage 的适配层
    cte_column_rollup_service.py           # 递归穿透核心 DFS 逻辑
    derived_relation_schema_builder.py     # CTE / 子查询 schema 构建骨架
    expression_dependency_extractor.py     # 表达式字段依赖抽取骨架
    orchestrator_integration.py            # 编排集成示例
    __init__.py
  patches/
    integration_patch.md                   # 建议修改点与伪 diff
  tests/
    test_cte_column_rollup_service.py      # 纯 Python 单测，不依赖 sqlglot
  golden_cases/intl_ab_metric_cte/
    input.sql                              # 本次上传的复杂 SQL
    expected_root_lineage_sample.json      # 关键输出字段样例期望血缘
    README.md                              # Golden Case 说明
```

## 核心结论

这条 SQL 不是简单 CTE 投影，它同时覆盖：

- 多层 CTE：`order_90 → no_user → search_list/order_detail → search_result/order_result → final select`
- 聚合指标：`count distinct`、`sum`、`avg`、分子分母比率
- 表达式指标：`cast`、`concat`、`round`、`case when`、`map access`、`split`、`nvl`
- join 派生字段：`ab_rule left join search_list/order_detail`
- `select *` 派生 CTE：`product`、`search_result`/`order_result` 内部子查询都涉及 `select *`

因此本次改造不建议继续用 `SimpleColumnLineage` 的单点 while 展开，而应该新增内部 `ColumnDependency` 多输入模型；对外可以继续兼容旧的 `SimpleColumnLineage[]`。

## 推荐落地顺序

1. 先合入 `models.py` 与 `cte_column_rollup_service.py`。
2. 用 `lineage_adapter.py` 把旧 `SimpleColumnLineage[]` 转为 `ColumnDependency[]`。
3. 在 orchestrator 中新增 `immediate_lineage`、`root_lineage`、`lineage_paths` 三份产物。
4. 先用 `expected_root_lineage_sample.json` 做小范围回归。
5. 后续再补表达式级 SourceLocation、完整函数语义、复杂窗口函数。
