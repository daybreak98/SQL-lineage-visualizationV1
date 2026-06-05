# 测试与 Golden Cases 说明

## 1. 新增测试

本次为复杂 SQL 容错能力新增了以下测试文件：

- `backend/tests/test_complex_sql_shields.py`
- `backend/tests/test_complex_sql_segmenter.py`
- `backend/tests/test_complex_sql_parser_adapter.py`
- `backend/tests/test_complex_sql_analyzer.py`
- `backend/tests/test_complex_sql_golden_cases.py`
- `backend/tests/integration/test_analyze_api_complex_sql_guard.py`

## 2. 覆盖点

### shield 测试
- regex literal shielding
- JSONPath literal shielding
- `${zdt...}` 模板 shielding
- Freemarker block shielding

### segmenter 测试
- CTE + join 分段
- lateral view 分段

### parser adapter 测试
- `sqlglot` parse error 的结构化返回

### analyzer 测试
- broken CTE 时返回 `partial`
- segment fallback 是否生效

### API 集成测试
- 模板 SQL 的 guard 字段返回
- lateral view 的 unsupported diagnostics
- partial fallback 是否暴露 `segments / parse_attempts`

## 3. Golden Cases

本次新增 5 组 golden cases：

### `complex_regex_json`
- 覆盖 regex literal + JSONPath + template literal + CTE

### `hive_lateral_view_explode`
- 覆盖 `lateral view explode`

### `spark_template_variable`
- 覆盖 `${zdt...}` 这类 Spark/Hive 模板变量

### `multi_cte_join_20_tables`
- 覆盖长 CTE 链和大 join 扇出

### `parse_error_partial_fallback`
- 覆盖单个坏 CTE item 导致整体 parse 失败但 segment 可恢复的场景

## 4. 全量回归

执行命令：

```bash
cd backend
pytest -q
```

结果：

```text
115 passed, 1 warning
```

## 5. 测试隔离修复

为了保证测试稳定性，本次额外修复了元数据库共享污染问题：

- 在 `backend/tests/conftest.py` 中加入自动清表
- 避免 metadata 测试与 analyze 测试互相污染

这一步让全量 pytest 可以稳定重复执行。

