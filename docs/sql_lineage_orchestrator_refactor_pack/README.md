# SQL 血缘项目：CTE / 非 CTE 链路进一步统一改造包

本压缩包用于指导 opencode / Codex 在当前 SQL 血缘项目中继续改造 `POST /api/sql/analyze` 的后端编排链路。

核心目标：

```text
不要继续维护 CTE / 非 CTE 两套大分支；
也不要把所有底层 Service 强行合并；
而是把 analyze_controller 改为统一 Orchestrator 编排。
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `SQL_lineage_unified_orchestrator_design.md` | 主设计文档，说明为什么合并、合并边界、风险和验收标准 |
| `opencode_prompt.md` | 可直接复制给 opencode 的开发提示词 |
| `implementation_checklist.md` | 实施步骤和回归检查表 |
| `core_code/lineage_context.py` | `LineageResolveContext` 参考实现 |
| `core_code/query_structure_service.py` | `QueryStructureResult` 与统一结构分析参考实现 |
| `core_code/source_location_targets.py` | 从 graph nodes 提取 SourceLocation target 的参考实现 |
| `core_code/source_location_service_patch.py` | SourceLocation 扩展参考实现，支持 output_column / physical_table / cte |
| `core_code/analyze_orchestrator_patch.py` | analyze_controller 统一编排伪代码/参考实现 |
| `tests/test_unified_orchestrator_reference.py` | CTE / 非 CTE 合并链路测试建议 |
| `tests/test_source_location_reference.py` | SourceLocation 扩展测试建议 |

## 使用方式

1. 先阅读 `SQL_lineage_unified_orchestrator_design.md`。
2. 把 `opencode_prompt.md` 作为任务提示词交给 opencode。
3. 代码实现时不要机械复制所有参考代码，需结合当前项目已有 dataclass / Pydantic model / graph node 字段命名做最小适配。
4. 每完成一小步跑已有 C00-C10 测试，再补充本包里的新增测试。

