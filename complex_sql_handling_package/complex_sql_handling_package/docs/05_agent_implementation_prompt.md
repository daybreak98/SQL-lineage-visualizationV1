# 给 opencode / Agent 的实施提示词

你现在要在 SQL 血缘项目中实现“复杂 Hive/Spark 生产 SQL 容错处理层”。

## 项目背景

当前项目已经可以解析表级和子查询级血缘，下一步要推进字段血缘。生产 SQL 可能长达 1000 行，包含多层 CTE、多 join、lateral view/explode、复杂 regexp、JSONPath、单双引号、模板变量，但基本符合 Hive/Spark 语法。

## 本轮目标

不要直接重写血缘引擎。本轮只新增一个前置模块：`ComplexSqlAnalyzer`。

它负责：

```text
1. 保留 original_sql。
2. 生成 normalized_sql 和 analysis_sql。
3. 屏蔽复杂字符串、正则、JSONPath、模板变量。
4. 按顶层 SQL 结构分段。
5. 调用 sqlglot 尝试完整解析。
6. 完整解析失败时进入 segment-level partial 解析。
7. 返回结构化 diagnostics，而不是直接 failed。
```

## 必须遵守的边界

```text
1. 不允许直接修改 original_sql。
2. 不允许暴力 replace 单引号、双引号、正则内容。
3. 不允许因为 sqlglot parse 失败导致整个接口崩溃。
4. 不允许把 placeholder mapping 丢失。
5. 不允许把 ComplexSqlAnalyzer 和 LineageEngine 写死耦合。
```

## 推荐实现文件

```text
src/complex_sql_guard/
  models.py
  preflight.py
  shields.py
  segmenter.py
  dialect.py
  parser_adapter.py
  analyzer.py
```

## 验收命令

```bash
python -m unittest discover -s tests -v
python scripts/run_demo.py
```

## 输出要求

完成后给出：

```text
1. 新增/修改文件列表。
2. 核心实现说明。
3. 测试结果。
4. 当前不支持的语法清单。
5. 下一步如何接入 ScopeResolver / NameResolver / LineageEngine。
```
