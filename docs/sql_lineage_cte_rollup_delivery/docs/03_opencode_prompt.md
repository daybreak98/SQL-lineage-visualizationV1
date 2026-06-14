# 给 opencode / Codex 的开发提示词

你将基于现有 SQL 血缘解析项目做一次后端增强：实现 CTE / 子查询派生字段的递归列级血缘穿透。

## 背景

当前项目已经能解析最终 SELECT 的一跳字段血缘，例如：

```text
search_result.show_uv → output:S2D
order_result.total_order_commission → output:单UV收益
```

但复杂 SQL 中存在多层 CTE，目标是继续穿透到物理根表字段：

```text
mdw_order_v3_international.init_commission_after → order_detail.order_commission → order_result.total_order_commission → output:单UV收益
```

## 目标

实现以下能力：

1. 新增内部模型 `ColumnRef`、`ColumnDependency`、`DerivedRelationSchema`、`LineagePath`。
2. 新增 `CteColumnRollupService`，对 CTE / 子查询字段做 DFS 递归展开。
3. 对外保持现有接口兼容，不破坏 `/api/sql/analyze`。
4. 在 AnalysisResult 中新增或预留：
   - `immediate_column_lineage`
   - `root_column_lineage`
   - `lineage_paths`
5. 支持一个输出字段依赖多个输入字段。
6. 支持聚合/表达式字段依赖抽取的最小闭环。
7. 递归循环、字段找不到、select * 无元数据时返回 diagnostic，不直接崩溃。

## 参考代码

请参考本交付包：

```text
src/lineage_cte_rollup/models.py
src/lineage_cte_rollup/cte_column_rollup_service.py
src/lineage_cte_rollup/lineage_adapter.py
src/lineage_cte_rollup/orchestrator_integration.py
```

## 修改建议

优先修改后端：

```text
services/cte_column_rollup_service.py       新增
services/derived_relation_schema_builder.py 新增或按现有 resolver 封装
services/expression_dependency_extractor.py 新增或增强现有 name_resolver
models/lineage_models.py                    新增内部依赖模型
application/analysis_orchestrator.py        接入 rollup
```

不要把 rollup 写到 controller 中。Controller 只负责入参和响应。

## 核心验收 SQL

使用：

```text
golden_cases/intl_ab_metric_cte/input.sql
```

至少验收以下最终输出字段：

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

## 必须通过的单测

先运行：

```bash
pytest tests/test_cte_column_rollup_service.py
```

该测试不依赖 sqlglot，只验证 DFS 递归穿透、多输入依赖、循环防护、缺失 schema 降级。

## 开发注意事项

1. 不要用 `while source_table in cte_schemas` 处理单链血缘，必须使用 DFS。
2. 不要假设一个输出字段只有一个来源。
3. 不要把 CTE 名、表名、表别名混为一个字符串，模型里必须有 `relation_kind`。
4. 表达式字段可以先只抽取内部出现的 Column，不要求理解所有函数语义。
5. 对 `count(distinct case when ... then col end)`，至少需要提取 `col` 以及 case 条件字段。
6. `select *` 第一版可以依赖元数据展开；无元数据时返回 partial diagnostic。
7. GraphBuilder 默认使用 root lineage，但应保留 lineage path 用于调试和前端展开。
