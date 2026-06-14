# C18 前端运行时 Mock 与调试入口清理说明

日期：2026-06-15

## 本轮目标

针对主页面前端实现，先做一轮小范围清理，不扩展新功能：

1. 去掉正式运行时页面中的 mock 展示内容。
2. 清理已确认无引用的前端死代码。
3. 去掉主导航中的调试入口，避免正式页面和内部排障页混用。
4. 修复用户可见乱码文案。

## 本轮改动

### 1. 清理运行时 Drawer 中的 mock 内容

调整文件：

- `frontend/src/components/Drawer.tsx`
- `frontend/src/data/mockLineage.ts`
- `frontend/src/components/CanvasToolbar.tsx`

处理内容：

- 删除运行时 `Drawer` 中的 `snapshots`、`milestones`、`taxonomy` 三类静态展示页签。
- 删除无实际行为的 `checkpoint` 按钮。
- 保留 `diagnostics` 与 `more` 两个真正有运行时价值的抽屉页签。
- 将工具栏里的 `?` 按钮改为直接打开 `diagnostics`，避免打开已删除的 taxonomy 抽屉内容。
- `mockLineage.ts` 中仅保留测试仍在使用的图夹具，不再保留运行时历史说明数据。

结果：

- 主页面抽屉现在只展示当前分析结果相关内容和少量工作区操作。
- 不再把历史里程碑、快照说明混入正式运行时页面。

### 2. 清理前端死代码

调整文件：

- `frontend/src/data/selectors.ts`
- `frontend/src/data/__tests__/selectors.test.ts`

处理内容：

- 删除已经无任何运行时引用的 `fieldNodes()`。
- 删除已经无任何运行时引用的 `fieldEdges()`。
- 同步清理测试中的无效 import。

结果：

- 去掉了一组确认无引用的旧 mock selector 实现。
- 减少了 `selectors.ts` 中运行时逻辑和旧演示逻辑混放的问题。

### 3. 移除主页面 Debug 入口

调整文件：

- `frontend/src/App.tsx`
- `frontend/src/components/LeftNav.tsx`
- `frontend/src/components/__tests__/LeftNav.test.tsx`
- `frontend/src/pages/DebugPage.tsx`
- `frontend/src/styles/index.css`

处理内容：

- 从左侧导航移除 `Debug Mode`。
- 从 `App.tsx` 中移除 debug 页面分支。
- 删除未再使用的 `DebugPage.tsx`。
- 删除对应的 debug 样式。
- 更新导航测试断言。

结果：

- 正式工作台入口只保留 `Workbench` 和 `Dialect Convert`。
- 避免把内部排障页面继续暴露在主导航中。

### 4. 修复前端乱码文案

调整文件：

- `frontend/src/components/MetadataDialog.tsx`
- `frontend/src/graphPipeline.ts`

处理内容：

- 重写 `MetadataDialog` 中的示例 payload，移除乱码中文注释，改为稳定英文示例文本。
- 修复搜索结果 fallback reason 的乱码字符串。
- 顺手修正 `MetadataDialog` 中若干可读性较差的文案和字段回退逻辑。

结果：

- 用户可见文本不再出现乱码。
- 元数据导入弹窗示例内容更稳定，便于后续继续维护。

## 验证情况

已执行：

1. `frontend` 下 `npm run typecheck`
   - 结果：通过
2. `frontend` 下定向相关测试
   - `src/components/__tests__/LeftNav.test.tsx`：通过
   - `src/components/__tests__/CanvasToolbar.test.tsx`：通过
   - `src/data/__tests__/selectors.test.ts`：通过
   - `src/__tests__/analyzeFlow.test.tsx`：通过

补充说明：

- 全量 `vitest` 目前仍存在 1 条失败用例：
  - `src/pages/__tests__/DialectConvertPage.test.tsx`
  - 失败点：`edits the target sql directly in compare mode`
- 该失败点属于 SQL 方言转换页面，和本轮主页面清理改动无直接关系，本轮未继续扩修。

## 本轮结论

这轮先完成了“减法型收尾”：

- 去掉正式运行时中的 mock 内容
- 去掉确认无引用的死代码
- 去掉主导航中的 debug 页面
- 修掉前端可见乱码文案

整体目标是让主页面前端实现更贴近真实分析链路，减少后续继续叠功能时的维护噪音。
