# 实施检查表：CTE / 非 CTE 链路统一 Orchestrator 改造

## 0. 改造前确认

- [ ] 当前 C00-C10 测试全部通过。
- [ ] 确认 `analyze_controller.py` 当前存在 CTE / 非 CTE 两套大分支。
- [ ] 确认 `name_resolver.py` 支持或已经新增 `is_cte_context=True`。
- [ ] 确认 `source_location_service.py` 当前仍主要围绕 output_column 定位。

---

## 1. 新增结构分析层

- [ ] 新增 `query_structure_service.py`。
- [ ] 新增 `QueryStructureResult`。
- [ ] 实现 `extract_cte_names(tree)`。
- [ ] 实现 `extract_physical_table_names(tree, exclude_cte_names=True)`。
- [ ] 实现 `extract_final_select_source_names(tree)`。
- [ ] 实现 `analyze_query_structure(tree)`。
- [ ] 测试 CTE 名不进入 physical_table_names。

---

## 2. 新增解析上下文

- [ ] 新增 `LineageResolveContext`。
- [ ] `resolve_column_lineage_names()` 支持 `context` 参数。
- [ ] 保持旧参数兼容。
- [ ] 废弃或弱化 `is_cte_context=True`。
- [ ] `context.resolve_scope == "final_select"` 时，只解析最终输出字段。

---

## 3. 改造 analyze_controller

- [ ] 去掉 CTE / 非 CTE 两套大段重复逻辑。
- [ ] 统一调用 `analyze_query_structure(tree)`。
- [ ] 统一调用 `_load_metadata(structure.physical_table_names)`。
- [ ] 统一调用 `resolve_column_lineage_names(tree, metadata, context)`。
- [ ] 统一组装 graphs。
- [ ] 统一 merge_graphs。
- [ ] 统一 source_location_service 调用。

---

## 4. 图谱构建

- [ ] CTE SQL 保留 `build_cte_structure_graph()`。
- [ ] 非 CTE SQL 保留 `build_table_structure_graph()`。
- [ ] 所有 SQL 都尝试 `build_column_lineage_graph()`。
- [ ] `validate_graph()` 不报 source/target 缺失。
- [ ] CTE 字段血缘 graph 中的 node id 与 source_location target entity_id 一致。

---

## 5. SourceLocation 改造

- [ ] 新增 `SourceLocationTarget`。
- [ ] 实现 `extract_source_location_targets_from_graph(graph)`。
- [ ] `build_source_locations()` 支持 target_entities。
- [ ] 兼容旧 output_column_names 入参。
- [ ] 支持 `physical_table` 定位。
- [ ] 支持 `cte` 定位。
- [ ] 跳过 `query_result:final`。
- [ ] mask 字符串和注释后再正则扫描。
- [ ] 支持 start/end offset。
- [ ] 支持同 entity 多 occurrence。

---

## 6. Capability 与诊断

- [ ] API 返回 `cte_structure_lineage=true/false`。
- [ ] API 返回 `cte_final_select_column_lineage=true/false`。
- [ ] API 返回 `cte_end_to_end_column_lineage=false`，除非已真实实现。
- [ ] CTE 内复杂结构不能静默通过，必须返回 partial/diagnostic。

---

## 7. 回归测试

- [ ] 非 CTE 单表测试。
- [ ] 非 CTE Join 测试。
- [ ] CTE 结构图测试。
- [ ] CTE 最后一跳字段血缘测试。
- [ ] CTE 名不查 metadata 测试。
- [ ] CTE + Join 最终选择测试。
- [ ] SourceLocation physical_table 测试。
- [ ] SourceLocation cte 测试。
- [ ] SourceLocation 注释/字符串防误匹配测试。
- [ ] 同一物理表多次出现 occurrence 测试。

---

## 8. 最终验收命令建议

```bash
pytest -q
pytest -q tests/test_analyze_api_c03.py
pytest -q tests/test_analyze_api_c04.py
pytest -q tests/test_analyze_api_c05.py
pytest -q tests/test_analyze_api_c08.py
pytest -q tests/test_unified_orchestrator_reference.py
pytest -q tests/test_source_location_reference.py
```

