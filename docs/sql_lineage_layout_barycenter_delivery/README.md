# SQL 血缘图布局优化交付包：Semantic Layered DAG + Barycenter / Median

本包用于给本地 Codex / opencode 开发参考，目标是把 SQL 血缘图从“普通节点网络图”改为“SQL 语义分层 DAG”，通过节点摆放减少边交叉，让依赖走向更清楚。

## 解决的问题

复杂 SQL 的列级血缘图如果直接把节点交给通用布局算法，常见问题是：

1. 物理表、CTE、聚合结果、最终输出字段混在一起；
2. `search_result` / `order_result` 这类主分支上下穿插；
3. 公共依赖节点如 `ab_rule` 被拉到边缘；
4. 字段级边大量交叉；
5. 重新分析后节点位置不稳定。

本包实现的是布局前的数据规范化能力：

```text
LineageIR / GraphViewModel
  -> semantic rank/lane/cluster 标注
  -> 同层节点 Barycenter / Median 排序
  -> 字段端口 Port Ordering
  -> 前端可直接消费的 x/y position
```

## 推荐集成位置

```text
AnalysisOrchestrator
  -> LineageEngine
  -> GraphBuilder
  -> GraphLayoutPlanner  # 本包核心
  -> AnalysisResultBuilder
```

不要把布局语义塞进 Controller，也不要让前端自己猜 CTE 语义。后端输出 `rank/lane/order_in_rank/layout_hint`，前端负责像素渲染、拖拽覆盖和交互状态。

## 目录

```text
docs/
  01_context_summary.md
  02_design_semantic_layered_layout.md
  03_barycenter_median_algorithm.md
  04_integration_plan.md
  05_codex_prompt.md
  06_acceptance_checklist.md
src/sql_lineage_layout/
  models.py
  semantic_layering.py
  crossing_minimizer.py
  port_order_optimizer.py
  layout_planner.py
  graph_view_model_adapter.py
  demo_case.py
tests/
  test_crossing_minimizer.py
  test_layout_planner.py
  test_port_order_optimizer.py
golden_cases/intl_ab_metric_layout/
  input.sql
  expected_layout_summary.json
  README.md
examples/
  run_demo.py
```

## 本地运行

```bash
cd sql_lineage_layout_barycenter_delivery
python -m unittest discover -s tests -v
python examples/run_demo.py
```

## 最小落地目标

第一版只需要做到：

1. 固定 rank：物理表 -> 基础 CTE -> 明细增强 CTE -> 聚合 CTE -> 输出字段；
2. 对每一层执行 Weighted Barycenter sweep；
3. 保留 SQL 原始顺序作为 tie-breaker；
4. 输出字段按来源自然聚集：搜索指标、混合指标、订单指标；
5. GraphViewModel 中增加 `rank/lane/order_in_rank/semantic_role/layout_hint`；
6. 前端按 `rank/order_in_rank` 计算初始坐标，用户拖拽位置只在前端交互状态中覆盖。
