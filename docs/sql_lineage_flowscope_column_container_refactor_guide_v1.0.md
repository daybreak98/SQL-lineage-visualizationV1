# SQL 血缘图 FlowScope 风格列容器改造开发指南

> 版本：v1.0  
> 目标项目：SQL-lineage-visualizationV1 前端  
> 面向执行者：Codex / 前端开发工程师  
> 改造类型：前端图投影、节点渲染、动态布局与字段端口路由  
> 默认实施范围：P0——物理源表字段到 Query Result 输出字段的容器化列血缘

---

## 1. 文档目标

本次改造要将当前列级血缘视图：

```text
物理表节点 → 独立输出字段节点 → Query Result 节点
```

升级为 FlowScope 风格的关系容器视图：

```text
物理表容器
├── 源字段行
├── 源字段行
└── 源字段行
        ↓ 字段端口连线
Query Result 容器
├── 输出字段行
├── 输出字段行
└── 输出字段行
```

核心原则：

1. **表、CTE、子查询、Query Result 是画布主节点。**
2. **字段是主节点内部的 ColumnRow，不再作为普通画布节点散落。**
3. **字段级边通过 `sourcePort` / `targetPort` 精确连接字段行。**
4. **后端血缘事实图保持不变，前端增加一层展示投影。**
5. **保留现有自研 HTML 节点 + SVG 边 + 布局 + 动画体系，不引入 React Flow。**

---

## 2. 当前源码架构确认

本方案基于当前上传前端源码制定。现有关键链路如下：

```text
/api/sql/analyze
    ↓
BackendAnalysisResult.graph_view_model
    ↓
normalizeBackendGraph()
    ↓
WorkbenchState.backendGraph
    ↓
visibleGraph(state)
    ├── visibleTableGraph()
    ├── visibleSubqueryGraph()
    └── visibleColumnGraph()
    ↓
layoutComfortGraph() / layoutColumnLineage()
    ↓
LineageCanvas
    ├── HTML .node
    └── SVG .edge-layer
```

### 2.1 当前列级血缘实现

文件：

```text
src/graphPipeline.ts
```

当前 `visibleColumnGraph()` 的行为是：

1. 保留 `output_field`、`output`、`expression`、`unknown`；
2. 遇到 `physical_column → output_field` 的 projection 边时；
3. 根据 `physical_column:table.column` 推断所属 `physical_table:table`；
4. 隐藏物理列节点；
5. 将边改写为：

```text
physical_table → output_field
```

因此当前列视图已经实现了“列归属表”的初步聚合，但丢失了源字段端口信息。

### 2.2 当前节点尺寸模型

文件：

```text
src/nodeVisualTokens.ts
```

当前所有节点均使用固定高度：

```typescript
height: 45
```

FlowScope 风格节点包含可变数量的字段行，因此必须改成动态高度。

### 2.3 当前边路由模型

文件：

```text
src/graphComfortLayout.ts
```

当前边锚点由节点左右边界和“同节点多边排序偏移”计算：

```text
source node right/left center + portAnchorOffset
    →
target node left/right center + portAnchorOffset
```

它不知道某条边属于哪个字段行。因此需要新增字段级端口坐标。

### 2.4 当前画布与动画

文件：

```text
src/components/LineageCanvas.tsx
src/graphTransition.ts
src/useGraphTransition.ts
```

当前已经具备：

- 稳定实体 ID；
- enter / persist / exit 分类；
- `requestAnimationFrame` 坐标插值；
- 节点淡入、淡出、缩放；
- 边跟随每帧位置重新计算；
- 拖拽时取消动画；
- 大图动画降级。

本次必须复用这些能力，不另建第二套动画系统。

---

## 3. 改造结论与边界

## 3.1 可以实现

当前后端已经提供 P0 所需事实：

```text
physical_table
physical_column
output_column / output_field
output
column_lineage / projection
output_column_to_result / output
```

因此可以在不修改后端的前提下实现：

```text
物理表字段行 → Query Result 输出字段行
```

## 3.2 P0 不修改的模块

禁止为本功能修改以下部分：

```text
/api/sql/analyze
BackendAnalysisResult 主接口
SQLGlot 解析主流程
name_resolver
cte_column_rollup_service
SQLite 元数据仓储
Monaco SQL 编辑器
方言转换页面
```

## 3.3 P0 暂不实现

以下内容留到 P1/P2：

- CTE 内部字段容器；
- 子查询内部字段容器；
- 全表元数据字段展开；
- 字段数据类型、注释的完整展示；
- 将表达式完全折叠为边标签；
- React Flow 迁移；
- 后端新增 `owner_entity_id` 强契约。

---

## 4. 目标交互效果

## 4.1 表级模式

```text
┌──────────────────┐              ┌──────────────────┐
│ dwd_order_di     │─────────────▶│ Query Result     │
└──────────────────┘              └──────────────────┘
```

## 4.2 列级模式

```text
┌──────────────────────────┐
│ TBL  dwd_order_di        │
├──────────────────────────┤
│ order_no              ●──┼──────────────┐
│ user_id               ●──┼──────────┐   │
│ amount                ●──┼──────┐   │   │
└──────────────────────────┘      │   │   │
                                  │   │   │
                         ┌────────▼───▼───▼────────┐
                         │ OUT  Query Result       │
                         ├──────────────────────────┤
                         │ order_no             ●  │
                         │ uid                  ●  │
                         │ total_amount         ●  │
                         └──────────────────────────┘
```

## 4.3 折叠行为

展开时：

```text
source column row → output column row
```

任一容器折叠时：

```text
source relation → target relation
```

降级后的表级边必须按关系对去重，避免一张表的 30 个字段生成 30 条重叠表边。

## 4.4 选择行为

- 单击表头：选择关系实体；
- 单击字段行：选择字段实体；
- 双击字段行：继续触发现有源码定位或 DetailPanel 行为；
- 单击折叠按钮：只切换容器展开状态，不选择节点；
- 拖拽：拖动整个关系容器；
- 字段行不得单独拖拽。

---

## 5. 目标架构

```text
Backend Flat Graph
│
├── physical_table
├── physical_column
├── output_field
├── output
├── expression
└── edges
        │
        ▼
buildRelationColumnProjection()
        │
        ├── resolve column owner
        ├── group columns into relation nodes
        ├── preserve expression nodes
        ├── convert column edges to relation-port edges
        ├── filter unrelated wide-table columns
        └── collapse fallback + edge dedup
        │
        ▼
RelationColumnGraph
│
├── relation nodes with columns[]
├── expression nodes
└── edges with sourcePort / targetPort
        │
        ▼
layoutComfortGraph()
│
├── dynamic node box
├── variable-height collision packing
└── relation-level DAG layout
        │
        ▼
LineageCanvas
│
├── RelationNodeCard
├── ColumnRow
└── SVG field-port edges
```

重要约束：

```text
WorkbenchState.backendGraph 仍然是后端事实图。
RelationColumnGraph 只是 visibleGraph 的派生结果，不能写回 backendGraph。
```

---

## 6. 数据模型改造

文件：

```text
src/types/lineage.ts
```

## 6.1 新增字段行模型

```typescript
export type GraphColumnRole =
  | 'source'
  | 'output'
  | 'derived'
  | 'unknown';

export interface GraphColumnRow {
  /** 字段稳定实体 ID，同时也是字段端口 ID */
  entityId: string;

  /** 展示名称 */
  label: string;

  /** 所属表、CTE、子查询或输出容器 ID */
  ownerEntityId: string;

  role: GraphColumnRole;

  ordinal?: number;
  dataType?: string;
  comment?: string;
  expression?: string;

  /** 是否实际存在可见字段血缘边 */
  connected?: boolean;

  /** 后续可用于字段级告警与置信度 */
  warning?: boolean;
  confidence?: 'high' | 'medium' | 'low' | 'unknown';
}
```

## 6.2 扩展 GraphNode

```typescript
export interface GraphNode {
  id: string;
  entityId: string;
  type:
    | 'table'
    | 'column'
    | 'cte'
    | 'subquery'
    | 'output'
    | 'output_field'
    | 'expression'
    | 'unknown';
  label: string;
  tag?: string;
  x: number;
  y: number;
  pinned?: boolean;
  ordinal?: number;
  rank?: number;
  lane?: string;
  semanticRole?: string;
  orderInRank?: number;

  /** 新增：关系容器中的字段行 */
  columns?: GraphColumnRow[];

  /** 新增：容器是否折叠 */
  collapsed?: boolean;

  /** 新增：因宽表过滤而隐藏的字段数 */
  hiddenColumnCount?: number;

  /** 可选：显式尺寸，便于布局缓存与动画 */
  width?: number;
  height?: number;
}
```

## 6.3 扩展 GraphEdge

```typescript
export interface GraphEdge {
  id: string;

  /** 主节点 ID：表、CTE、子查询、Output、Expression */
  source: string;
  target: string;

  /** 字段端口 ID；为空表示连接容器级端口 */
  sourcePort?: string;
  targetPort?: string;

  /** 保留后端原始字段实体，便于诊断和选择 */
  originalSourceEntityId?: string;
  originalTargetEntityId?: string;

  type:
    | 'table'
    | 'cte'
    | 'subq'
    | 'output'
    | 'expr'
    | 'join'
    | 'projection'
    | 'alias'
    | 'unknown';

  mapping?: string;
  synthetic?: boolean;
  sourcePortOrder?: number;
  targetPortOrder?: number;
}
```

## 6.4 WorkbenchState 增加折叠状态

不要直接修改 `backendGraph` 节点上的 `collapsed` 作为唯一真相。折叠属于交互状态，应存放在 WorkbenchState。

推荐使用普通对象，避免 Set 在状态复制、调试和序列化时产生额外问题：

```typescript
export interface WorkbenchState {
  // ...existing fields

  collapsedRelationIds: Record<string, true>;
  columnContainerMode: 'legacy' | 'relation_rows';
}
```

初始值：

```typescript
collapsedRelationIds: {},
columnContainerMode: 'relation_rows',
```

保留 `legacy` 是为了快速回滚。

---

## 7. 前端投影构建

主要文件：

```text
src/graphPipeline.ts
```

建议将新逻辑拆出：

```text
src/relationColumnProjection.ts
```

避免继续膨胀 `graphPipeline.ts`。

## 7.1 新建核心类型

```typescript
export interface BuildRelationColumnProjectionOptions {
  collapsedRelationIds: Record<string, true>;
  selectedEntityId?: string | null;
  searchTerm?: string;
  columnFilterThreshold?: number;
}
```

## 7.2 解析物理列所属表

P0 后端尚未提供 `owner_entity_id`，采用兼容解析：

```typescript
export function parsePhysicalColumnOwner(
  columnEntityId: string,
): { ownerEntityId: string; columnName: string } | null {
  const prefix = 'physical_column:';
  if (!columnEntityId.startsWith(prefix)) return null;

  const qualified = columnEntityId.slice(prefix.length);
  const lastDot = qualified.lastIndexOf('.');
  if (lastDot <= 0 || lastDot === qualified.length - 1) return null;

  const tableName = qualified.slice(0, lastDot);
  const columnName = qualified.slice(lastDot + 1);

  return {
    ownerEntityId: `physical_table:${tableName}`,
    columnName,
  };
}
```

要求：

- 不要使用第一个 `.` 分割；
- 必须使用最后一个 `.`；
- 支持 `catalog.schema.table.column`；
- 解析失败时不得静默丢弃，应保留为 unknown 或加入 diagnostics。

## 7.3 输出字段所属容器

P0 默认所有 `output_field` 归属最终 `output`：

```typescript
function resolveOutputOwner(
  base: GraphLike,
  outputFieldId: string,
): string | null {
  const direct = base.edges.find(
    edge => edge.source === outputFieldId && edge.type === 'output',
  );

  if (direct) return direct.target;

  return base.nodes.find(node => node.type === 'output')?.entityId ?? null;
}
```

优先使用真实 `output_field → output` 边，不要写死 `out:query_result`。

## 7.4 构建 ColumnRow

```typescript
function toSourceColumnRow(
  columnNode: GraphNode,
  ownerEntityId: string,
): GraphColumnRow {
  return {
    entityId: columnNode.entityId,
    label: parsePhysicalColumnOwner(columnNode.entityId)?.columnName
      ?? columnNode.label,
    ownerEntityId,
    role: 'source',
    ordinal: columnNode.ordinal,
  };
}

function toOutputColumnRow(
  fieldNode: GraphNode,
  ownerEntityId: string,
): GraphColumnRow {
  return {
    entityId: fieldNode.entityId,
    label: fieldNode.label,
    ownerEntityId,
    role: 'output',
    ordinal: fieldNode.ordinal,
  };
}
```

排序规则：

```text
1. ordinal 有值时按 ordinal；
2. ordinal 相同或缺失时按 label；
3. 排序必须稳定，避免切换时字段行跳动。
```

## 7.5 构建关系容器

伪代码：

```typescript
export function buildRelationColumnProjection(
  base: GraphLike,
  options: BuildRelationColumnProjectionOptions,
): GraphLike {
  const nodeById = new Map(base.nodes.map(node => [node.entityId, node]));
  const containerById = new Map<string, GraphNode>();
  const columnOwnerById = new Map<string, string>();

  // 1. 保留物理表、output，以及 P0 中仍需独立展示的 expression/unknown
  for (const node of base.nodes) {
    if (node.type === 'table' || node.type === 'output') {
      containerById.set(node.entityId, {
        ...node,
        columns: [],
        collapsed: Boolean(options.collapsedRelationIds[node.entityId]),
      });
    }
  }

  // 2. 将 physical_column 放入物理表
  for (const node of base.nodes) {
    if (node.type !== 'column') continue;

    const owner = parsePhysicalColumnOwner(node.entityId);
    if (!owner) continue;

    let container = containerById.get(owner.ownerEntityId);
    if (!container) {
      container = createSyntheticTableContainer(owner.ownerEntityId);
      containerById.set(owner.ownerEntityId, container);
    }

    container.columns!.push(toSourceColumnRow(node, owner.ownerEntityId));
    columnOwnerById.set(node.entityId, owner.ownerEntityId);
  }

  // 3. 将 output_field 放入 output
  for (const node of base.nodes) {
    if (node.type !== 'output_field') continue;

    const ownerId = resolveOutputOwner(base, node.entityId);
    if (!ownerId) continue;

    const output = containerById.get(ownerId);
    if (!output) continue;

    output.columns!.push(toOutputColumnRow(node, ownerId));
    columnOwnerById.set(node.entityId, ownerId);
  }

  // 4. 转换字段边
  const projectedEdges = buildProjectedColumnEdges(
    base,
    columnOwnerById,
    containerById,
    options,
  );

  // 5. 表达式节点：P0 保持独立
  const expressionNodes = base.nodes.filter(
    node => node.type === 'expression' || node.type === 'unknown',
  );

  // 6. 字段过滤与排序
  const containers = Array.from(containerById.values()).map(container =>
    finalizeContainerColumns(container, projectedEdges, options),
  );

  return {
    nodes: [...containers, ...expressionNodes],
    edges: projectedEdges,
  };
}
```

---

## 8. 字段边投影

## 8.1 普通字段到字段

后端：

```text
physical_column:T.a → output_field:x
```

前端展示边：

```typescript
{
  id: originalEdge.id,
  source: 'physical_table:T',
  target: 'out:query_result',
  sourcePort: 'physical_column:T.a',
  targetPort: 'output_field:x',
  originalSourceEntityId: 'physical_column:T.a',
  originalTargetEntityId: 'output_field:x',
  type: 'projection',
  mapping: originalEdge.mapping,
}
```

## 8.2 表达式节点

P0 保留表达式节点。支持两种边：

```text
source column row → expression node
expression node → output column row
```

当一端是字段，一端是普通节点时：

```typescript
{
  source: sourceOwnerId,
  sourcePort: sourceColumnId,
  target: expressionNodeId,
}
```

或：

```typescript
{
  source: expressionNodeId,
  target: outputOwnerId,
  targetPort: outputFieldId,
}
```

不要为了容器化而删除 expression 实体，否则会破坏表达式选择、源码定位和诊断。

## 8.3 折叠降级

```typescript
function degradeColumnEdgeIfCollapsed(
  edge: GraphEdge,
  sourceNode: GraphNode,
  targetNode: GraphNode,
): GraphEdge {
  if (!sourceNode.collapsed && !targetNode.collapsed) return edge;

  return {
    ...edge,
    id: `collapsed:${edge.source}->${edge.target}`,
    sourcePort: undefined,
    targetPort: undefined,
    originalSourceEntityId:
      edge.originalSourceEntityId ?? edge.sourcePort,
    originalTargetEntityId:
      edge.originalTargetEntityId ?? edge.targetPort,
    synthetic: true,
  };
}
```

降级后去重键：

```typescript
const key = `${edge.source}->${edge.target}:${edge.type}`;
```

注意：去重时不要只用 `source->target`，否则 join、projection、expression 等语义可能互相覆盖。

---

## 9. 宽表字段过滤

新增常量：

```typescript
export const COLUMN_CONTAINER = {
  filterThreshold: 30,
  hardRenderLimit: 120,
};
```

规则：

### 字段数不超过 30

展示容器内全部后端已返回字段。

### 字段数超过 30

只展示：

1. 当前有可见边的字段；
2. 当前选中的字段；
3. 搜索命中的字段；
4. 有诊断的字段；
5. 必要时保留首尾少量上下文字段。

返回：

```typescript
{
  columns: visibleColumns,
  hiddenColumnCount: allColumns.length - visibleColumns.length,
}
```

P0 后端通常只返回参与血缘的物理列，因此 `hiddenColumnCount` 可能为 0，但结构必须提前保留。

不得在列级血缘模式对字段端口区域使用 DOM 虚拟列表。被连线的字段行必须真实存在，否则 SVG 无法获得稳定端口位置。

---

## 10. 动态节点尺寸

主要文件：

```text
src/nodeVisualTokens.ts
```

## 10.1 新增容器尺寸常量

```typescript
export const RELATION_NODE_GEOMETRY = {
  tableWidth: 236,
  outputWidth: 236,
  headerHeight: 48,
  rowHeight: 26,
  bodyPaddingTop: 5,
  bodyPaddingBottom: 5,
  hiddenBadgeHeight: 24,
  collapsedHeight: 48,
  radius: 12,
};
```

## 10.2 修改 getComfortNodeBox

当前函数接收 `type: string`，无法根据字段数量计算高度。改为同时支持节点对象：

```typescript
export function getComfortNodeBox(
  nodeOrType: GraphNode | string,
): { width: number; height: number; radius: number } {
  const type = typeof nodeOrType === 'string'
    ? nodeOrType
    : nodeOrType.type;

  if (typeof nodeOrType !== 'string') {
    const node = nodeOrType;
    const isRelationContainer =
      node.type === 'table' ||
      node.type === 'cte' ||
      node.type === 'subquery' ||
      node.type === 'output';

    if (isRelationContainer && node.columns) {
      if (node.collapsed) {
        return {
          width: node.type === 'output'
            ? RELATION_NODE_GEOMETRY.outputWidth
            : RELATION_NODE_GEOMETRY.tableWidth,
          height: RELATION_NODE_GEOMETRY.collapsedHeight,
          radius: RELATION_NODE_GEOMETRY.radius,
        };
      }

      const hiddenBadgeHeight = node.hiddenColumnCount
        ? RELATION_NODE_GEOMETRY.hiddenBadgeHeight
        : 0;

      return {
        width: node.type === 'output'
          ? RELATION_NODE_GEOMETRY.outputWidth
          : RELATION_NODE_GEOMETRY.tableWidth,
        height:
          RELATION_NODE_GEOMETRY.headerHeight +
          RELATION_NODE_GEOMETRY.bodyPaddingTop +
          node.columns.length * RELATION_NODE_GEOMETRY.rowHeight +
          RELATION_NODE_GEOMETRY.bodyPaddingBottom +
          hiddenBadgeHeight,
        radius: RELATION_NODE_GEOMETRY.radius,
      };
    }
  }

  return COMFORT_NODE_BOX[type] ?? COMFORT_NODE_BOX.unknown;
}
```

## 10.3 nodeBox API 修改

`src/graphPipeline.ts`：

```typescript
export function nodeBox(node: GraphNode) {
  const box = getComfortNodeBox(node);
  return { width: box.width, height: box.height };
}
```

不要继续只传 `node.type`。

## 10.4 全量替换调用方

必须搜索：

```text
getComfortNodeBox(
nodeBox(
```

将涉及节点真实尺寸的调用全部改为传节点对象，包括：

- `graphComfortLayout.ts`；
- `LineageCanvas.tsx`；
- graph bounds；
- collision；
- edge routing；
- fit / center；
- 测试辅助函数。

只在纯样式 token 查询时允许继续传字符串。

---

## 11. 动态高度布局

主要文件：

```text
src/graphComfortLayout.ts
```

## 11.1 当前问题

当前高度估算：

```typescript
maxGroupSize * minNodeGap + tallestNode
```

当前碰撞处理：

```typescript
if (current.y - previous.y < minGap) {
  current.y = previous.y + minGap;
}
```

这只适合固定高度节点。字段容器高度不同时会互相重叠。

## 11.2 新的层内打包算法

```typescript
function packVariableHeightNodes(
  nodes: GraphNode[],
  startY: number,
  gap: number,
): number {
  if (!nodes.length) return startY;

  let cursor = startY;

  for (const node of nodes) {
    const box = getComfortNodeBox(node);
    node.y = cursor + box.height / 2;
    cursor += box.height + gap;
  }

  return cursor;
}
```

## 11.3 层高度计算

```typescript
function calculateLevelContentHeight(
  nodes: GraphNode[],
  gap: number,
): number {
  if (!nodes.length) return 0;

  const nodeHeight = nodes.reduce(
    (sum, node) => sum + getComfortNodeBox(node).height,
    0,
  );

  return nodeHeight + Math.max(0, nodes.length - 1) * gap;
}
```

画布高度：

```typescript
const maxLevelHeight = Math.max(
  ...Array.from(groups.values()).map(group =>
    calculateLevelContentHeight(group, cfg.minNodeGap),
  ),
);

const height = Math.max(
  cfg.minHeight,
  cfg.marginY * 2 + maxLevelHeight,
);
```

## 11.4 层内垂直居中

```typescript
for (const [level, list] of groups.entries()) {
  const contentHeight = calculateLevelContentHeight(list, cfg.minNodeGap);
  const startY = cfg.marginY + (height - cfg.marginY * 2 - contentHeight) / 2;

  packVariableHeightNodes(list, startY, cfg.minNodeGap);

  for (const node of list) {
    node.x = Math.min(
      width - cfg.marginX,
      cfg.marginX + level * rankGap,
    );
  }
}
```

## 11.5 Barycenter 保持

现有 4 轮上下扫描 Barycenter 排序继续保留。动态高度只替换坐标分配和碰撞部分，不修改层次计算与排序逻辑。

---

## 12. 字段端口坐标与边路由

主要文件：

```text
src/graphComfortLayout.ts
```

## 12.1 字段行中心坐标

```typescript
export function getColumnPortOffsetY(
  node: GraphNode,
  portEntityId: string,
): number | null {
  if (node.collapsed || !node.columns?.length) return null;

  const index = node.columns.findIndex(
    column => column.entityId === portEntityId,
  );

  if (index < 0) return null;

  const box = getComfortNodeBox(node);
  const top = -box.height / 2;

  return (
    top +
    RELATION_NODE_GEOMETRY.headerHeight +
    RELATION_NODE_GEOMETRY.bodyPaddingTop +
    index * RELATION_NODE_GEOMETRY.rowHeight +
    RELATION_NODE_GEOMETRY.rowHeight / 2
  );
}
```

返回相对节点中心的 Y 偏移，便于动画时只替换节点中心坐标。

## 12.2 路由优先级

```text
1. edge.sourcePort 存在且源容器展开：使用字段行 Y；
2. 否则使用现有节点级 portAnchorOffset；
3. edge.targetPort 同理；
4. 端口不存在时必须安全降级，不得产生 NaN 路径。
```

## 12.3 routeComfortEdgePath 修改

```typescript
const sourceColumnOffset = edge.sourcePort
  ? getColumnPortOffsetY(sourceNode, edge.sourcePort)
  : null;

const targetColumnOffset = edge.targetPort
  ? getColumnPortOffsetY(targetNode, edge.targetPort)
  : null;

const sourceOffsetY = sourceColumnOffset ?? fallbackSourceOffset;
const targetOffsetY = targetColumnOffset ?? fallbackTargetOffset;
```

X 坐标继续使用节点左右边界：

```typescript
const sx = isForward
  ? sourceNode.x + sourceBox.width / 2
  : sourceNode.x - sourceBox.width / 2;
```

字段端口无需单独向外突出 DOM 圆点，SVG 锚点使用节点边界即可。

## 12.4 多边同端口处理

同一个字段可能产生多条边。若完全使用同一点会重叠，建议增加微小偏移：

```typescript
const samePortOffset =
  portAnchorOffset(indexWithinSamePort, samePortCount, 3);
```

最终：

```typescript
sy = sourceNode.y + columnOffsetY + samePortOffset;
```

`buildComfortPortIndexes()` 需要从“按节点统计”扩展为“按节点 + 字段端口统计”：

```text
source key = `${edge.source}::${edge.sourcePort ?? '__node__'}`
target key = `${edge.target}::${edge.targetPort ?? '__node__'}`
```

---

## 13. LineageCanvas 渲染改造

主要文件：

```text
src/components/LineageCanvas.tsx
```

建议新增组件：

```text
src/components/LineageCanvas/RelationNodeCard.tsx
src/components/LineageCanvas/ColumnRow.tsx
```

避免继续将所有节点 JSX 堆在 `LineageCanvas.tsx`。

## 13.1 RelationNodeCard 接口

```typescript
interface RelationNodeCardProps {
  node: GraphNode;
  box: { width: number; height: number };
  selectedEntityId: string;
  currentEntityIds: Set<string>;
  dimmed: boolean;
  warning: boolean;
  dragging: boolean;

  onSelectRelation: (entityId: string) => void;
  onSelectColumn: (entityId: string) => void;
  onDoubleClickEntity: (entityId: string) => void;
  onToggleCollapsed: (entityId: string) => void;
  onStartDrag: (event: React.MouseEvent, node: GraphNode) => void;
}
```

## 13.2 节点结构

```tsx
<div className="relation-node">
  <div className="relation-node__header">
    <button
      className="relation-node__collapse"
      onClick={...}
    >
      {node.collapsed ? '›' : '⌄'}
    </button>

    <div className="relation-node__identity">
      <span className="relation-node__kind">{node.tag}</span>
      <span className="relation-node__title">{node.label}</span>
    </div>
  </div>

  {!node.collapsed && (
    <div className="relation-node__columns">
      {node.columns?.map(column => (
        <ColumnRow key={column.entityId} ... />
      ))}
    </div>
  )}

  {!node.collapsed && Boolean(node.hiddenColumnCount) && (
    <div className="relation-node__hidden">
      +{node.hiddenColumnCount} hidden
    </div>
  )}
</div>
```

## 13.3 ColumnRow

```tsx
function ColumnRow(props: ColumnRowProps) {
  const selected = props.selectedEntityId === props.column.entityId;

  return (
    <button
      type="button"
      className="column-row"
      data-selected={selected || undefined}
      data-role={props.column.role}
      onMouseDown={event => event.stopPropagation()}
      onClick={event => {
        event.stopPropagation();
        props.onSelect(props.column.entityId);
      }}
      onDoubleClick={event => {
        event.stopPropagation();
        props.onDoubleClick(props.column.entityId);
      }}
    >
      <span className="column-row__target-port" />
      <span className="column-row__label">{props.column.label}</span>
      <span className="column-row__source-port" />
    </button>
  );
}
```

端口圆点仅用于视觉提示，真正路由坐标仍由布局函数计算，避免 DOM 测量依赖。

## 13.4 普通节点保持

`expression`、`unknown` 等非容器节点继续使用当前 `.node` 样式。

建议：

```typescript
const isRelationContainer = Boolean(node.columns);
```

渲染分支：

```tsx
isRelationContainer
  ? <RelationNodeCard ... />
  : <LegacyGraphNode ... />
```

## 13.5 拖拽规则

- Header 和容器空白区域可启动拖拽；
- ColumnRow 的 `mousedown` 必须 `stopPropagation()`；
- Collapse 按钮必须 `stopPropagation()`；
- 正在拖拽时继续调用 `transitionFrame.cancel()`；
- 拖拽位置仍按容器 node.id / entityId 保存。

---

## 14. CSS 规范

文件：

```text
src/styles/index.css
```

新增：

```css
.relation-node {
  position: absolute;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1.5px solid #cbd5e1;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 3px 10px rgba(15, 23, 42, 0.10);
  transform-origin: center center;
  will-change: transform, opacity;
}

.relation-node[data-type="output"] {
  border: 2px solid #2563eb;
  background: #f8fbff;
}

.relation-node__header {
  height: 48px;
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
  cursor: grab;
}

.relation-node[data-collapsed="true"] .relation-node__header {
  border-bottom: none;
}

.relation-node__collapse {
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
}

.relation-node__columns {
  padding: 5px 8px;
}

.column-row {
  position: relative;
  width: 100%;
  height: 26px;
  display: flex;
  align-items: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #475569;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.column-row:hover {
  background: #f1f5f9;
}

.column-row[data-selected="true"] {
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 700;
}

.column-row__label {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  padding: 0 8px;
}

.column-row__target-port,
.column-row__source-port {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  opacity: 0.65;
  flex: none;
}

.relation-node__hidden {
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-top: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 11px;
}
```

要求：

- 不覆盖现有表级、子查询级节点视觉；
- 仅对带 `columns` 的容器节点使用新类；
- 保留现有 selected、current、warning、stale、dimmed、downstream-impact 语义；
- 字段选中不应让整个表节点同时出现强烈呼吸光效；
- 表被选中时可以高亮容器边框；字段被选中时只高亮字段行和相关边。

---

## 15. 状态与 Action 改造

文件：

```text
src/workbench/state.ts
src/workbench/actions.ts
```

## 15.1 初始化

```typescript
collapsedRelationIds: {},
columnContainerMode: 'relation_rows',
```

## 15.2 折叠 Action

```typescript
export function toggleRelationCollapsed(
  state: WorkbenchState,
  entityId: string,
): WorkbenchState {
  const next = { ...state.collapsedRelationIds };

  if (next[entityId]) {
    delete next[entityId];
  } else {
    next[entityId] = true;
  }

  return {
    ...state,
    collapsedRelationIds: next,
    graphTransition: {
      ...state.graphTransition,
      phase: 'preparing',
      fromMode: state.graphViewMode,
      toMode: state.graphViewMode,
      reason: 'collapse-change',
    },
  };
}
```

## 15.3 分析结果更新时

`buildAnalyzeSuccessState()` 中清空折叠覆盖：

```typescript
collapsedRelationIds: {},
```

防止新 SQL 继承旧图的实体折叠状态。

## 15.4 视图切换

表级 → 列级时保留 `positions`，不要在新的 `requestGraphViewModeChange()` 中清空位置。

当前 `requestGraphViewModeChange()` 已经不清空 positions，应继续使用该函数，不要回退到旧的 `switchGraphViewMode()` 清空实现。

---

## 16. 选择、高亮与路径计算兼容

当前 `selectedEntity` 可能变成字段实体，而可见主节点是其 owner relation。

必须新增 helper：

```typescript
export function visibleOwnerEntityId(
  graph: GraphLike,
  selectedEntityId: string,
): string {
  for (const node of graph.nodes) {
    if (node.entityId === selectedEntityId) return selectedEntityId;
    if (node.columns?.some(column => column.entityId === selectedEntityId)) {
      return node.entityId;
    }
  }

  return selectedEntityId;
}
```

但注意：

- UI 字段行选中仍使用原字段 ID；
- 图遍历时不能只查 `graph.nodes`；
- 边关联判断应同时考虑 `sourcePort` / `targetPort`。

例如相关边判断：

```typescript
function edgeTouchesEntity(edge: GraphEdge, entityId: string): boolean {
  return (
    edge.source === entityId ||
    edge.target === entityId ||
    edge.sourcePort === entityId ||
    edge.targetPort === entityId ||
    edge.originalSourceEntityId === entityId ||
    edge.originalTargetEntityId === entityId
  );
}
```

下游影响路径应将字段端口作为真实血缘实体计算，不要只按关系主节点计算，否则选中一个字段会错误高亮整张表的全部字段路径。

推荐建立两张邻接图：

```text
relation adjacency：用于布局和容器级高亮
entity adjacency：用于字段级路径、mapping、diagnostics
```

P0 最少要求：

- 选中字段只高亮与该字段端口直接关联的边；
- 相关关系容器可以轻度高亮；
- 不相关字段行保持普通或 dimmed；
- DetailPanel 继续拿到字段实体 ID。

---

## 17. 动画兼容

现有 `graphTransition.ts` 按主节点实体 ID 插值位置，可以直接复用。

## 17.1 稳定节点

表级和列级模式必须共享：

```text
physical_table:...
out:query_result / 后端真实 output ID
```

不要在列级模式生成：

```text
column-mode-table:...
```

否则表级到列级切换会被识别为退出/进入，而不是持续节点。

## 17.2 字段行进入动画

字段行是容器内部 DOM，不需要加入 `GraphTransitionPlan` 的主节点集合。

使用 CSS：

```css
.relation-node__columns {
  animation: column-rows-enter 180ms ease-out;
}

@keyframes column-rows-enter {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

## 17.3 高度变化

P0 不要求逐帧插值节点高度。采用：

```text
容器尺寸立即切换
主节点中心位置按现有 transition 插值
字段行淡入/淡出
边每帧按当前中心 + 新端口偏移重算
```

若出现明显跳动，再在 P1 增加尺寸插值，不要在 P0 过度复杂化。

## 17.4 过渡期间边

`useGraphTransition()` 的 renderGraph 会合并前后图边。字段端口边与表级边 ID 不应冲突。

建议 ID：

```text
column:<original-edge-id>
collapsed:<source-owner>-><target-owner>:<edge-type>
table:<source>-><target>:<edge-type>
```

这样旧边淡出、新边淡入时不会互相覆盖。

---

## 18. Feature Flag 与回滚

新增前端开关：

```typescript
columnContainerMode: 'legacy' | 'relation_rows'
```

`visibleColumnGraph()`：

```typescript
if (state.columnContainerMode === 'legacy') {
  return visibleLegacyColumnGraph(base, positions);
}

return visibleRelationColumnGraph(state, base, positions);
```

将当前 `visibleColumnGraph()` 原实现重命名为：

```typescript
visibleLegacyColumnGraph()
```

不要直接删除，至少保留一个迭代周期。

快速回滚仅需：

```typescript
columnContainerMode: 'legacy'
```

不得通过回滚后端接口解决前端问题。

---

## 19. 推荐文件改造清单

## 19.1 新增文件

```text
src/relationColumnProjection.ts
src/components/LineageCanvas/RelationNodeCard.tsx
src/components/LineageCanvas/ColumnRow.tsx
src/__tests__/relationColumnProjection.test.ts
src/__tests__/columnPortRouting.test.ts
```

## 19.2 必须修改

| 文件 | 主要改动 |
|---|---|
| `src/types/lineage.ts` | ColumnRow、端口字段、折叠状态、Feature Flag |
| `src/graphPipeline.ts` | 保留 legacy，接入新 relation-column 投影 |
| `src/nodeVisualTokens.ts` | 动态节点尺寸 |
| `src/graphComfortLayout.ts` | 变量高度布局、字段端口路由 |
| `src/components/LineageCanvas.tsx` | 容器节点渲染、字段选择、折叠 |
| `src/styles/index.css` | RelationNodeCard 与 ColumnRow 样式 |
| `src/workbench/state.ts` | 初始状态、分析后重置 |
| `src/workbench/actions.ts` | toggleRelationCollapsed |
| `src/data/selectors.ts` | 字段端口路径与高亮兼容 |
| `src/components/__tests__/LineageCanvas.test.tsx` | 新列视图组件断言 |
| `src/__tests__/graphLayoutHints.test.ts` | 动态高度不重叠测试 |

## 19.3 不得新增依赖

本次不得引入：

```text
@xyflow/react
react-flow
elkjs
dagre
framer-motion
```

使用现有 React、SVG、布局与动画即可。

---

## 20. 分阶段实施顺序

## Commit 1：类型与 Feature Flag

- 新增 `GraphColumnRow`；
- 扩展 GraphNode / GraphEdge；
- 新增 `collapsedRelationIds`；
- 新增 `columnContainerMode`；
- 保证 typecheck 通过。

## Commit 2：RelationColumnProjection

- 新建 `relationColumnProjection.ts`；
- 编写 owner 解析；
- 表字段与输出字段聚合；
- 字段边转换；
- 折叠降级与去重；
- 完成纯函数单测。

## Commit 3：动态尺寸与布局

- `getComfortNodeBox(node)`；
- 变量高度画布计算；
- 层内节点打包；
- 动态节点碰撞测试。

## Commit 4：字段端口路由

- `getColumnPortOffsetY()`；
- `buildComfortPortIndexes()` 支持字段端口；
- `routeComfortEdgePath()` 支持字段行；
- 路径起终点测试。

## Commit 5：RelationNodeCard UI

- 表头；
- 字段行；
- 折叠按钮；
- 字段选择；
- 拖拽冲突处理；
- CSS。

## Commit 6：选择、高亮与动画兼容

- 字段级 edge matching；
- 字段选中与容器轻高亮；
- 过渡边 ID；
- 大图降级确认。

## Commit 7：回归、E2E 与文档

- 全量测试；
- 浏览器 smoke；
- README 更新；
- Feature Flag 使用说明。

---

## 21. 测试要求

## 21.1 纯函数测试：relationColumnProjection

必须覆盖：

1. 单表单字段；
2. 单表多字段；
3. 多表到多个输出字段；
4. 字段 ordinal 排序；
5. `catalog.schema.table.column` owner 解析；
6. 输出字段通过真实 output edge 找 owner；
7. 缺失 physical_table 时生成兼容容器；
8. owner 解析失败不崩溃；
9. 字段边保留 mapping；
10. sourcePort / targetPort 正确；
11. 折叠后字段边降级；
12. 降级边去重；
13. expression 中间节点保留；
14. 宽表字段过滤；
15. legacy 模式结果不变。

示例断言：

```typescript
expect(edge).toMatchObject({
  source: 'physical_table:db.tbl',
  sourcePort: 'physical_column:db.tbl.user_id',
  target: 'out:query_result',
  targetPort: 'output_field:uid',
});
```

## 21.2 动态布局测试

必须覆盖：

- 2 行字段与 20 行字段节点同层不重叠；
- 折叠后高度恢复 48；
- 输出容器高度正确；
- 不同层 X 间距不小于最小 rank gap；
- 同层节点上下边界间距不小于 minNodeGap；
- 手工拖拽坐标仍优先；
- 表级视图固定节点布局不回归。

边界断言：

```typescript
const previousBottom = prev.y + getComfortNodeBox(prev).height / 2;
const currentTop = curr.y - getComfortNodeBox(curr).height / 2;

expect(currentTop - previousBottom).toBeGreaterThanOrEqual(minGap);
```

## 21.3 字段端口路由测试

- 第一行字段端口 Y；
- 中间字段端口 Y；
- 最后一行字段端口 Y；
- source / target 连接左右边界；
- 同端口多边有微小偏移；
- 端口不存在安全降级；
- 节点折叠后使用节点级中心端口；
- 路径不包含 `NaN`、`undefined`。

## 21.4 组件测试

`LineageCanvas.test.tsx` 新增：

- 列视图不再渲染独立 `.node[data-type="output_field"]`；
- 表容器中显示源字段行；
- Query Result 容器中显示输出字段行；
- 点击字段行选择字段实体；
- 点击折叠按钮不触发表选择；
- 折叠后字段行消失；
- 展开后字段行恢复；
- 字段选中只高亮对应 row；
- relation 节点仍可拖拽；
- 字段行拖动不会启动节点拖拽；
- 旧 table / subquery 视图 UI 不变化。

## 21.5 动画测试

- table → column 时物理表与 output 为 persisting；
- 不再把所有 output_field 当作 entering 主节点；
- column → table 时字段行消失但容器不退出；
- 折叠切换 reason 为 `collapse-change`；
- 快速连续切换不残留退出边；
- 拖拽时 transition 被取消。

## 21.6 E2E

至少使用：

```text
e2e/cases/single_table_column.sql
```

并补充：

```text
e2e/cases/multi_table_column.sql
e2e/cases/expression_column.sql
e2e/cases/wide_table_column.sql
```

浏览器验收：

1. SQL 分析成功；
2. 切换列级视图；
3. 字段行显示；
4. 边连到正确字段行；
5. 折叠表后边退化；
6. 展开后恢复字段连线；
7. 选择字段能联动详情；
8. 拖拽、缩放、平移正常；
9. 切回表级动画平滑；
10. 控制台无错误。

---

## 22. 性能与降级

## 22.1 动画阈值

保留当前：

```typescript
nodes <= 120 && edges <= 220
```

但 RelationColumnGraph 主节点较少、字段行较多，应增加字段行阈值：

```typescript
const totalColumnRows = graph.nodes.reduce(
  (sum, node) => sum + (node.columns?.length ?? 0),
  0,
);

const shouldAnimate =
  graph.nodes.length <= 120 &&
  graph.edges.length <= 220 &&
  totalColumnRows <= 500;
```

## 22.2 大图降级

超过阈值时：

- 不做节点坐标逐帧动画；
- 字段行只做 100ms opacity；
- 关闭边标签；
- 默认折叠超宽表；
- 仅展开选中路径涉及的表。

## 22.3 不使用 DOM 测量

字段端口坐标由常量与字段顺序计算，不通过：

```typescript
getBoundingClientRect()
```

逐条测量字段行。这样可避免：

- 强制同步布局；
- 缩放坐标换算错误；
- 动画过程中边滞后；
- 测试环境 jsdom 无尺寸。

---

## 23. 验收标准

## 23.1 功能验收

- [ ] 列级模式以表/输出容器展示字段；
- [ ] 源字段与输出字段均显示在所属容器内；
- [ ] 字段边连接到正确字段行；
- [ ] 折叠后边自动降级到关系级；
- [ ] 展开后恢复字段端口连线；
- [ ] 字段可选中并进入现有 DetailPanel；
- [ ] 表级、子查询级视图无行为回归；
- [ ] 表级 ↔ 列级切换不重新请求后端；
- [ ] backendGraph 不被前端投影污染。

## 23.2 视觉验收

- [ ] 表头与字段区层级清晰；
- [ ] 字段行高度一致；
- [ ] 边端口与字段行中心对齐；
- [ ] 不出现边连接到容器空白区域；
- [ ] 不出现节点相互覆盖；
- [ ] Query Result 与物理表视觉区分明确；
- [ ] 字段选中高亮不过度影响整个容器；
- [ ] 折叠按钮点击区域足够大。

## 23.3 工程验收

以下命令全部通过：

```bash
npm run typecheck
npm run test
npm run build
npm run smoke:browser
```

不得出现：

- TypeScript `any` 大量扩散；
- 控制台 React key 警告；
- SVG path 中 `NaN`；
- 重复 entity ID；
- 无效边端点；
- 快速切换后的 RAF 泄漏；
- 拖拽后节点与鼠标错位。

---

## 24. Codex 执行要求

Codex 开始编码前必须先阅读并确认：

```text
src/types/lineage.ts
src/graphPipeline.ts
src/graphComfortLayout.ts
src/nodeVisualTokens.ts
src/components/LineageCanvas.tsx
src/graphTransition.ts
src/useGraphTransition.ts
src/workbench/state.ts
src/workbench/actions.ts
src/data/selectors.ts
```

实施要求：

1. 不创建脱离项目的独立 Demo；
2. 直接修改当前前端项目；
3. 保留 legacy 列视图作为 Feature Flag 回滚路径；
4. 不引入 React Flow；
5. 不修改后端接口；
6. 不删除表达式实体；
7. 所有新投影函数优先写成纯函数；
8. 每个阶段完成后运行 typecheck 和对应测试；
9. 最终提供变更文件清单、设计取舍和测试结果；
10. 遇到当前文档与实际代码冲突时，以现有接口兼容和不破坏回归为优先，并在总结中说明偏差。

---

## 25. 可直接交给 Codex 的任务提示词

```text
你现在需要在我现有的 SQL 血缘可视化前端项目中，将当前列级血缘视图改造成 FlowScope 风格的“关系容器 + 内部字段行 + 字段端口连线”模式。

请严格依据《SQL 血缘图 FlowScope 风格列容器改造开发指南 v1.0》实施，并先阅读以下真实源码：

- src/types/lineage.ts
- src/graphPipeline.ts
- src/graphComfortLayout.ts
- src/nodeVisualTokens.ts
- src/components/LineageCanvas.tsx
- src/graphTransition.ts
- src/useGraphTransition.ts
- src/workbench/state.ts
- src/workbench/actions.ts
- src/data/selectors.ts

核心目标：

1. 保持后端 /api/sql/analyze 和 backendGraph 事实模型不变；
2. 新增 relation-column 前端投影层；
3. physical_column 放入所属 physical_table 的 columns[]；
4. output_field 放入最终 output / Query Result 的 columns[]；
5. 字段边改为 relation source/target + sourcePort/targetPort；
6. LineageCanvas 渲染表容器、字段行、折叠按钮；
7. 布局支持可变节点高度；
8. SVG 边精确连接字段行中心；
9. 任一容器折叠时，字段边去重降级为关系级边；
10. 复用现有 graphTransition 动画，保持表和 Output 稳定 ID；
11. 保留当前 legacy 列视图作为 Feature Flag 回滚路径；
12. 不引入 @xyflow/react、dagre、elkjs 或 framer-motion；
13. 表级和子查询级视图不得回归。

默认只完成 P0：物理源表字段到最终输出字段。CTE/subquery 内部字段容器留到后续，不要擅自扩大范围。

请按小步提交逻辑实施：

A. 类型和状态；
B. relationColumnProjection 纯函数；
C. 动态尺寸与布局；
D. 字段端口路由；
E. RelationNodeCard / ColumnRow；
F. 选择、高亮、折叠和动画兼容；
G. 测试、构建和浏览器验收。

最终必须交付：

- 实际修改后的代码；
- 新增和修改文件清单；
- 关键设计说明；
- 未完成项与原因；
- npm run typecheck 结果；
- npm run test 结果；
- npm run build 结果；
- npm run smoke:browser 结果。

不要只给方案或伪代码，必须直接完成当前项目改造。
```

---

## 26. 最终设计摘要

本次改造的本质不是重做血缘解析，而是改变前端展示投影：

```text
当前：
physical_column 被隐藏
physical_table → 独立 output_field → output

目标：
physical_table(columns[])
    field port → field port
output(columns[])
```

最重要的三个实现点：

```text
1. visibleColumnGraph 不再丢失列实体，而是将列变为容器内部字段行；
2. GraphEdge 保存 sourcePort / targetPort；
3. 布局与路由支持动态节点高度和字段行端口。
```

只要保持后端事实图、稳定实体 ID 和现有动画体系不变，该改造可以在前端范围内完成，并且能够显著提高列血缘的可读性、字段归属感和视图切换连续性。
