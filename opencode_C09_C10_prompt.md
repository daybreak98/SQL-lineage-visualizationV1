# 交给 opencode 的开发提示词：C09-C10 实现

你现在在一个 SQL 血缘可视化项目中开发。请参考我提供的压缩包 `c09_c10_design_core_code.zip`，只实现 C09-C10，不要扩展到 AI、MCP、Text-to-SQL、复杂语义层。

## 背景

项目当前已经做到 C08：字段血缘图应表达：

```text
physical_column -> output_column -> query_result:final
```

C08 已经要求后端 graph_builder.py 补充 `query_result:final` 和 `output_column_to_result` 边；前端 graphPipeline.ts 需要把 `output_column_to_result` 映射为 output，并在 Column 视图中展示 Query Result。

## 本轮目标

### C09：表达式依赖与口径详情面板

实现：

```text
1. 后端识别 SELECT 输出表达式依赖。
2. 对 sum/count/count distinct/除法等常见表达式生成 expression node。
3. 生成 expression_dependency 边：source column -> expression。
4. 生成 expression_to_output 边：expression -> output_column。
5. 响应增加 semantics_report.metrics。
6. 前端 DetailPanel 点击 output 或 expression 节点后，展示字段名、表达式、依赖字段、聚合函数、诊断信息。
```

示例 SQL：

```sql
select
  sum(order_amount) as gmv,
  count(distinct order_no) as order_cnt,
  sum(order_amount) / count(distinct order_no) as adr
from dwd_order_di;
```

期望：

```text
gmv depends_on 包含 order_amount，aggregate_functions 包含 SUM
order_cnt depends_on 包含 order_no，aggregate_functions 包含 COUNT_DISTINCT
adr depends_on 包含 order_amount/order_no，operators 包含 DIV
```

### C10：Golden Case 回归冻结

实现：

```text
1. 建立 backend/tests/golden_cases 目录。
2. 每个 case 包含 input.sql、metadata.json、options.json、expected.min.json、README.md。
3. 新增 pytest，遍历 golden case，调用现有 analyze API 或 analyze service。
4. 断言 must_have_nodes、must_have_edges、must_have_metrics、forbidden_diagnostics。
5. 增加 no_dangling_edges 不变量，保证所有 edge.source / edge.target 都能在 nodes 中找到。
```

## 参考文件

请优先阅读压缩包中的：

```text
docs/C09_设计方案.md
docs/C10_设计方案.md
backend/app/services/expression_analyzer.py
backend/app/services/graph_builder_c09_patch.py
backend/app/models/semantics_models.py
backend/tests/test_expression_analyzer_c09.py
backend/tests/golden/test_c10_golden_cases.py
frontend/src/types/analysis.c09.ts
frontend/src/components/DetailPanel.c09.tsx
frontend/src/graphPipeline.c09.patch.ts
golden_cases/c09_metric_expression_basic/*
golden_cases/c08_query_result_final/*
```

## 开发要求

```text
1. 不要直接整包覆盖项目，必须结合当前项目结构合并。
2. 不要接 AI，不要接 LLM，不要生成脱离 SQL 证据的解释。
3. 不要破坏 C08 的 output_column -> query_result:final 链路。
4. 不要删除已有测试来通过本轮。
5. 不要大规模重构前后端，只做 C09-C10 必要改动。
6. 如果当前模型字段名不同，请保持外部 API 契约稳定，并在内部做适配。
7. diagnostics 不能被吞掉；解析失败或部分支持必须如实返回。
```

## 后端落地建议

```text
1. 新增或合并 ExpressionAnalyzer。
2. 在 analyze pipeline 中，在已有 output_fields / lineage_result 生成后调用 ExpressionAnalyzer。
3. 尽量复用现有 NameResolver 的字段归属结果，避免直接猜测字段来源。
4. 把 metrics 写入 AnalysisResult.semantics_report.metrics。
5. 在 GraphBuilder 中为 metrics 补 expression node / expression_dependency / expression_to_output。
6. 保留 C08 的 output_column_to_result。
7. 增加 no dangling edge 测试。
```

## 前端落地建议

```text
1. 扩展 AnalysisResult 类型，增加 semantics_report。
2. graphPipeline 支持 expression node、expression_dependency、expression_to_output。
3. Column 视图允许展示 expression 节点。
4. DetailPanel 点击 output_field 时按 metric.name 或 entity_id 匹配 semantics_report.metrics。
5. DetailPanel 点击 expression 时优先读 node.data.expression。
6. semantics_report 缺失时不能崩溃。
```

## 必须通过的测试

```bash
cd backend
pytest tests/test_expression_analyzer_c09.py -q
pytest tests/golden/test_c10_golden_cases.py -q
pytest tests/integration -q

cd frontend
npm test -- --run
```

如果当前项目还没有完全对应的测试目录，请创建最小版本，但不要跳过测试。

## 验收口径

```text
1. 后端返回 semantics_report.metrics。
2. graph_view_model 中 expression 节点和表达式边不悬空。
3. C08 的 query_result:final 仍然显示。
4. DetailPanel 能显示表达式、依赖字段、聚合函数。
5. C10 golden case 能防止 C03-C09 核心能力回退。
```
