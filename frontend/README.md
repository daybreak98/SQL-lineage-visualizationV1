# SQL Lineage Workbench v1.4 Merged Final Frontend

亚字段工作台由 React 路由 `/?view=subfield` 提供，从原工作台顶部也可进入；旧 `/subfield.html` 会跳转。运行 `npm ci`、`npm run dev`，然后打开 `http://127.0.0.1:5173/?view=subfield`。Vite 把 `/api` 转发到 `BACKEND_PROXY_TARGET`（默认 `http://localhost:8000`）；部署构建产物时需要在同源提供 API。

内置示例均为合成数据。点「试用示例」分析双 JSON；选中 `media_id` 后可以运行剪枝评审。单列演示展示候选键；合成窗口摘录展示窗口与行选择；合成文本 Map 摘录可分别定位 `str_to_map` 函数和带引号的键。文本 Map 行只表示文本查键证据，不提供 JSON 子路径或删键建议。若服务未返回相关证据，界面不会推断。

点「下载证据（JSON）」保存当前请求、SQL 和服务完整响应。示例摘录的出处为合成夹具声明，定位对应提交的 SQL。修改 SQL、方言或源列后会清除旧结果；修改保护根或候选键只清除评审包。

## 当前版本定位

- 版本：`v1.4 merged final`
- 默认视图：`subquery_dependency`
- 主链路：`Analyze → Subquery Dependency → Select Output → Current Field Path → Detail Mapping → Locate SQL → Dirty/Stale → Re-analyze`
- 目标：保留 v1.3 P0-Core 主链路，并合入 v1.4 的节点视觉分类、GraphRenderMode 状态机、Toolbar 去重和画布空间预算。

## 目录结构

```text
sql-lineage-workbench-v1.4/
  package.json
  vite.config.ts
  tailwind.config.js
  postcss.config.js
  tsconfig.json
  tsconfig.node.json
  index.html
  README.md
  src/
    main.tsx
    App.tsx
    styles/index.css
    types/lineage.ts
    utils/cx.ts
    data/
      mockLineage.ts
      selectors.ts
    components/
      TopBar.tsx
      LeftNav.tsx
      SqlEditorPanel.tsx
      Splitter.tsx
      SearchBar.tsx
      CanvasToolbar.tsx
      LineageCanvas.tsx
      DetailPanel.tsx
      Drawer.tsx
      StatusStrip.tsx
```

## 快速启动

```bash
npm install
npm run dev
```

然后打开：

```text
http://localhost:5173
```

## 构建

```bash
npm run build
npm run preview
```

## 交互验收路径

1. 打开页面后默认显示 `subquery_dependency` 子查询依赖图。
2. 点击搜索结果中的 `order_cnt`，进入 `current_field_path` 字段路径图。
3. 点击 `Clear`，回到 `subquery_dependency`。
4. 点击 `Full Preview`，进入 `full_graph_preview`，该模式只允许用户主动触发。
5. 拖动中间 Splitter，验证 SQL/Canvas 比例可调整。
6. 点击图谱节点，底部 DetailPanel 显示摘要。
7. 点击图谱边，底部 DetailPanel 显示 mapping。
8. 修改 SQL，页面进入 `dirty + stale`，Analyze 按钮变成 `Re-analyze`。
9. SQL 中输入 `broken_parse` 后 Analyze，模拟 failed。
10. SQL 中输入 `unknown_col` 后 Analyze，模拟 partial 与 Unknown 节点风险态。
11. 打开左侧 `R / N / S / !`，查看 RenderMode、Node Taxonomy、Snapshots、Diagnostics。

## 重要实现边界

### 1. RuntimeState

运行态集中在 `WorkbenchState`：

```ts
pageMode: empty | ready | analyzing | analyzed | dirty | failed
analysisStatus: none | running | success | partial | failed
trustStatus: trusted | stale | untrusted
```

### 2. GraphRenderMode

状态机在 `src/data/selectors.ts` 的 `transitionRenderMode()` 中维护：

```ts
subquery_dependency
current_field_path
focus_field
semantic_mode
large_graph
full_graph_preview
```

### 3. PathContext

`buildPathContext()` 是 Output Capsule、Path Inline、Path Anchor、Bottom Status 的统一来源，避免多个组件各自维护当前路径状态。

### 4. Mock 数据

所有 mock 血缘数据集中在：

```text
src/data/mockLineage.ts
```

包括：

- SQL 示例
- entities
- sourceLocations
- diagnostics
- edge mappings
- default outputs
- search items
- paths
- subquery nodes / edges
- milestones / snapshots

## 后续接入建议

### Monaco Editor

当前 `SqlEditorPanel.tsx` 是 textarea shell，保留了 Monaco 接入边界。后续可替换为：

```ts
@monaco-editor/react
```

建议保留 `SqlEditorEnginePort` 形式，不要让业务组件直接持有 monaco 实例。

### React Flow

当前 `LineageCanvas.tsx` 使用 SVG + div mock 画布，后续可替换为：

```ts
reactflow
```

建议保持 Graph Fact / Graph View / Graph Interaction 分离：

- Graph Fact：后端分析事实
- Graph View：当前可见节点边
- Graph Interaction：选中、拖拽、viewport、布局缓存

### 后端 API

后续接口建议：

```text
POST /api/sql/analyze
GET  /api/fields/search
GET  /api/fields/{entity_id}/path
```

前端不要猜血缘，字段搜索与字段路径必须由后端结果驱动。

## 给 opencode / DeepSeek 的开发建议

优先按以下顺序继续工程化：

1. 先跑通当前项目，不改 UI 结构。
2. 把 `mockLineage.ts` 替换成 API client 层，不要直接改组件。
3. 引入 Zustand 或 useReducer 管理 `WorkbenchState`。
4. 再替换 Monaco Editor。
5. 最后替换 React Flow。
6. 每次替换后跑通 README 的 11 条交互验收路径。
