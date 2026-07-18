# 生产脏 SQL 血缘压测集

本目录承载 10 份可独立执行的 Spark SQL 血缘压测用例。每份文件是一个以 `WITH` 开始、以单条 `SELECT` 结束的查询，面向现有 SQL 血缘解析链路的回归验证。

## 静态准入契约

每份用例必须同时满足以下条件：

- 至少 300 个物理行；
- 至少 26 个具名关系（CTE、内联/标量子查询别名与物理表引用的合计）；
- 包含中文注释、含反斜杠的正则表达式；
- 包含正则、JSON、数组展开、窗口、聚合、条件和日期时间函数族；
- 包含 CTE、内联或标量子查询、JOIN 与集合运算；
- 使用 Spark SQL 语法，且只有一个最终查询。

## 使用方式

执行静态校验并生成本目录内的 `validation_report.json`：

```powershell
python tools/validate_production_dirty_sql_corpus.py
```

仅检查指定前缀的案例：

```powershell
python tools/validate_production_dirty_sql_corpus.py --cases 01 02 03 04 05
```

完整案例清单、业务场景和预期根表到输出路径由后续用例生成任务维护在本文件中。
