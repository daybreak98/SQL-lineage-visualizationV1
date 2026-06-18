# 架构债清单 — 孤立模块

> 来源：codegraph v1.0.1 索引（275 文件 / 3,203 节点 / 8,232 边）+ `codegraph callers` + grep import 双重验证。
> 范围：主代码 `backend/app/`。
> 日期：2026-06-18。

## 概述

在构建整体架构图（见 `docs/ARCHITECTURE.md`）时，通过 `codegraph callers <symbol>` 与 `grep "from app.services.<module> import"` 交叉验证，发现 `backend/app/services/` 下有 **3 个模块未接入运行时管线**。它们或是 placeholder、或是被内联重写后遗留、或是待接入未接入，均会增加新读者理解成本与误改风险。

`backend/app/services/__init__.py` 为空文件（0 行），无 re-export，因此下表"被引用"情况反映的是真实显式 import。

## 债项清单

### 1. `lineage_rollup_service.py` — 显式 placeholder（低风险）

| 项 | 内容 |
|---|---|
| 路径 | `backend/app/services/lineage_rollup_service.py` |
| 规模 | 12 行，仅 1 个函数 `rollup_structure_edges` |
| 孤立证据 | `grep "lineage_rollup_service" backend/` → **0 匹配**（无任何文件 import 此模块） |
| 自述 | docstring 原文：*"Placeholder hook for later column-to-structure rollups. C05 only needs already-extracted structure edges. Keeping this tiny function makes the C05 file list explicit without pretending we have full rollup logic."* |
| 性质 | **显式占位钩子**，C05 阶段故意留的文件占位，真正的 rollup 逻辑未实现 |
| 实际替代 | CTE 列血缘 rollup 由 `cte_column_rollup_service.CteColumnRollupService` 承担（见 `analyze_controller.py:212`） |
| 建议 | **删除或明确标注**。既然 rollup 已由 `cte_column_rollup_service` 实现，此 placeholder 已无对应"待实现"语义。若保留作历史标记，应在文件头加 `# DEPRECATED: superseded by cte_column_rollup_service` 并从 `services/` 移至 `docs/历史/` 或直接删除。优先级：低（不影响运行，仅是认知负担）。 |

### 2. `lateral_view_dependency_extractor.py` — 重复实现 + 孤立（中风险）

| 项 | 内容 |
|---|---|
| 路径 | `backend/app/services/lateral_view_dependency_extractor.py` |
| 规模 | 76 行，2 个函数：`extract_lateral_view_dependencies`（AST 路径）+ `extract_lateral_view_dependencies_heuristic`（正则兜底） |
| 孤立证据 | `grep "lateral_view_dependency_extractor" .`（全项目）→ **0 匹配**；`codegraph callers extract_lateral_view_dependencies` → 无调用者 |
| 性质 | **完全孤立的独立模块，功能被内联重写** |
| 实际替代 | `derived_relation_schema_builder.py:236` 自定义了 `_extract_lateral_view_dependencies`，并在 Line 270 用 `transform_type="lateral_view"` 标记，覆盖了同功能。`name_resolver.py:574` 把 `"lateral_view"` 列为 unsupported_feature。 |
| 风险 | 同一 lateral view 提取逻辑存在两份实现，后续修 bug 或扩方言时容易只改一份，造成行为不一致。 |
| 建议 | **二选一收口**。对比 `lateral_view_dependency_extractor.extract_lateral_view_dependencies` 与 `derived_relation_schema_builder._extract_lateral_view_dependencies` 的覆盖度与测试覆盖，保留更完整的一版，另一版删除或改为被调用方。若 `derived_relation_schema_builder` 的内联版已满足生产，则直接删除此孤立模块 + 其测试（若有）。优先级：中（重复实现是行为分叉的高发源头）。 |

### 3. `graph_port_order_optimizer.py` — 待接入未接入（中风险）

| 项 | 内容 |
|---|---|
| 路径 | `backend/app/services/graph_port_order_optimizer.py` |
| 规模 | 41 行，`PortOrderOptimizer` 类，含 `optimize` + `optimize_from_edges` 两个方法 |
| 孤立证据 | `grep "graph_port_order_optimizer" backend/` → **仅 1 匹配**：`backend/tests/test_graph_port_order_optimizer.py:2`；`backend/app/` 内零 import；`codegraph callers graph_port_order_optimizer` → 仅测试文件 |
| 性质 | **有完整实现且单测覆盖，但未接入主管线** |
| 实际替代 | `graph_layout_planner.GraphLayoutPlanner` 内部用私有方法 `_assign_port_orders` 处理端口顺序（`graph_layout_planner.py` 未 import `PortOrderOptimizer`） |
| 风险 | 一个带单测的优化器躺在 services 里却不被用，新读者会以为端口顺序走的是这个优化器，误改 `_assign_port_orders` 时不知道还有个"正牌"实现；或反过来，误以为 `PortOrderOptimizer` 在生效而放松对 `_assign_port_orders` 的测试。 |
| 建议 | **确认是否应接入**。对比 `PortOrderOptimizer.optimize_from_edges` 与 `graph_layout_planner._assign_port_orders` 的算法差异与效果。若 `PortOrderOptimizer` 更优，应接入 `graph_layout_planner` 并删除 `_assign_port_orders`；若 `_assign_port_orders` 已够用，则删除 `graph_port_order_optimizer.py` 及其测试，避免"双实现"困惑。优先级：中（带测试的死代码比无测试的死代码更误导）。 |

## 验证命令（可复现）

```powershell
# 在项目根目录执行

# 1. lineage_rollup_service — 期望 0 匹配
Get-ChildItem -Path backend -Recurse -Filter *.py | Select-String -Pattern "lineage_rollup_service" -SimpleMatch

# 2. lateral_view_dependency_extractor — 期望仅自身文件 + 0 import
Get-ChildItem -Path . -Recurse -Filter *.py | Select-String -Pattern "lateral_view_dependency_extractor" -SimpleMatch

# 3. graph_port_order_optimizer — 期望仅测试文件
Get-ChildItem -Path backend -Recurse -Filter *.py | Select-String -Pattern "graph_port_order_optimizer" -SimpleMatch

# 用 codegraph callers（需先 codegraph init）
codegraph callers graph_port_order_optimizer
codegraph callers extract_lateral_view_dependencies
codegraph callers rollup_structure_edges
```

## 处理优先级

| 顺序 | 债项 | 优先级 | 理由 |
|---|---|---|---|
| 1 | `lateral_view_dependency_extractor` | 中 | 重复实现，行为分叉风险最高 |
| 2 | `graph_port_order_optimizer` | 中 | 带测试的死代码，误导性最强 |
| 3 | `lineage_rollup_service` | 低 | 显式 placeholder，风险最低但认知负担明显 |

## 关联文档

- `docs/ARCHITECTURE.md` — 整体架构图，§6 模块清单已标注这 3 个模块的孤立状态
