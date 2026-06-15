# SQL 血缘图视图切换平滑动画 - 实施计划

> 基于《SQL 血缘图视图切换平滑动画补丁实施指南 v1.0》的实际落地方案

## 一、现状检查结果

### 1.1 节点 ID 稳定性检查

| 检查项 | 现状 | 结论 |
|--------|------|------|
| 节点 ID 格式 | 使用 `entityId`（如 `physical_table:xxx`、`cte:xxx`、`out:query_result`） | **稳定** |
| React key | `LineageCanvas.tsx:416` 使用 `key={node.id}` | **稳定** |
| 跨视图一致性 | `node.id` 来自后端 `entity_id`，同一实体在不同视图中 ID 相同 | **OK** |

### 1.2 画布挂载方式检查

| 检查项 | 现状 | 结论 |
|--------|------|------|
| LineageCanvas key | `App.tsx:189` 无 `key={graphViewMode}` | **不会重挂载** |
| 视图切换清空图 | `switchGraphViewMode()` 只重置 `positions: {}`，不清空 `backendGraph` | **OK** |

### 1.3 节点定位方式检查

| 检查项 | 现状 | 结论 |
|--------|------|------|
| 定位方式 | `left: position.x - box.width/2, top: position.y - box.height/2` | **需改为 translate3d** |
| CSS transition | `transition: background .1s, border .1s, box-shadow .1s, opacity .1s`（无 transform） | **OK，不会双重缓动** |

### 1.4 边路由检查

| 检查项 | 现状 | 结论 |
|--------|------|------|
| 坐标源 | 每帧基于 `positions` 对象计算，与节点共用坐标源 | **OK，动画帧统一坐标即可** |
| 路由函数 | `routeEdgePath()` 接收 `sourcePos`、`targetPos` 参数 | **OK** |

## 二、改造文件清单

| 文件 | 操作 | 原因 |
|------|------|------|
| `types/lineage.ts` | 修改 | 新增 `Point`, `GraphTransitionPhase`, `GraphTransitionState` 类型 |
| `graphTransition.ts` | **新增** | 纯函数：节点分类、位置插值、缓动、降级判断、过渡计划构建 |
| `useGraphTransition.ts` | **新增** | RAF Hook：管理动画生命周期、中断、token 防重入 |
| `workbench/state.ts` | 修改 | `WorkbenchState` 增加 `graphTransition` + `graphTransitionEnabled` 字段 |
| `workbench/actions.ts` | 修改 | 新增 `requestGraphViewModeChange`、`finishGraphTransition`、`cancelGraphTransition` |
| `graphPipeline.ts` | 修改 | 新增 `applyFramePositions()`、`buildTargetVisibleGraph()` 辅助函数 |
| `components/LineageCanvas.tsx` | 修改 | 接入 `useGraphTransition`；节点改 `translate3d`；enter/exit 视觉；边基于帧坐标路由 |
| `styles/index.css` | 修改 | 节点改 `left:0; top:0` + transform；enter/exit 状态属性；reduced-motion |

## 三、分阶段实施

### Phase 1：类型 + 纯函数层

**目标**：建立动画的数据基础和纯函数工具。

**文件**：
- `types/lineage.ts` - 新增过渡相关类型定义
- `graphTransition.ts` - 新增纯函数模块

**关键实现**：
```typescript
// types/lineage.ts
export interface Point { x: number; y: number; }
export type PositionMap = Record<string, Point>;
export type GraphTransitionPhase = 'idle' | 'preparing' | 'running' | 'finishing';

export interface GraphTransitionState {
  phase: GraphTransitionPhase;
  fromMode: GraphViewMode | null;
  toMode: GraphViewMode | null;
  startedAt: number | null;
  durationMs: number;
  fromPositions: PositionMap;
  toPositions: PositionMap;
  framePositions: PositionMap;
  enteringEntityIds: string[];
  persistingEntityIds: string[];
  exitingEntityIds: string[];
  progress: number;
  reason: 'view-mode-change' | 'collapse-change' | 'expand-change' | 'layout-change' | null;
}

// graphTransition.ts
export function nodeKey(node: GraphNode): string;
export function graphPositions(graph: GraphLike): PositionMap;
export function classifyTransitionNodes(prev: GraphLike, next: GraphLike): TransitionNodeSets;
export function resolveEnterPosition(entityId: string, nextGraph: GraphLike, currentPositions: PositionMap): Point;
export function resolveExitPosition(entityId: string, prevGraph: GraphLike, targetPositions: PositionMap, currentPositions: PositionMap): Point;
export function createGraphTransitionPlan(options: {...}): GraphTransitionPlan;
export function interpolatePoint(from: Point, to: Point, progress: number): Point;
export function interpolatePositions(from: PositionMap, to: PositionMap, progress: number): PositionMap;
export function easeOutCubic(t: number): number;
export function shouldAnimateGraph(graph: GraphLike): boolean;
export function assertStableGraphEntityIds(graph: GraphLike): void;
```

### Phase 2：状态层 + Actions

**目标**：在工作台状态中集成过渡状态，提供状态转换动作。

**文件**：
- `workbench/state.ts` - 增加 `graphTransition` 初始状态
- `workbench/actions.ts` - 新增过渡相关 actions

**关键实现**：
```typescript
// workbench/state.ts
export const initialWorkbenchState: WorkbenchState = {
  // ... 现有字段
  graphTransition: EMPTY_GRAPH_TRANSITION,
  graphTransitionEnabled: true,
};

// workbench/actions.ts
export function requestGraphViewModeChange(state: WorkbenchState, nextMode: GraphViewMode): WorkbenchState;
export function finishGraphTransition(state: WorkbenchState): WorkbenchState;
export function cancelGraphTransition(state: WorkbenchState): WorkbenchState;
```

### Phase 3：RAF Hook

**目标**：实现 requestAnimationFrame 驱动的动画控制器。

**文件**：
- `useGraphTransition.ts` - 新增 Hook

**关键实现**：
```typescript
export interface UseGraphTransitionOptions {
  previousGraph: GraphLike;
  nextGraph: GraphLike;
  enabled: boolean;
  durationMs?: number;
  onFinish?: () => void;
}

export interface GraphTransitionFrame {
  graph: GraphLike;
  positions: PositionMap;
  progress: number;
  phase: GraphTransitionPhase;
  enteringEntityIds: Set<string>;
  exitingEntityIds: Set<string>;
  cancel: () => void;
}

export function useGraphTransition(options: UseGraphTransitionOptions): GraphTransitionFrame;
```

**核心逻辑**：
- 使用 `transitionTokenRef` 防止快速切换时旧回调提交
- 动画期间每帧调用 `setFrame()` 更新状态
- 支持 `cancel()` 中断（拖拽、重新分析时调用）
- 动画完成后调用 `onFinish()` 清理状态

### Phase 4：画布渲染改造

**目标**：在 LineageCanvas 中接入动画系统。

**文件**：
- `components/LineageCanvas.tsx` - 主要改造
- `graphPipeline.ts` - 新增辅助函数
- `styles/index.css` - 样式调整

**关键改造点**：

1. **节点定位改为 translate3d**：
```tsx
// Before
style={{ left: position.x - box.width / 2, top: position.y - box.height / 2 }}

// After
style={{
  transform: `translate3d(${position.x - box.width / 2}px, ${position.y - box.height / 2}px, 0) scale(${visual.scale})`,
  opacity: visual.opacity,
}}
```

2. **接入 useGraphTransition**：
```tsx
const targetGraph = useMemo(() => visibleGraph(state), [state.backendGraph, state.graphViewMode, state.positions]);
const previousGraphRef = useRef(targetGraph);

const transitionFrame = useGraphTransition({
  previousGraph: previousGraphRef.current,
  nextGraph: targetGraph,
  enabled: state.graphTransitionEnabled && shouldAnimateGraph(targetGraph),
  durationMs: 260,
  onFinish: () => {
    previousGraphRef.current = targetGraph;
  },
});

const renderGraph = useMemo(
  () => applyFramePositions(transitionFrame.graph, transitionFrame.positions),
  [transitionFrame.graph, transitionFrame.positions],
);
```

3. **enter/exit 视觉**：
```tsx
function nodeTransitionVisual(
  entityId: string,
  progress: number,
  entering: Set<string>,
  exiting: Set<string>,
): { opacity: number; scale: number } {
  if (entering.has(entityId)) {
    return { opacity: progress, scale: 0.94 + progress * 0.06 };
  }
  if (exiting.has(entityId)) {
    return { opacity: 1 - progress, scale: 1 - progress * 0.06 };
  }
  return { opacity: 1, scale: 1 };
}
```

4. **边基于帧坐标路由**：
```tsx
const ports = buildPortIndexes(renderGraph, positions);
// 所有边路由使用 renderGraph 和 framePositions
```

5. **拖拽取消动画**：
```tsx
const startDrag = (event: React.MouseEvent, node: GraphNode) => {
  transitionFrame.cancel();
  // ... 原有拖拽逻辑
};
```

6. **动画期间暂停 fitView**：
```tsx
useEffect(() => {
  if (transitionFrame.phase === 'running') return;
  // ... fitView 逻辑
}, [state.canvasCommand, transitionFrame.phase]);
```

### Phase 5：样式调整

**目标**：优化节点渲染性能，支持 enter/exit 状态。

**关键 CSS**：
```css
.node {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: center center;
  will-change: transform, opacity;
  backface-visibility: hidden;
  /* 移除 left/top 的 transition，由 RAF 控制 */
}

.node[data-entering="true"] {
  pointer-events: none;
}

.node[data-exiting="true"] {
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .node {
    transition: none !important;
    animation: none !important;
  }
}
```

## 四、关键设计决策

### 4.1 Feature Flag

```typescript
// workbench/state.ts
graphTransitionEnabled: true,  // 默认启用
```

关闭后直接走 `visibleGraph → layout → render` 原路径，不执行动画。

### 4.2 动画参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 默认时长 | 260ms | 流畅但不迟缓 |
| 最短时长 | 180ms | 快速切换下限 |
| 最长时长 | 320ms | 大图上限 |
| 缓动函数 | `easeOutCubic` | 快速启动、缓慢收尾 |

### 4.3 降级策略

| 档位 | 条件 | 策略 |
|------|------|------|
| Full | ≤120 节点且 ≤220 边 | RAF 节点插值 + 每帧边路由 + enter/exit |
| Lite | 121～300 节点或 221～600 边 | 节点 transform 过渡，边 120ms 淡出后切换 |
| Off | >300 节点、低性能或 reduced-motion | 直接切换或 80ms 交叉淡入 |

### 4.4 快速切换处理

使用 `transitionTokenRef` 递增 token：
```typescript
const transitionTokenRef = useRef(0);

function startTransition() {
  const token = ++transitionTokenRef.current;
  
  const tick = () => {
    if (token !== transitionTokenRef.current) {
      return;  // 旧回调，直接返回
    }
    // ... 动画逻辑
  };
}
```

### 4.5 拖拽冲突处理

拖拽开始时立即取消动画，使用当前帧位置作为拖拽起点：
```typescript
const startDrag = (event: React.MouseEvent, node: GraphNode) => {
  transitionFrame.cancel();
  // 使用 transitionFrame.positions[node.id] 作为起点
};
```

## 五、不修改的内容

### 5.1 后端文件（禁止修改）

```
backend/app/api/analyze_controller.py
backend/app/services/sql_parse_service.py
backend/app/services/name_resolver.py
backend/app/services/cte_column_rollup_service.py
backend/app/services/graph_builder.py
backend/app/domain/graph_view_model.py
```

### 5.2 API 契约（禁止修改）

```
AnalysisResult
GraphViewModel
GraphNode
GraphEdge
/api/sql/analyze
```

### 5.3 现有功能（禁止破坏）

- SQL 解析准确率
- CTE 递归穿透逻辑
- 节点视觉设计、颜色、信息密度
- 选中、高亮、折叠、拖拽、缩放、编辑器跳转
- Barycenter / Median 排序逻辑

## 六、验收标准

### 6.1 功能验收

- [ ] 表级、子查询级、列级视图切换不触发后端 API
- [ ] 公共节点不会卸载重建（DOM 元素复用）
- [ ] `subquery → table` 节点移动连续
- [ ] `table → subquery` CTE 节点自然展开
- [ ] 退出节点动画完成后才从 DOM 删除
- [ ] 边在整个动画过程中连接正确端口
- [ ] 选中节点和路径高亮在切换后仍正确
- [ ] 动画期间开始拖拽不会导致节点与鼠标脱节
- [ ] 快速连续切换后最终模式正确
- [ ] 新 AnalysisResult 到达后不会残留旧动画节点

### 6.2 性能验收

- [ ] 典型 30～80 节点图动画无明显卡顿
- [ ] 动画期间主线程无持续 >50ms Long Task
- [ ] 大图自动降级
- [ ] reduced-motion 设置下不执行复杂动画

### 6.3 工程验收

- [ ] 后端代码无修改
- [ ] API schema 无修改
- [ ] `GraphViewModel` 未写入动画状态
- [ ] TypeScript 严格检查通过
- [ ] 生产构建通过
- [ ] Feature Flag 可关闭动画
- [ ] 关闭后行为与改造前一致

## 七、实施顺序

1. **Phase 1**：类型 + 纯函数层（`types/lineage.ts`、`graphTransition.ts`）
2. **Phase 2**：状态层 + Actions（`workbench/state.ts`、`workbench/actions.ts`）
3. **Phase 3**：RAF Hook（`useGraphTransition.ts`）
4. **Phase 4**：画布渲染改造（`LineageCanvas.tsx`、`graphPipeline.ts`）
5. **Phase 5**：样式调整（`styles/index.css`）
6. **Phase 6**：验证（typecheck、test、build）
7. **Phase 7**：启动服务供验收

## 八、风险与回滚

### 8.1 风险点

1. **节点 ID 不稳定**：如果某些视图生成的节点 ID 不一致，会导致动画失效
2. **性能问题**：大图每帧重新路由边可能导致卡顿
3. **拖拽冲突**：动画与拖拽的坐标切换可能产生跳跃

### 8.2 回滚方案

关闭 Feature Flag：
```typescript
graphTransitionEnabled: false
```

或直接删除新增文件，恢复原有 `switchGraphViewMode` 逻辑。

## 九、测试计划

### 9.1 单元测试（待实施）

- `graphTransition.test.ts`：节点分类、插值、进入/退出位置、降级判断
- `useGraphTransition.test.ts`：Hook 生命周期、取消、快速切换

### 9.2 组件测试（待实施）

- `LineageCanvas.transition.test.tsx`：DOM 复用、边同步、拖拽中断

### 9.3 手动验收

- 启动前后端服务
- 加载含 CTE 的示例 SQL
- 点击 Analyze
- 切换 Table / Subquery / Column 视图
- 观察节点移动、边连接、enter/exit 效果
- 测试拖拽中断、快速切换

---

**文档版本**：v1.0  
**创建日期**：2026-06-15  
**作者**：AI Assistant  
**审核状态**：待验收
