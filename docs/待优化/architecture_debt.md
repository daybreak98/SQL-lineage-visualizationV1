# 架构债与优化优先级

> 范围：主代码 `backend/app/` 与 `frontend/src/`。
> 初次审查：2026-06-18。P0 收口：2026-06-20。

## 优先级定义

| 优先级 | 判定标准 |
|---|---|
| P0 | 会产生错误血缘、错误契约或明显不一致的生产行为 |
| P1 | 容易造成后续行为分叉、误改或较高维护成本 |
| P2 | 主要影响认知成本、构建治理或长期可维护性 |

## P0：已完成

### Lateral View 列依赖收口

**原问题**

- `lateral_view_dependency_extractor.py` 未被生产代码调用。
- `derived_relation_schema_builder.py` 内存在两套私有处理逻辑。
- `amount_item` 会被错误解析成 `ods_order_log.amount_item`，而不是
  `ods_order_log.refund_amount`。

**处理结果**

- `lateral_view_dependency_extractor.extract_lateral_view_dependencies` 成为唯一
  AST 提取入口。
- 提取器读取 SQLGlot `Lateral.alias.columns`，建立输出列到行展开表达式输入列的映射。
- `derived_relation_schema_builder` 使用现有 scope 将表别名解析成真实关系名，并以
  Lateral View 映射覆盖通用解析器产生的错误同名投影。
- `TransformType` 增加 `lateral_view`。
- 保留复杂 SQL 守卫的 defensive diagnostics、`unsupported_features` 和既有状态判定
  策略；当前修复不代表所有 Lateral View 方言和函数均已完全支持。

**回归契约**

```text
LATERAL VIEW explode(split(b.refund_amount, ',')) e AS amount_item

amount_item -> ods_order_log.refund_amount
```

测试：

- `backend/tests/test_lateral_view_dependency_extractor.py`
- `backend/tests/test_derived_relation_schema_builder.py`
- `backend/tests/integration/test_analyze_api_complex_sql_guard.py`

### 删除失效的 rollup placeholder

`backend/app/services/lineage_rollup_service.py` 无运行时或测试调用者，且真实 CTE
列血缘展开已由 `cte_column_rollup_service.CteColumnRollupService` 承担。该文件已删除。

## P1：待处理

### 方言转换尽量保持源 SQL 结构

**现状**

`POST /api/sql/convert` 使用：

```python
sqlglot.transpile(
    source_sql,
    read=source_dialect,
    write=target_dialect,
    pretty=True,
)
```

SQLGlot 会先将 SQL 解析为 AST，再按目标方言重新生成完整 SQL。这样可以保证目标语法
正确，但会统一重排缩进、换行、CTE、投影字段和各个子句。即使真正变化的只有一个函数，
Diff 也可能显示大量纯格式差异。

`pretty=False` 不能解决问题，因为目标 SQL 会被压缩成单行。

当前已有 `_minimize_diff_noise` 和 `_restore_source_word_case`，能够处理无语义变化时保留
原文以及部分关键字大小写恢复，但不能恢复整体结构。

**目标**

在继续由 SQLGlot 负责目标方言语义正确性的前提下，让转换结果尽量沿用源 SQL 的：

- 关键字大小写。
- 缩进宽度。
- SELECT 字段换行方式。
- 逗号前置或后置风格。
- `WHERE`、`GROUP BY`、`ORDER BY` 的换行方式。
- CTE 括号、空行和分号习惯。

用户查看 Diff 时，应优先看到函数、类型和语法结构的真实转换，而不是格式化噪音。

**推荐实施方案：源格式驱动的目标渲染**

1. 从源 SQL 提取 `SqlFormatProfile`：
   - 关键字大小写风格。
   - 缩进字符和宽度。
   - SELECT 投影是否逐行。
   - 逗号位置。
   - 子句与条件的换行策略。
   - CTE 和多语句分隔策略。
2. 使用 SQLGlot 完成源方言到目标方言的 AST 转换。
3. 按 SELECT、CTE、投影字段和主要子句对源/目标 AST 节点进行结构配对。
4. 使用目标 AST 的语义内容和源 SQL 的格式配置重新生成目标 SQL。
5. 无法可靠配对时回退到 SQLGlot `pretty=True`，并返回格式保持等级。

建议后端响应增加：

```text
format_preservation: high | medium | low
structural_changes: string[]
```

**分阶段实施**

| 阶段 | 内容 | 预期效果 |
|---|---|---|
| 1 | 格式特征提取和恢复 | 保留约 80% 的缩进、字段换行、子句布局与大小写 |
| 2 | 源/目标 AST 节点结构对齐 | 转换后的表达式保持在原字段和原子句位置 |
| 3 | 基于源码区间的局部补丁 | 仅替换发生变化的源码片段，其他字符保持不变 |

阶段 1 为当前推荐范围。阶段 3 虽然视觉效果最好，但注释、模板变量、嵌套函数和一对多
语法转换会显著增加错误风险，暂不建议实施。

**前端配合**

- 保留左右两侧独立的 Format 按钮。
- 默认转换采用“保持源结构”策略。
- DiffEditor 可启用忽略纯空白差异作为额外降噪，但不能替代后端结构保持。
- 格式保持等级较低时，在状态栏提示用户目标 SQL 已进行结构重排。

**验收标准**

- 仅发生函数替换时，未变化的 SELECT 字段和主要子句保持原行位置。
- `WHERE`、`GROUP BY`、`ORDER BY` 不因转换被无意义拆行。
- CTE 数量和顺序不变时，保持原 CTE 布局。
- 转换结果仍能被目标方言重新解析。
- 格式恢复失败时必须安全回退，不能影响 SQL 转换正确性。
- 建立 Spark → StarRocks、Hive → Spark 的格式保持 golden cases。

### 字段级端口排序的数据契约未接通

`graph_port_order_optimizer.PortOrderOptimizer` 与
`graph_layout_planner._assign_port_orders` 并非重复实现：

- `PortOrderOptimizer` 排列 `LayoutNode.field_order`，目标是节点内部字段顺序。
- `_assign_port_orders` 排列边的 `source_port_order` / `target_port_order`。

当前真正问题是主管线没有向 `LayoutNode.fields` 和 `LayoutEdge.data[source_field]`
传入字段信息，因此 `PortOrderOptimizer` 无法有效接入。

建议：

1. 先定义后端图布局字段端口契约。
2. 让 column lineage edge 携带 `source_field` / `target_field`。
3. 接入字段排序并增加交叉线数量回归测试。
4. 若后端布局最终不负责字段行排序，则删除该优化器及其独立测试。

### Lateral View 支持范围扩展

当前仅保证 SQLGlot 能正常解析的 AST 路径，并继续返回 defensive diagnostics。
后续需要针对以下形式分别增加 golden cases：

- `posexplode` 多输出列。
- `inline` 多字段输出。
- 多级 Lateral View 链。
- 输入表达式引用多个字段。
- 无表限定符字段与多表歧义。

## P2：待处理

### 大文件职责拆分

| 文件 | 当前规模 | 建议边界 |
|---|---:|---|
| `backend/app/api/analyze_controller.py` | 约 537 行 | API handler、分析编排、结果装配 |
| `frontend/src/components/LineageCanvas.tsx` | 约 561 行 | 路径选择、视口交互、SVG 渲染 |
| `frontend/src/graphPipeline.ts` | 约 703 行 | 后端归一化、视图投影、布局适配 |
| `frontend/src/pages/DialectConvertPage.tsx` | 约 480 行 | 页面状态、编辑器、转换结果展示 |

拆分应以新增行为或回归修复为契机，不做无测试保护的大规模机械移动。

### 工程配置治理

- `frontend/package.json` 中 `test` 与 `test:watch` 重复定义。
- 多个核心依赖使用 `latest`，构建结果不可稳定复现。
- 后端 CORS 使用 `allow_origins=["*"]`，需要按开发/生产环境配置。

## 可复现检查

```powershell
# 确认旧 placeholder 已删除且无引用
rg "lineage_rollup_service|rollup_structure_edges" backend

# 确认 Lateral View 仅保留一个 AST 提取入口
rg "def .*lateral|extract_lateral_view_dependencies" backend/app/services

# 确认字段端口优化器仍仅由测试直接引用
rg "PortOrderOptimizer|graph_port_order_optimizer" backend
```
