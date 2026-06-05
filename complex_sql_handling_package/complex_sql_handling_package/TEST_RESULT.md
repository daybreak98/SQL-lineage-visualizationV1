# 测试结果

执行命令：

```bash
python -m unittest discover -s tests -v
python scripts/run_demo.py
```

结果：

```text
test_analyze_dirty_sql_returns_partial_or_success ... ok
test_does_not_split_nested_select ... ok
test_segments_top_level_clauses ... ok
test_keeps_original_sql ... ok
test_shields_regex_and_template ... ok

Ran 5 tests in 0.002s
OK
```

说明：当前环境未安装 sqlglot，因此 parser_adapter 会返回 `SQLGLOT_NOT_INSTALLED` 诊断，但预处理、placeholder、分段、partial result 均可正常工作。实际项目接入时建议安装 `sqlglot` 并继续补充分段级 parse 测试。
