# FlowScope 与当前 SQL 血缘可视化项目对比  
## 可借鉴点、改造边界与分阶段落地方案 v1.0

> 文档目标：不是简单罗列 FlowScope 功能，而是从产品、架构、解析内核、领域模型、图谱构建、前端交互、性能、测试和部署等层面，自顶向下分析当前项目可以借鉴的设计，并明确哪些内容应直接吸收、哪些需要结合 Spark/Hive 场景改造、哪些不应照搬。  
>
> 当前项目基线：SQLGlot + Python + FastAPI + SQLite + Monaco Editor + React Flow，重点面向复杂 Spark/Hive 数仓 SQL 的本地静态分析与血缘可视化。  
>
> FlowScope 参考基线：`pondpilot/flowscope` 的公开 `master` 分支文档，以及核心源码快照 `30ef56af65db975e46ed4c22a5696ed0708e0b44` 附近实现。  
>
> 文档日期：2026-06-16。

---

# 1. 总体结论

## 1.1 最重要的判断

FlowScope 最值得借鉴的不是 Rust、WASM、CodeMirror、React Flow 或某个具体界面，而是它已经形成了比较完整的工程闭环：

```text
SQL 输入
  ↓
方言解析
  ↓
作用域与名称解析
  ↓
表达式字段依赖
  ↓
语句级血缘片段
  ↓
跨语句统一图模型
  ↓
图变换与简化
  ↓
稳定 API 契约
  ↓
React 图谱与编辑器联动
  ↓
CLI / Web / VS Code 等多种产品外壳
```

当前项目已经在 v0.7 规划中识别出以下正确方向：

- Orchestrator 编排式分析链路；
- DiagnosticsCollector 旁路收集；
- Stable Entity ID；
- GraphViewModel 与 GraphInteractionState 分离；
- SourceLocation 增强；
- Golden Case；
- partial / unsupported / timeout 降级；
- Monaco Editor 工程化边界。

因此，FlowScope 的出现并不说明当前项目方向错误。相反，它证明这些设计确实是产品级 SQL 静态分析工具必须具备的基础。

当前项目真正需要做的是：

> 将这些仍然停留在“文档规划层”的能力，收敛成稳定的领域模型、清晰的模块边界、可验证的图变换管线和可度量的质量体系。

---

## 1.2 推荐借鉴优先级

| 优先级 | 借鉴方向 | 对当前项目的价值 |
|---|---|---|
| P0 | 稳定分析结果契约 | 防止前后端模型持续漂移 |
| P0 | Canonical Entity 与 Relation Instance 双层身份 | 解决多语句合并、自连接、同名 CTE、别名等核心问题 |
| P0 | Scope Stack 与实例感知名称解析 | 提升复杂 CTE、子查询、自连接列血缘准确率 |
| P0 | 多输入表达式依赖模型 | 支持 CASE、聚合、函数、比率等真实指标 |
| P0 | 原始事实图与派生简化图分离 | 支持 CTE 隐藏、根血缘、路径血缘和后续降复杂度 |
| P0 | Imported / Implied / Resolved Metadata | 提升 `select *`、字段归属和诊断能力 |
| P1 | 多文件统一图模型 | 为 SQLite 全仓血缘和跨脚本依赖奠定基础 |
| P1 | Source Span 与图谱双向定位 | 让血缘结果可解释、可验证 |
| P1 | Graph Builder Worker、布局缓存和取消机制 | 提升复杂 SQL 前端可用性 |
| P1 | Schema 契约快照与前后端兼容测试 | 防止 API 变更引发静默错误 |
| P2 | CLI 本地服务与目录监听 | 支持本地项目目录、EXE 和增量分析 |
| P2 | AI 仅消费确定性分析结果 | 避免 AI 污染核心血缘事实 |

---

## 1.3 不建议照搬的内容

| 内容 | 不建议原因 |
|---|---|
| 全面改写为 Rust + WASM | 当前项目的核心优势是 SQLGlot、Python 开发速度和 Spark/Hive 适配，重写成本远大于收益 |
| 立即追求大量 SQL 方言 | 会稀释 Spark/Hive 生产 SQL 的专项优势 |
| 复制完整 SQL Linter | 与当前核心目标偏离，且 SQLFluff 等项目已经很成熟 |
| 优先开发 VS Code 插件 | 当前最关键问题仍然是解析准确率和图谱可读性 |
| 复制 Librarian PDF RAG | 与生产 SQL 血缘核心痛点关联较弱 |
| 直接复制 FlowScope `app/` | `app/` 采用 O'Saasy License，且产品定位与当前项目不完全一致 |
| 用通用 ELK 布局取代语义布局 | FlowScope 的布局主要利用拓扑结构，当前项目仍应保留 SQL 语义 rank、lane、权重和字段端口排序 |

---

# 2. 产品定位层：借鉴“核心引擎 + 多种产品外壳”

## 2.1 FlowScope 的产品结构

FlowScope 将同一套 SQL 分析能力封装成多个入口：

```text
flowscope-core
  ├─ WASM API
  ├─ TypeScript API
  ├─ React 组件
  ├─ Web App
  ├─ CLI
  ├─ Local Serve
  └─ VS Code Extension
```

核心价值不是“每个端都重新做一次解析”，而是：

```text
一个确定性分析内核
  + 一个稳定结果契约
  + 多个消费端
```

## 2.2 当前项目应该如何借鉴

当前项目不需要立刻增加所有外壳，但应该从架构上允许：

```text
SQL Lineage Engine
  ├─ FastAPI
  ├─ 本地 CLI
  ├─ Web 前端
  ├─ 桌面 EXE
  └─ 后续批处理任务
```

推荐的产品边界：

```text
核心引擎：
  不理解 HTTP
  不理解 React Flow
  不理解 SQLite UI
  只负责输入 AnalysisRequest，输出 AnalysisResult

API 层：
  FastAPI 请求校验、序列化、错误映射

前端层：
  消费 GraphViewModel 和 SourceLocation

批处理层：
  扫描 SQL 文件并将实体、语句、边写入 SQLite

桌面层：
  启动本地后端和前端，不修改分析逻辑
```

## 2.3 建议形成的目录结构

```text
backend/app/
├── api/
│   ├── analyze_routes.py
│   ├── metadata_routes.py
│   └── project_routes.py
├── application/
│   ├── analysis_orchestrator.py
│   ├── project_analysis_service.py
│   └── analysis_result_builder.py
├── domain/
│   ├── models/
│   │   ├── entity.py
│   │   ├── lineage.py
│   │   ├── diagnostics.py
│   │   ├── source_location.py
│   │   └── graph_view.py
│   └── services/
│       ├── lineage_rollup.py
│       ├── graph_transform.py
│       └── semantic_classifier.py
├── ports/
│   ├── sql_parser.py
│   ├── metadata_repository.py
│   └── project_repository.py
├── adapters/
│   ├── sqlglot/
│   ├── sqlite/
│   └── file_system/
└── cli/
    └── main.py
```

## 2.4 直接收益

1. 后续开发 CLI、EXE 或批处理时，不必复制解析逻辑。
2. 前端页面可以持续演进，而不会影响领域模型。
3. Codex 开发时有清晰的依赖方向，不容易将 SQLGlot AST、数据库 DAO 和 React Flow 数据混在一起。
4. 后续增加第二解析器做对抗验证时，只需实现新的 Parser Adapter。

---

# 3. 总体架构层：借鉴稳定的“分析内核—契约—视图”三层结构

## 3.1 FlowScope 的关键分层

FlowScope 的 Monorepo 关系清晰：

```text
Rust Core
  ↓
WASM
  ↓
TypeScript Core API
  ↓
React Visualization
  ↓
Web App / VS Code
```

它的核心意义是：分析事实、跨语言契约、图谱呈现和具体应用之间有明确边界。

## 3.2 当前项目建议的对应结构

```text
SQLGlot Adapter
  ↓
Internal Analysis IR
  ↓
AnalysisResult / JSON Schema
  ↓
Generated TypeScript Types
  ↓
GraphViewModel Adapter
  ↓
React Flow Canvas
```

其中最重要的一条约束是：

> 前端不得直接消费 SQLGlot AST，也不得根据后端原始 AST 自己推断节点类型、CTE 层级和字段来源。

## 3.3 当前项目需要新增的中间层

目前项目如果仍然主要使用：

```text
SQLGlot AST
  → 简单字典
  → Pydantic
  → GraphBuilder
```

建议进一步明确两个中间产物：

### A. Analysis IR

负责表达解析事实：

```python
class AnalysisIR:
    statements: list[StatementIR]
    entities: list[Entity]
    lineage_edges: list[LineageEdge]
    diagnostics: list[Diagnostic]
    source_locations: list[SourceLocation]
    resolved_schema: ResolvedSchema
```

### B. GraphViewModel

负责表达某种视图：

```python
class GraphViewModel:
    view_mode: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    layout_hints: LayoutHints
```

两者之间通过 GraphBuilder 和 GraphTransformPipeline 转换。

## 3.4 必须避免的结构

```text
SQLGlot AST
  → GraphBuilder 直接遍历
  → React Flow nodes / edges
```

这种结构的风险：

- 解析逻辑与展示逻辑耦合；
- CTE 隐藏、字段折叠和根血缘会修改原始事实；
- 无法支持多个视图；
- 无法可靠做跨脚本合并；
- 前端布局需求会反向污染解析模型。

---

# 4. 领域身份模型：最值得优先借鉴的设计

## 4.1 FlowScope 解决了两个不同的问题

FlowScope 同时区分：

### Canonical Identity

用于判断不同语句中的实体是否是同一张物理表或同一个物理字段。

例如：

```text
catalog.schema.table
catalog.schema.table.column
```

### Relation Instance

用于表示某张表在某个语句、某个 scope、某个别名下的一次具体引用。

例如：

```sql
FROM employees e1
JOIN employees e2
```

物理实体相同：

```text
employees
```

但实例不同：

```text
statement_1.scope_3.alias_e1
statement_1.scope_3.alias_e2
```

## 4.2 当前 Stable Entity ID 规划需要进一步细化

当前项目已经提出：

```text
entity_id
node_id
interaction_id
```

这还应继续扩展为：

| ID | 作用 |
|---|---|
| canonical_entity_id | 跨语句、跨文件稳定标识物理表和物理字段 |
| relation_instance_id | 标识某语句中某个 alias/scope 下的关系实例 |
| derived_entity_id | 标识 CTE、子查询、输出字段等语句内派生实体 |
| graph_node_id | 某个视图中的节点 ID |
| interaction_key | 前端选择、拖拽、折叠等状态键 |

## 4.3 推荐 ID 形式

```text
canonical table:
table:hive:ihotel_default.mdw_order_v3_international

canonical column:
column:hive:ihotel_default.mdw_order_v3_international.order_no

relation instance:
relation_instance:stmt_12:scope_4:alias_a:
table:hive:ihotel_default.mdw_order_v3_international

CTE:
cte:file_x.sql:stmt_12:scope_1:search_result

CTE column:
cte_column:file_x.sql:stmt_12:scope_1:search_result.show_uv

output:
output:file_x.sql:stmt_12:单UV收益
```

## 4.4 为什么这是第一优先级

缺少该模型会导致：

1. Self Join 的两侧字段错误合并。
2. 不同 SQL 文件中同名 CTE 错误合并。
3. 物理表跨脚本无法稳定聚合。
4. 重新分析后节点位置无法复用。
5. SQL diff 无法判断“改名”和“新增”。
6. SQLite 全仓血缘中出现大量重复实体。
7. CTE 隐藏后无法正确保留中间路径。

## 4.5 推荐验收用例

```sql
WITH x AS (
    SELECT id FROM db.t
)
SELECT a.id, b.id
FROM x a
JOIN x b ON a.id = b.id;
```

必须同时满足：

- `db.t.id` 只有一个 canonical entity；
- `x a` 与 `x b` 是两个 relation instance；
- `a.id` 与 `b.id` 的路径可区分；
- 最终输出的两个 `id` 不发生节点冲突；
- 隐藏 CTE 后仍能生成两条可追踪的根血缘路径。

---

# 5. 解析内核层：借鉴 Scope Stack 与实例感知解析

## 5.1 FlowScope 的 Scope 设计

FlowScope 为每个：

- SELECT；
- CTE body；
- 子查询；
- 派生表；

建立独立 scope，并在 scope 中维护：

```text
tables
aliases
alias_instances
subquery_aliases
subquery_columns
scope_id
```

它解决的核心问题不是“能否找到字段名”，而是：

> 在当前词法作用域中，这个字段引用到底指向哪个关系实例。

## 5.2 当前项目需要避免的简化

以下做法对复杂 SQL 不可靠：

```python
global_alias_map = {
    "a": "table_a",
    "b": "table_b",
}
```

因为：

- 同一个别名可以在不同子查询中重复使用；
- 内层 alias 会覆盖外层 alias；
- CTE 和物理表可能同名；
- 同一个 CTE 可以被引用多次；
- correlated subquery 需要逐层向外查找；
- Self Join 必须保留实例。

## 5.3 推荐 ScopeResolver 模型

```python
@dataclass
class ResolveScope:
    scope_id: str
    parent_scope_id: str | None
    statement_id: str
    relations_by_alias: dict[str, RelationInstance]
    derived_relations: dict[str, DerivedRelationSchema]
    output_columns: dict[str, ColumnDependency]
    unresolved_wildcards: list[PendingWildcard]
```

名称解析顺序：

```text
1. 当前 scope 的 alias instance
2. 当前 scope 的派生表 alias
3. 当前 scope 的 CTE definition
4. 父 scope
5. 元数据中的物理表
6. 无法消歧则返回 AMBIGUOUS_COLUMN / UNKNOWN_COLUMN
```

## 5.4 推荐模块职责

```text
ScopeResolver：
  建立作用域、关系实例和 alias 可见性

NameResolver：
  在 scope 中将 ColumnRef 解析为具体 EntityRef

ExpressionAnalyzer：
  提取表达式中出现的所有字段引用

LineageEngine：
  将输出字段与已解析输入字段建立依赖

DiagnosticsCollector：
  记录字段歧义、未知字段、作用域降级和启发式解析
```

## 5.5 当前项目可直接借鉴的边界

- CTE definition 与 CTE reference 分离；
- 物理实体与引用实例分离；
- Scope-local subquery columns；
- 父子 scope 查找；
- 同名 alias 不跨 scope 泄漏；
- 对实例数量设置安全上限；
- 解析失败时保留诊断而不是直接崩溃。

---

# 6. 表达式依赖层：从单字段来源升级为多输入依赖

## 6.1 FlowScope 的做法

FlowScope 会递归遍历表达式中的：

- Identifier；
- Qualified Identifier；
- Binary Operation；
- Unary Operation；
- Function Arguments；
- CASE WHEN；
- CAST；
- IN；
- BETWEEN；
- IS NULL；
- LIKE；
- Tuple；
- EXTRACT 等。

因此：

```sql
CAST(
  CASE
    WHEN a.is_display = 1
    THEN a.price * a.quantity
  END
AS DECIMAL)
```

会抽取：

```text
a.is_display
a.price
a.quantity
```

## 6.2 当前项目必须升级的核心模型

不再使用只支持：

```text
一个输出字段 ← 一个输入字段
```

的模型。

应改为：

```python
@dataclass
class ColumnDependency:
    output: EntityRef
    inputs: list[EntityRef]
    expression: str | None
    transform_type: str
    aggregation: AggregationInfo | None
    evidence_locations: list[SourceLocationRef]
    confidence_level: str
```

## 6.3 TransformType 建议

```text
projection
alias
cast
arithmetic
case_when
aggregate
window
filter_derived
map_access
array_access
udf
constant
unknown
```

## 6.4 对当前复杂 SQL 的直接价值

例如：

```sql
cast(b.total_order_commission / a.show_uv as decimal(20,2))
as 单UV收益
```

应该形成：

```text
output.单UV收益
  ← order_result.total_order_commission
  ← search_result.show_uv
```

继续向上展开后得到多个物理根字段。

再例如：

```sql
count(
    distinct case
        when a.is_display = '1'
        then a.search_request_uid
    end
) as show_pv
```

至少要记录：

```text
a.is_display
a.search_request_uid
  → search_result.show_pv
```

## 6.5 UDF 的处理建议

FlowScope 对未知函数主要抽取参数字段。当前项目可进一步增加本地 UDF 规则库：

```json
{
  "function": "json_path_array",
  "dependency_policy": "all_arguments",
  "semantic_role": "collection_extract",
  "output_cardinality": "may_expand"
}
```

规则分级：

```text
builtin_exact
configured_exact
argument_dependency_only
unknown_function
```

这会成为 Spark/Hive 生产场景的重要差异化。

---

# 7. CTE 与图变换层：借鉴 bypass 思想，但不要破坏原始事实

## 7.1 FlowScope 的 CTE 隐藏机制

FlowScope 在隐藏 CTE 时会进行图后处理：

```text
A → CTE → B
```

转换为：

```text
A → B
```

并支持：

```text
A → CTE1 → CTE2 → B
```

以及 fan-in / fan-out：

```text
A、B → CTE → C、D
```

转换为：

```text
A→C
A→D
B→C
B→D
```

它还会尝试继承：

- expression；
- operation；
- join info；
- approximate；
- metadata。

## 7.2 当前项目应借鉴的核心思想

CTE 隐藏不是前端简单删除节点，而是：

```text
原始事实图
  ↓
Graph Transformation
  ↓
派生展示图
```

## 7.3 当前项目应比 FlowScope 更严格

不要直接用变换后的边替换原始边。

建议同时保留：

```python
class AnalysisResult:
    immediate_lineage: list[LineageEdge]
    root_lineage: list[LineageEdge]
    lineage_paths: list[LineagePath]
    fact_graph: LineageGraph
```

前端视图按需生成：

```text
full_path_view
root_view
immediate_view
cte_hidden_view
main_chain_view
metric_view
grain_change_view
```

## 7.4 推荐 GraphTransformPipeline

```text
FactGraph
  ↓
ScopeNormalizationTransform
  ↓
DuplicateEntityMergeTransform
  ↓
CteBypassTransform
  ↓
SimpleProjectionCollapseTransform
  ↓
MainChainExtractionTransform
  ↓
ViewGraph
```

每个 Transform 必须：

- 输入不可变图或图副本；
- 输出新的图；
- 保留 provenance；
- 记录被折叠路径；
- 可独立测试；
- 不修改事实血缘。

## 7.5 推荐 BypassEdge 模型

```python
@dataclass
class BypassEdge(LineageEdge):
    derived_from_edge_ids: list[str]
    collapsed_node_ids: list[str]
    path_ids: list[str]
    propagated_expression: str | None
    approximate: bool
```

## 7.6 对后续“降低复杂度”的价值

有了通用图变换层，可以进一步实现：

```text
直接投影链折叠
简单 CAST 链折叠
别名链折叠
无粒度变化 CTE 合并
公共维表分支折叠
只保留主事实链路
只保留某个指标路径
```

这是当前项目可以明显超越 FlowScope 的方向。

---

# 8. 元数据层：借鉴 Imported / Implied / Resolved Schema

## 8.1 FlowScope 的三类元数据

FlowScope 会区分：

```text
Imported Schema：
用户提供或外部导入的明确元数据

Implied Schema：
从 CREATE TABLE、字段引用、JOIN 条件等推导出的元数据

Resolved Schema：
实际分析使用的合并结果
```

同时记录表和字段的来源。

## 8.2 当前 SQLite 元数据仓库建议升级

当前项目不应只存：

```text
table
column
comment
type
```

还应记录：

```text
metadata_origin
metadata_version
resolution_priority
source_statement_id
quality_status
last_updated_at
temporary
primary_key
foreign_key
partition_key
grain_hint
```

## 8.3 推荐数据模型

```python
class MetadataOrigin(str, Enum):
    IMPORTED = "imported"
    DDL = "ddl"
    INFERRED_REFERENCE = "inferred_reference"
    INFERRED_JOIN = "inferred_join"
    MANUAL = "manual"
    UNKNOWN = "unknown"
```

```python
class ResolvedColumn:
    canonical_entity_id: str
    name: str
    data_type: str | None
    origin: MetadataOrigin
    confidence_level: str
    metadata_version: str
```

## 8.4 Select Star 的处理

建议采用三档结果：

| 元数据情况 | 行为 |
|---|---|
| 完整字段列表 | 精确展开 |
| 部分字段列表 | 展开已知字段，保留 unresolved wildcard |
| 无字段列表 | 不伪造字段，记录 PendingWildcard，返回 partial |

## 8.5 PendingWildcard 的借鉴价值

FlowScope 会记录无法展开的 `SELECT *`，并尝试通过下游字段引用反推必须流经的字段。

当前项目可设计：

```python
@dataclass
class PendingWildcard:
    source_relation_id: str
    target_relation_id: str
    scope_id: str
    source_location: SourceLocation
    inference_candidates: set[str]
```

后续当下游引用：

```text
cte_x.order_no
```

而 `cte_x` 来自：

```sql
SELECT * FROM source_table
```

可推断：

```text
source_table.order_no
  → cte_x.order_no
```

但必须标记：

```text
resolution_type = inferred_from_downstream
confidence_level = medium
```

---

# 9. 多语句与多文件层：从“单 SQL 页面”走向本地数仓代码地图

## 9.1 FlowScope 的 Flat Graph

FlowScope 不再让每个 Statement 各自持有完全独立图，而是：

```text
AnalyzeResult
  ├─ statements[]
  ├─ nodes[]
  ├─ edges[]
  └─ issues[]
```

节点和边通过：

```text
statement_ids[]
source_name
canonical_name
```

关联到具体语句和文件。

相同物理表跨语句只保留一个 canonical node，但：

- CTE 保持 statement scoped；
- Self Join instance 保持独立；
- Cross Statement 产生独立边。

## 9.2 当前项目长期目标与其高度匹配

当前项目已经计划：

```text
批量导入数仓 SQL 脚本
  ↓
解析写入 SQLite
  ↓
构建整个数仓模型
```

因此应尽早避免只围绕单请求设计 ID 和数据结构。

## 9.3 推荐分两层存储

### Analysis Snapshot

记录某次单文件或单请求分析结果：

```text
analysis_run
statement
local_entity
local_lineage_edge
diagnostic
source_location
```

### Warehouse Canonical Graph

记录跨脚本稳定实体：

```text
canonical_entity
relation_instance
script
job
cross_script_edge
entity_occurrence
metadata_version
```

## 9.4 推荐跨脚本合并规则

| 实体 | 合并规则 |
|---|---|
| 物理表 | 按 catalog + schema + normalized name |
| 物理字段 | 按物理表 canonical ID + normalized column |
| CTE | 不跨 statement 合并 |
| 子查询 | 不跨 statement 合并 |
| 输出临时别名 | 默认不跨 statement 合并 |
| INSERT/CTAS 目标表 | 合并到物理 canonical entity |
| Self Join instance | 保持 statement scoped |
| 临时表 | 根据 session/script scope 决定是否合并 |

## 9.5 推荐第一批跨脚本能力

1. 一张表由哪些脚本生产。
2. 一张表被哪些脚本消费。
3. 一个字段经过哪些脚本传递。
4. 修改某字段影响哪些下游目标字段。
5. 同一个目标表是否存在多个生产脚本。
6. 哪些脚本解析为 partial。
7. 哪些跨脚本链路存在断点。

---

# 10. SourceLocation 与诊断层：借鉴“结果必须可回到证据”

## 10.1 FlowScope 的定位模型特点

FlowScope 的节点会记录：

```text
span
name_spans
body_span
occurrence spans
statement IDs
source names
```

这使得：

- 点击节点定位 SQL；
- 同一物理表在多个文件中的出现位置可追踪；
- CTE 名称和 CTE body 可分别定位；
- Self Join 的两个引用可以定位到不同 occurrence。

## 10.2 当前 SourceLocation v2 方向正确

当前项目已经计划：

```text
start_line
start_col
end_line
end_col
start_offset
end_offset
range_type
origin
coordinate_system
confidence
```

建议进一步增加：

```text
source_name
statement_id
scope_id
occurrence_type
parent_location_id
normalized_text
offset_encoding
```

## 10.3 OccurrenceType 建议

```text
definition
reference
alias_declaration
column_reference
qualifier_reference
expression
cte_body
join_condition
filter_condition
group_by
order_by
output_alias
```

## 10.4 SourceLocation 不应只是 UI 功能

它应该成为以下能力的共同证据层：

```text
血缘解释
诊断定位
SQL diff
图谱点击定位
AI 回答引用
Golden Case 验证
解析错误排查
```

## 10.5 诊断模型建议

```python
class Diagnostic:
    code: str
    severity: str
    stage: str
    message: str
    entity_ids: list[str]
    locations: list[SourceLocationRef]
    resolution_type: str
    suggested_action: str | None
```

Stage 建议：

```text
preprocess
parse
scope
name_resolution
metadata
expression
lineage
graph_transform
layout
```

## 10.6 必须避免 numeric confidence 伪精确

P0 建议使用：

```text
exact
high
medium
low
unknown
```

并配套：

```text
resolution_reason
evidence_count
diagnostic_codes
```

不要只返回难以解释的：

```text
0.83
```

---

# 11. 前端图谱层：借鉴 Worker、缓存和取消，不照搬通用布局

## 11.1 FlowScope 的性能设计

FlowScope 将高成本工作拆分：

```text
AnalyzeResult
  ↓
Graph Builder Worker
  ↓
React Flow nodes / edges
  ↓
Layout Worker / ELK
  ↓
最终坐标
```

并实现：

- Graph Builder Web Worker；
- 布局缓存；
- 请求 ID；
- pending request 管理；
- 取消旧请求；
- Worker 不支持时降级；
- Dagre 同步布局；
- ELK Layered 异步布局；
- 快速网格布局；
- 节点高度按字段和过滤条件动态计算。

## 11.2 当前项目应直接借鉴的内容

### A. Graph Builder Worker

适合放入 Worker 的任务：

```text
过滤不可见节点
构造表/字段节点
构造字段边
处理折叠状态
路径高亮集合计算
视图模式转换
GraphViewModel → React Flow model
```

### B. Layout Worker

适合放入 Worker 的任务：

```text
rank 分层
lane 分配
Weighted Barycenter
Median Sweep
Port Ordering
虚拟节点
坐标计算
交叉边统计
```

### C. Cancellation

每次分析或切换视图都生成：

```text
request_id
graph_version
layout_version
```

旧请求返回时，如果 version 不匹配则丢弃。

### D. Layout Cache

缓存键至少包含：

```text
analysis_id
view_mode
visible_node_ids hash
visible_edge_ids hash
collapsed_state hash
layout_algorithm
direction
semantic_layout_version
```

## 11.3 不建议照搬的布局部分

FlowScope 传给 ELK 的主要是：

```text
node id
width
height
edge source
edge target
```

它使用：

```text
ELK Layered
LAYER_SWEEP
```

来做通用交叉最小化。

但它没有充分表达：

```text
SQL 处理阶段
主事实链路
聚合 CTE
维表分支
指标分组
边的重要性
字段端口顺序
```

当前项目应继续采用：

```text
SQL Semantic Rank
+ Dependency Lane
+ Weighted Barycenter / Median
+ Port Ordering
+ ELK/Dagre 坐标微调
```

## 11.4 推荐布局职责分工

```text
后端：
  semantic_role
  rank_hint
  lane_hint
  main_chain_score
  edge_weight
  transform_type

前端 Worker：
  同层排序
  字段排序
  虚拟节点
  坐标计算
  缓存
  增量位置复用
```

## 11.5 推荐节点语义

```text
physical_source
base_cte
enrich_cte
dedup_cte
aggregate_cte
union_cte
output_relation
output_metric
dimension_source
control_dependency
diagnostic_node
```

## 11.6 当前项目可超越 FlowScope 的方向

1. 自动识别主事实链路。
2. 自动识别粒度变化节点。
3. 简单加工链自动折叠。
4. 维表增强分支自动放入辅助泳道。
5. 指标按分子、分母、基础指标、复合指标分组。
6. 字段级 Port Ordering。
7. 显示交叉边数量和布局质量评分。
8. 根据当前聚焦字段重新局部布局，而不是全图重排。

---

# 12. GraphViewModel 与交互状态：继续坚持当前项目的分离设计

## 12.1 FlowScope 给出的正面经验

FlowScope 的 Worker 请求会接收：

```text
selectedNodeId
searchTerm
collapsedNodeIds
expandedTableIds
showColumnEdges
```

说明图构建需要考虑当前交互状态。

## 12.2 当前项目应做得更严格

建议保持三层：

### FactGraph

后端确定性血缘事实。

### GraphViewModel

某种视图下的逻辑节点和边。

### GraphInteractionState

用户当前交互：

```text
selected
highlighted
collapsed
expanded
viewport
node_positions
focus_path
search_term
```

## 12.3 状态流转

```text
FactGraph
  + ViewConfig
  → GraphViewModel

GraphViewModel
  + GraphInteractionState
  → React Flow nodes / edges / positions
```

## 12.4 关键约束

- 拖拽位置不得写回血缘事实。
- 折叠不得删除 LineageIR。
- 高亮不得修改 edge 类型。
- 搜索过滤不得修改后端结果。
- 重新分析后通过 canonical_entity_id 尽可能复用位置。
- 视图切换后保留用户聚焦实体，但不强行复用不兼容坐标。

---

# 13. API 契约与类型治理：这是 FlowScope 最成熟的工程点之一

## 13.1 FlowScope 的实践

FlowScope 使用：

```text
Rust Serialize / Deserialize
+ JsonSchema
+ API Schema Snapshot
+ Rust ↔ TypeScript Compatibility Test
```

CI 中会：

- 运行 Rust tests；
- Clippy；
- rustfmt；
- Schema Snapshot Guard；
- TypeScript Schema Compatibility；
- WASM build；
- CLI serve test；
- coverage；
- 性能门禁。

## 13.2 当前 FastAPI 项目的对应实现

推荐：

```text
Pydantic Models
  ↓
FastAPI OpenAPI
  ↓
openapi-typescript
  ↓
generated/api-types.ts
```

并增加：

```text
schema snapshot
API response contract test
frontend typecheck
backward compatibility test
```

## 13.3 建议最先冻结的模型

```text
AnalysisRequest
AnalysisResult
StatementResult
EntityRef
LineageEdge
LineagePath
Diagnostic
SourceLocation
ResolvedSchema
GraphViewModel
```

## 13.4 推荐兼容规则

| 变更 | 规则 |
|---|---|
| 新增 optional 字段 | 兼容 |
| 新增 enum 值 | 前端必须有 unknown fallback |
| 删除字段 | 升级 schema major version |
| 字段改名 | 新旧字段并存一个版本 |
| 修改字段含义 | 禁止静默修改，必须升级版本 |
| 修改 ID 生成规则 | 必须提供 migration/version |

## 13.5 建议 Schema Guard

```text
tests/contracts/
├── analysis_result.schema.json
├── graph_view_model.schema.json
├── diagnostics.schema.json
└── source_location.schema.json
```

测试要求：

```text
Pydantic model 生成 schema
  ↓
与 snapshot 比较
  ↓
变化必须显式更新
```

---

# 14. 测试体系：从“测试数量”转向“语义正确性”

## 14.1 FlowScope 可借鉴的测试层次

- Core unit tests；
- CTE bypass tests；
- Scope/self-join tests；
- SQL fixture corpus；
- Schema compatibility；
- CLI integration；
- Performance gate；
- Coverage。

## 14.2 当前项目测试体系建议

### 第一层：Parser Adapter Tests

```text
输入 SQL
→ AST / parse status
```

### 第二层：Scope Resolution Tests

```text
alias
nested subquery
CTE reuse
self join
same-name CTE
correlated scope
```

### 第三层：Expression Dependency Tests

```text
CASE
aggregate
function
window
map access
array access
UDF
arithmetic
```

### 第四层：Lineage Golden Cases

```text
input.sql
metadata.json
expected.entities.json
expected.immediate_lineage.json
expected.root_lineage.json
expected.paths.json
expected.diagnostics.json
```

### 第五层：Graph Transform Tests

```text
CTE bypass
simple projection collapse
main chain extraction
focus path
grain-change view
```

### 第六层：Layout Tests

```text
crossing count
rank correctness
lane stability
port order
position reuse
```

### 第七层：Frontend Interaction Tests

```text
drag end
collapse
expand
click graph → editor
click editor → graph
rapid re-analysis cancellation
```

## 14.3 推荐质量指标

| 指标 | 定义 |
|---|---|
| Parse Coverage | 可产生 AST 的 SQL 占比 |
| Root Lineage Precision | 根字段来源中正确项比例 |
| Root Lineage Recall | 应识别根字段中实际识别比例 |
| Path Accuracy | CTE 中间路径准确率 |
| Diagnostic Precision | 诊断是否准确指出失败阶段 |
| Exact Location Rate | 可精确定位实体的比例 |
| Partial Explainability | partial 结果是否给出明确原因 |
| Layout Crossing Count | 同一 Golden Case 的边交叉数量 |
| Position Stability | 同结构重新分析后的节点位置变化 |
| Analysis P95 | 复杂 SQL 分析 P95 耗时 |
| Graph Build P95 | GraphViewModel 构建 P95 |
| Layout P95 | 布局 P95 |

---

# 15. 性能与大 SQL：借鉴“分阶段结果 + 非阻塞 UI”

## 15.1 推荐分析过程

```text
阶段 1：预处理和 Statement 切分
阶段 2：表级血缘
阶段 3：字段级血缘
阶段 4：递归 root lineage
阶段 5：语义分析
阶段 6：GraphViewModel
阶段 7：布局
```

## 15.2 前端渐进展示

用户不必等待全部完成后才看到结果：

```text
先显示：
  SQL 已切分
  物理表和 CTE 骨架

再显示：
  字段节点和字段边

最后显示：
  语义信息、诊断、布局优化
```

即使当前 API 仍是同步，也应在内部记录阶段耗时：

```json
{
  "timings": {
    "preprocess_ms": 12,
    "parse_ms": 36,
    "scope_ms": 18,
    "lineage_ms": 64,
    "graph_ms": 22,
    "layout_ms": 91
  }
}
```

## 15.3 大图降级策略

| 条件 | 建议 |
|---|---|
| 节点少 | 完整字段图 |
| 节点中等 | 默认折叠字段 |
| 节点很多 | 先显示 CTE/表级骨架 |
| 边过多 | 自动进入 focus/path 模式 |
| 布局超时 | 使用缓存或 fast layout |
| 全量字段展开 | 明确警告并异步计算 |
| 用户快速切换 | 取消旧 graph/layout 请求 |

---

# 16. 本地部署与 EXE：借鉴 CLI Serve，而不是立即重写桌面端

## 16.1 FlowScope 的模式

FlowScope CLI 可以：

```text
读取 SQL 文件
监听目录
运行分析
启动本地 Web UI
将前端资源打包进单一二进制
```

## 16.2 当前项目的低成本对应方案

```text
Python Backend
  + 编译后的 React 静态文件
  + 本地 SQLite
  + 启动器
```

启动流程：

```text
用户运行 exe
  ↓
检查本地端口
  ↓
启动 FastAPI
  ↓
打开内置 WebView 或系统浏览器
  ↓
加载本地前端
```

## 16.3 建议先做的 CLI

```bash
lineage analyze query.sql
lineage analyze ./sql_dir --recursive
lineage serve ./sql_dir
lineage import-schema schema.sql
lineage export --format json
```

## 16.4 不要过早做的事情

- 不要为了单文件 EXE 立刻重写 Rust。
- 不要为了桌面外壳改变分析内核。
- 不要先做复杂自动更新机制。
- 不要让桌面打包阻塞解析准确率建设。

---

# 17. AI 层：借鉴“AI 消费结构化结果”，但聚焦解析可信度

## 17.1 FlowScope 的正确边界

FlowScope 的 AI Librarian 不负责生成核心血缘，而是消费：

```text
lineage
SQL
uploaded documents
```

然后回答自然语言问题。

这个边界是正确的：

> 确定性事实由解析器产生，AI 只负责解释、检索和辅助判断。

## 17.2 当前项目更适合的 AI 方向

优先级高：

1. 对抗式解析验证。
2. 断链原因诊断。
3. UDF 语义规则候选生成。
4. 主链路和粒度变化摘要。
5. 图谱折叠建议。
6. 复杂 SQL 问题定位。

优先级低：

1. 通用 SQL 聊天。
2. PDF RAG。
3. 普通自然语言转 SQL。
4. 通用 SQL Linter 解释。

## 17.3 AI 输出必须结构化

```json
{
  "task": "lineage_validation",
  "verdict": "suspected_missing_dependency",
  "output_entity_id": "output:单UV收益",
  "parser_sources": [
    "order_result.total_order_commission"
  ],
  "suggested_sources": [
    "order_result.total_order_commission",
    "search_result.show_uv"
  ],
  "evidence_locations": ["loc_001"],
  "confidence_level": "high"
}
```

AI 的结果只能：

```text
新增诊断
新增建议
提升人工审查优先级
```

不能直接静默修改事实血缘。

---

# 18. 可直接借鉴、改造后借鉴、不应照搬矩阵

## 18.1 可直接借鉴

| FlowScope 设计 | 当前项目落地 |
|---|---|
| 核心引擎与 UI 分层 | AnalysisEngine 与 GraphCanvas 分离 |
| 稳定 API 契约 | Pydantic + OpenAPI + TS 类型生成 |
| Canonical Name | canonical_entity_id |
| Relation Instance | statement/scope/alias 实例 ID |
| Scope Stack | ScopeResolver |
| Expression recursive refs | ExpressionDependencyExtractor |
| CTE bypass transform | GraphTransformPipeline |
| Imported/Implied/Resolved Schema | SQLite 元数据来源模型 |
| Structured Diagnostics | DiagnosticsCollector |
| Source spans | SourceLocation v2 |
| Flat multi-statement graph | AnalysisResult 顶层 entities/edges/statements |
| Worker graph build | GraphBuilder Worker |
| Layout cache/cancel | Layout service versioning |
| Schema snapshot tests | Contract guard |

## 18.2 改造后借鉴

| FlowScope 设计 | 需要改造的原因 |
|---|---|
| ELK/Dagre | 增加 SQL semantic rank、lane、edge weight、port order |
| Browser-only parsing | 当前保留 Python 本地服务，更适合 SQLite 和批处理 |
| Metadata JSON | 需要支持 Hive DDL、DataGrip DDL、CSV、SHOW CREATE TABLE |
| Completion API | 应绑定当前 scope 和 SQLite 元数据版本 |
| dbt/Jinja preprocessing | 改为调度变量、Hive/Spark 模板和自定义宏 |
| CLI serve | 适配 Python 后端和本地 EXE |
| AI Librarian | 改为解析验证、断链诊断、图谱简化 |
| Generic dialect semantics | 聚焦 Spark/Hive/StarRocks 生产函数和 UDF |

## 18.3 不应照搬

| 内容 | 原因 |
|---|---|
| Rust/WASM 全量迁移 | 与当前核心优先级无关 |
| 72 条 Linter 规则 | 功能扩张，且不是血缘核心壁垒 |
| PDF 文档问答 | 当前业务价值有限 |
| 多格式导出优先 | 应晚于准确率和图谱可读性 |
| 全面 VS Code 插件 | 当前 Web 工作台尚未完成核心闭环 |
| 通用多方言竞争 | 会削弱数仓生产 SQL 专项优势 |
| O'Saasy App 源码复制 | 许可和产品差异问题 |

---

# 19. 推荐目标架构

```text
┌─────────────────────────────────────────────┐
│                Input Layer                  │
│ SQL Text / SQL Files / Directory / DDL      │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│           Preprocess & Segmentation         │
│ Template / ADD JAR / TEMP FUNCTION / Vars   │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│              SQLGlot Adapter                │
│ ParseResult + AST + Token/Location Mapping  │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│             Analysis Orchestrator           │
│ Scope / Metadata / Name / Expression        │
│ Lineage / Semantics / Diagnostics           │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│               Analysis IR                   │
│ Statements / Entities / Edges / Paths       │
│ Locations / Diagnostics / Resolved Schema   │
└──────────────┬────────────────┬─────────────┘
               ↓                ↓
┌───────────────────────┐  ┌───────────────────────┐
│ Graph Transform       │  │ SQLite Persistence    │
│ CTE Bypass            │  │ Canonical Entities    │
│ Root Rollup           │  │ Scripts / Jobs        │
│ Simplification        │  │ Cross-script Edges    │
└──────────────┬────────┘  └──────────────┬────────┘
               ↓                          ↓
┌─────────────────────────────────────────────┐
│              GraphViewModel                 │
│ rank / lane / role / weight / port hints    │
└──────────────────────┬──────────────────────┘
                       ↓
┌─────────────────────────────────────────────┐
│          Frontend Graph Pipeline            │
│ Worker Build / Layout / Cache / Cancel      │
│ Interaction Store / Monaco Linkage          │
└─────────────────────────────────────────────┘
```

---

# 20. 推荐模块清单

## 20.1 后端新增或重构

```text
domain/models/
  entity.py
  relation_instance.py
  lineage_edge.py
  lineage_path.py
  resolved_schema.py
  diagnostic.py
  source_location.py

application/
  analysis_orchestrator.py
  analysis_result_builder.py

services/
  scope_resolver.py
  expression_dependency_extractor.py
  derived_relation_schema_builder.py
  lineage_engine.py
  lineage_rollup_service.py
  graph_transform_pipeline.py
  semantic_role_classifier.py

transforms/
  cte_bypass_transform.py
  projection_collapse_transform.py
  main_chain_transform.py
  focus_path_transform.py

repositories/
  metadata_repository.py
  lineage_repository.py
  project_repository.py
```

## 20.2 前端新增或重构

```text
src/graph/
  adapters/
    graphViewModelAdapter.ts
  workers/
    graphBuilder.worker.ts
    semanticLayout.worker.ts
  layout/
    semanticRank.ts
    laneAssignment.ts
    crossingMinimizer.ts
    portOrder.ts
    layoutCache.ts
  state/
    graphInteractionStore.ts
  views/
    FullLineageView.tsx
    RootLineageView.tsx
    MetricView.tsx
    GrainChangeView.tsx
```

---

# 21. 分阶段实施路线

## 阶段 A：稳定领域模型与契约

### 目标

先确保后端输出模型可以长期演进。

### 任务

1. 定义 canonical_entity_id。
2. 定义 relation_instance_id。
3. 定义 StatementResult、Entity、LineageEdge、LineagePath。
4. 定义 SourceLocation v2。
5. 定义 ResolvedSchema 和 MetadataOrigin。
6. 生成 OpenAPI 和 TypeScript 类型。
7. 添加 Schema Snapshot。
8. GraphViewModel 与 GraphInteractionState 分离。

### 验收

- 前端不再手写 AnalysisResult 类型。
- 同一个物理字段跨语句使用相同 canonical ID。
- Self Join 产生不同 instance ID。
- CTE 不跨 statement 合并。
- API schema 变化会使测试失败。

---

## 阶段 B：完善 Scope 与表达式血缘

### 目标

解决复杂 SQL 的核心准确率问题。

### 任务

1. Scope Stack。
2. Alias Instance。
3. CTE definition/reference 分离。
4. DerivedRelationSchema。
5. 多输入 ColumnDependency。
6. CASE、聚合、函数、CAST、Map、Array。
7. PendingWildcard。
8. UDF 参数依赖默认规则。
9. Diagnostic stage。

### 验收

- 多层 CTE 可穿透。
- CTE Self Join 不串线。
- 比率指标识别多个输入。
- `count(distinct case when...)` 抽取条件字段和结果字段。
- `select *` 无元数据时返回 partial，不崩溃。
- 字段歧义不猜测。

---

## 阶段 C：建立事实图与图变换体系

### 目标

将“解析正确”与“展示清楚”解耦。

### 任务

1. FactGraph。
2. immediate/root/path 三类血缘。
3. CTE bypass。
4. 简单投影折叠。
5. ViewConfig。
6. 变换 provenance。
7. 主链路和聚焦路径。
8. 粒度变化分类。

### 验收

- 切换隐藏 CTE 不修改原始血缘。
- 简化边可以展开查看原始路径。
- root view 与 full path view 可切换。
- 相同 AnalysisResult 可生成多个 GraphViewModel。

---

## 阶段 D：图谱性能与布局

### 目标

让复杂 SQL 图谱在浏览器中稳定运行。

### 任务

1. Graph Builder Worker。
2. Semantic Layout Worker。
3. 请求取消。
4. 布局缓存。
5. fast layout。
6. 语义 rank。
7. lane。
8. Weighted Barycenter / Median。
9. Port Ordering。
10. 节点位置复用。

### 验收

- 快速连续分析不会展示旧结果。
- 折叠展开不会阻塞主线程。
- 同一结构重复布局可命中缓存。
- Golden Case 的交叉边数量低于基线。
- 节点拖拽后重新分析可复用位置。

---

## 阶段 E：多文件和 SQLite 全仓图

### 目标

从单 SQL 分析升级为本地数仓代码地图。

### 任务

1. source_name 和 script_id。
2. 多 Statement Flat Graph。
3. Canonical Entity merge。
4. Cross Script Edge。
5. SQLite schema。
6. 目录扫描。
7. 增量重解析。
8. 影响分析。
9. 脚本版本和 diff。

### 验收

- 同一表跨多个脚本只生成一个 canonical entity。
- 可以查找表的生产者和消费者。
- 可以查找字段的跨脚本路径。
- 修改一个脚本后只重算受影响部分。
- partial 脚本不会污染确定性边。

---

## 阶段 F：产品外壳与 AI

### 目标

在确定性能力稳定后扩展使用入口。

### 任务

1. CLI。
2. Local Serve。
3. 本地 EXE。
4. 目录监听。
5. AI 对抗验证。
6. UDF 规则建议。
7. 图谱简化建议。

### 验收

- CLI、Web 和 EXE 输出相同 AnalysisResult。
- AI 不直接修改事实图。
- AI 结论必须引用 Entity ID 和 SourceLocation。
- 所有 AI 建议均可人工接受或拒绝。

---

# 22. 建议加入主需求文档的新增条目

建议不要把 FlowScope 所有功能逐条加入需求文档，而是新增以下九个正式工程条目：

| ID 建议 | 条目 |
|---|---|
| R19 | Canonical Entity 与 Relation Instance |
| R20 | Scope Stack 与实例感知名称解析 |
| R21 | Imported / Implied / Resolved Metadata |
| R22 | FactGraph 与 GraphTransformPipeline |
| R23 | Multi-Statement Flat Graph |
| R24 | Graph Builder / Layout Worker |
| R25 | Schema Snapshot 与前后端兼容测试 |
| R26 | Analysis / Graph / Layout 性能门禁 |
| R27 | CLI Local Serve 与目录扫描 |

注意：

- 可以作为现有 R04、R05、R07、R10、R17 的子条目，而不一定全部新增主编号。
- 主文档仍应控制体量。
- 每个条目只保留目标、模型边界和最小验收。
- 具体算法和代码实现放入独立设计文档。

---

# 23. 建议优先阅读的 FlowScope 源码

## 23.1 核心分析与模型

```text
crates/flowscope-core/src/types/response.rs
crates/flowscope-core/src/analyzer/context.rs
crates/flowscope-core/src/analyzer/expression.rs
crates/flowscope-core/src/analyzer/query.rs
crates/flowscope-core/src/analyzer/global.rs
crates/flowscope-core/src/analyzer/transform.rs
```

关注：

- AnalyzeResult；
- Node / Edge；
- canonical_name；
- statement_ids；
- Scope；
- RelationInstance；
- CTE definitions；
- PendingWildcard；
- expression refs；
- flatten_lineages；
- filter_cte_nodes。

## 23.2 前端图谱与性能

```text
packages/react/src/utils/layout.ts
packages/react/src/utils/graphBuilderWorkerService.ts
packages/react/src/workers/graphBuilder.worker.ts
packages/react/src/utils/graphBuilders.ts
packages/react/src/utils/lineageHelpers.ts
```

关注：

- Web Worker；
- layout cache；
- cancel pending；
- dynamic node height；
- Dagre / ELK；
- LAYER_SWEEP；
- table/column/script view 转换。

## 23.3 契约和 CI

```text
docs/api_schema.json
docs/workspace-structure.md
.github/workflows/ci.yml
scripts/check_schema_sync.sh
crates/flowscope-core/tests/schema_guard.rs
packages/core/src/schema-compat.test.ts
```

关注：

- API snapshot；
- Rust ↔ TS schema compatibility；
- performance budget；
- WASM build；
- CLI integration。

---

# 24. 许可边界

FlowScope 的许可需要分开看：

```text
核心 engine 和 packages：
Apache-2.0

app/：
O'Saasy License
```

建议：

- 可以研究并按 Apache-2.0 要求借鉴核心 engine 和 packages 的实现思想或代码。
- 不应直接复制 `app/` 的完整应用源码和产品页面。
- 即使代码许可允许，也应优先借鉴模型和架构，而不是直接复制，以避免将 FlowScope 的产品假设带入当前 Spark/Hive 项目。
- 如实际复用代码，需保留版权声明和许可证文件，并单独进行许可证审查。

---

# 25. 最终建议

FlowScope 对当前项目最大的价值，不是提供一张“功能清单”，而是给出一个已经被实践验证的工程参照：

```text
SQL 血缘工具要达到产品级
不能只有 Parser + Graph
还必须有：
  作用域
  实例身份
  稳定契约
  元数据来源
  诊断
  SourceLocation
  图变换
  多文件模型
  性能治理
  测试门禁
  多种消费入口
```

当前项目不应转向模仿 FlowScope 的完整产品，而应该采取下面的路线：

```text
借鉴 FlowScope：
  工程边界
  数据模型
  作用域解析
  图变换
  多文件图
  性能治理
  契约测试

保留当前项目优势：
  SQLGlot + Python
  Spark/Hive 生产 SQL
  SQLite 本地元数据
  复杂脚本清洗
  语义化低交叉布局
  粒度变化分析
  主链路识别
  血缘可信度和断链诊断
```

最终产品应形成的差异是：

> FlowScope 更擅长将通用 SQL 转换成完整、可交互的本地血缘图；当前项目应更擅长将复杂数仓生产脚本转换成可验证、可简化、可排错、可进行影响分析的数据加工地图。

---

# 26. 参考依据索引

## FlowScope 官方仓库

- `README.md`：产品能力、Web/CLI/Serve、核心组件和许可说明。
- `docs/workspace-structure.md`：Monorepo 和包依赖结构。
- `docs/guides/schema-metadata.md`：Schema metadata 与 best-effort 行为。
- `docs/dialect-coverage.md`：方言、语句类型和 partial 行为。
- `crates/flowscope-core/src/types/response.rs`：AnalyzeResult、Node、canonical_name、statement_ids、span。
- `crates/flowscope-core/src/analyzer/context.rs`：Scope、RelationInstance、CTE、PendingWildcard。
- `crates/flowscope-core/src/analyzer/expression.rs`：表达式字段依赖递归抽取。
- `crates/flowscope-core/src/analyzer/global.rs`：多语句 flatten、canonical merge 和 cross-statement edges。
- `crates/flowscope-core/src/analyzer/transform.rs`：CTE bypass graph transform。
- `packages/react/src/utils/layout.ts`：Dagre、ELK、LAYER_SWEEP、缓存。
- `packages/react/src/utils/graphBuilderWorkerService.ts`：Graph Builder Worker、pending request、取消。
- `.github/workflows/ci.yml`：测试、schema compatibility、性能门禁、CLI serve、coverage。

## 当前项目文档

- `sql_lineage_workbench_requirement_breakdown_v0.7_delta.md`
- `sql_lineage_workbench_v0.7_delta_review.md`
- 当前 CTE 递归列级血缘设计与 Barycenter/Median 布局设计交付包。

---

# 27. 一页式执行摘要

## 现在立刻做

```text
1. 冻结 AnalysisResult / Entity / Edge / Path 契约
2. 区分 canonical entity 与 relation instance
3. 建立 Scope Stack
4. 将字段血缘升级为多输入依赖
5. 保留 fact graph，图简化改为 transform
6. 建立 imported / implied / resolved metadata
7. 加入 schema snapshot 和 TS compatibility
```

## 下一步做

```text
8. 多 Statement flat graph
9. CTE bypass / projection collapse
10. SourceLocation occurrence model
11. Graph Builder Worker
12. Layout cache / cancel / version
13. Semantic rank + lane + port ordering
14. Golden Case + performance gate
```

## 暂时不做

```text
15. Rust/WASM 重写
16. 通用 SQL Linter
17. VS Code 插件
18. PDF RAG
19. 大量导出格式
20. 全方言竞争
```

## 最终目标

```text
复杂 Spark/Hive 生产 SQL
  → 可信解析
  → 可追踪字段路径
  → 可简化语义图
  → 全仓跨脚本影响分析
```
