# SQL Lineage Workbench v1.4 Merged Final Frontend

亚字段工作台由 React 路由 `/?view=subfield` 提供，从原工作台顶部也可进入；旧 `/subfield.html` 会跳转。运行 `npm ci`、`npm run dev`，然后打开 `http://127.0.0.1:5173/?view=subfield`。Vite 把 `/api` 转发到 `BACKEND_PROXY_TARGET`（默认 `http://localhost:8000`）；部署构建产物时需要在同源提供 API。

使用自己的 SQL 时，点「编辑 SQL 原文」粘贴 SQL，选方言，再点「分析 SQL」。成功后首屏会列出已观察到的 JSON 路径、能追溯到的不同根输出和本次 SQL 静态分析的待确认项。服务明确返回空清单时显示 0；缺失时显示「未提供」。这个计数是独立于键检查的。选中枝干树的一条路径，可打开对应输出的详情，也可以点「定位读取证据」在本次分析的 SQL 原文中高亮带引号的 JSON 路径字面量；较早的响应未提供字面量位置时，「定位读取调用」会高亮提取函数。宽屏编辑器和画布之间的分隔线支持拖动、左右方向键和双击切换；窄屏依次排列。

要核查键，填写源表与 JSON 列，并在「检查范围」里查看已勾选的输出。默认检查所有可选输出；只取消本次问题不涉及的输出。改变范围后旧结论失效，需要重新检查；全部取消时不会发送检查请求。

查键后，从回执打开匹配的读取证据。只有一处时，点「查看此键的读取证据」会同步选中枝干树并定位提交 SQL；有多处时，先按具体路径和行列选择。没有可靠位置时，回执会说明原因。证据仅表示静态读取，回执的检查范围和结论保持原样。

- 「JSON 路径」接受 `$.user_id` 这类简单顶层路径。嵌套和数组路径仍可在树里查看。
- 「按字面键名」把 `a.b`、`$.a`、大小写或空格原样送检，也可以用「检查空键」核查 `""`。
- 「已看到读取」说明当前 SQL 中有相关读取，不能直接归因给每个所选输出；「本次未见读取」仍需核对键是否存在与修改影响；「暂不能判断」表示服务无法在当前条件下给出相应逐键结论。所有结论供人工核查，未验证行集，也不授权删除。

内置示例均为合成数据。「试用示例」分析双 JSON；单列五级演示适合检查 `media_id` 和 `example_unseen_key`。合成窗口摘录展示窗口与行选择；合成文本 Map 摘录可分别定位 `str_to_map` 函数和带引号的键。文本 Map 行只表示文本查键证据。

「下载证据（JSON）」保存当前请求、SQL 和服务响应。示例摘录的出处为合成夹具声明，定位对应提交的 SQL。修改 SQL、方言或源列声明会清除旧分析；修改检查源表、JSON 列、键或输出范围会清除旧的逐键结论和评审包。

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
