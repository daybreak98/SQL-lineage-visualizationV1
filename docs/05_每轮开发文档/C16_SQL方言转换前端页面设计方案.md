# C16 SQL方言转换前端页面设计方案

日期：2026-06-09  
阶段：设计方案  
状态：待开发

## 1. 目标

在当前主页面左侧导航增加一个新入口，进入“SQL 方言转换”次页面。该页面面向 SQL 开发与迁移场景，提供以下核心能力：

- SQL 方言转换
- 转换前后 SQL Diff 对比
- 可编辑、可复制、可再次转换
- 支持 `Hive`、`Spark`、`StarRocks(sr)`

本轮只做前端页面设计，不直接实现后端转换逻辑。

## 2. 设计原则

- 不把“方言转换”硬塞进现有血缘工作台主视图
- 采用独立次页面，避免和血缘分析状态机互相污染
- 尽量复用现有 Monaco 基础设施和视觉风格
- 第一版优先保证“可用、清晰、可验收”，避免做重型 IDE
- `sr` 在前后端统一映射为 `starrocks`

## 3. 页面入口设计

### 3.1 左侧导航新增按钮

在当前 [LeftNav.tsx](D:/Users/yingjie.hu/Documents/sql血缘解析可视化/SQL-lineage-visualizationV1/frontend/src/components/LeftNav.tsx) 中新增一个按钮：

- key：`convert`
- title：`Dialect Convert`
- 建议标签：`C`

建议放置顺序：

1. `Workbench`
2. `Convert`
3. 其他辅助入口

原因：

- `Convert` 是与 `Workbench` 同级的主任务页面
- 用户心智上属于“另一个工作台”，不是 `Drawer` 中的一个 tab

### 3.2 导航行为

点击 `Convert` 后，页面主区域整体切换到“方言转换页”，而不是打开右侧抽屉。

建议采用两种实现方式中的第一种：

- 方案 A：先不引入 `react-router`，在 `App.tsx` 内做页面级视图切换
- 方案 B：后续如果页面持续增多，再切换到 Router

本项目当前没有 Router 依赖，第一版建议使用 **方案 A**，改动最小。

## 4. 页面信息架构

建议转换页分为 4 个区域：

1. 页面头部工具栏
2. 左侧源 SQL 编辑区
3. 右侧目标 SQL 编辑区 / Diff 区
4. 底部结果与诊断区

推荐布局：

```text
+--------------------------------------------------------------+
| Header: Source Dialect | Target Dialect | Convert | Swap ... |
+-------------------------------+------------------------------+
| Source SQL Editor             | Target SQL / Diff Viewer     |
| Monaco Editor                 | Monaco DiffEditor / Editor   |
|                               |                              |
+-------------------------------+------------------------------+
| Diagnostics | Warnings | Convert Summary | Copy / Download   |
+--------------------------------------------------------------+
```

## 5. 核心功能设计

### 5.1 方言转换

必备控件：

- `Source Dialect` 下拉
- `Target Dialect` 下拉
- `Convert` 按钮
- `Swap` 按钮
- `Format Source` 按钮
- `Format Target` 按钮

第一版支持方言：

- `Hive`
- `Spark`
- `StarRocks`

展示层可以显示 `StarRocks`，内部统一传 `starrocks`。

### 5.2 Diff 对比

推荐使用 **Monaco DiffEditor**，理由：

- 项目已使用 `@monaco-editor/react`
- 现有 SQL 编辑器经验可复用
- Monaco DiffEditor 对 SQL 文本比对已经足够
- 后续可继续叠加语法高亮、只读目标区、差异导航

推荐显示模式：

- 默认：`Split Diff`
- 可切换：`Target Only`

原因：

- `Split Diff` 适合初次转换验收
- `Target Only` 适合复制结果或二次编辑

### 5.3 目标 SQL 可编辑

建议第一版允许用户修改右侧目标 SQL，但区分状态：

- 刚转换完成：显示“Generated”
- 用户改动后：显示“Modified”

这样便于后续继续复制、格式化、手工修正。

### 5.4 诊断与提示

底部结果区展示：

- 转换状态：`success / partial / failed`
- 用时
- 诊断条目
- 兼容性提示
- 不支持语法提示

例如：

- 某函数在目标方言中被近似转换
- 某语法在目标方言中需要手工调整
- 某条语句无法稳定转换

## 6. 编辑器方案

### 6.1 选择 Monaco 的原因

当前项目已有 [SqlEditorPanel.tsx](D:/Users/yingjie.hu/Documents/sql血缘解析可视化/SQL-lineage-visualizationV1/frontend/src/components/SqlEditorPanel.tsx)，并已接入：

- `@monaco-editor/react`
- SQL language
- 自动补全 provider
- hover provider

因此第一版应继续使用 Monaco，而不是引入新的在线 SQL 编辑器。

### 6.2 推荐编辑器组合

- 左侧：`Monaco Editor`
- 右侧：
  - 默认 `Monaco DiffEditor`
  - 或在“Target Only”模式下使用普通 `Monaco Editor`

### 6.3 是否需要 CodeMirror

当前不建议引入 CodeMirror，原因：

- 会增加依赖和样式成本
- 项目已有 Monaco 基础设施
- Diff 能力 Monaco 已足够

## 7. 组件拆分建议

建议新增以下前端组件：

- `frontend/src/pages/DialectConvertPage.tsx`
- `frontend/src/components/Convert/ConvertToolbar.tsx`
- `frontend/src/components/Convert/SourceSqlEditor.tsx`
- `frontend/src/components/Convert/TargetSqlViewer.tsx`
- `frontend/src/components/Convert/ConvertResultPanel.tsx`

可复用组件：

- 复用现有 Monaco loader 配置
- 可抽取现有 SQL Editor 的 provider 注册逻辑

如果要进一步减少代码量，也可以先不拆那么细，第一版只新增：

- `DialectConvertPage.tsx`
- `ConvertResultPanel.tsx`

## 8. 状态设计建议

不要把转换页状态塞进现有 `WorkbenchState`。

建议新增独立状态模型，例如：

```ts
interface ConvertPageState {
  sourceDialect: 'hive' | 'spark' | 'starrocks';
  targetDialect: 'hive' | 'spark' | 'starrocks';
  sourceSql: string;
  targetSql: string;
  diffMode: 'split' | 'target_only';
  convertStatus: 'idle' | 'running' | 'success' | 'partial' | 'failed';
  diagnostics: BackendDiagnostic[];
  backendMessage?: string;
  elapsedMs?: number;
  isTargetDirty: boolean;
}
```

原因：

- 转换页是独立任务域
- 避免污染当前血缘分析状态机
- 便于后续独立测试

## 9. 前端 API 契约建议

现有 `/api/sql/format` 不够表达“转换”。

建议后端新增接口：

- `POST /api/sql/convert`

请求体建议：

```json
{
  "sql": "select * from t",
  "source_dialect": "hive",
  "target_dialect": "spark",
  "pretty": true
}
```

响应建议：

```json
{
  "status": "success",
  "source_dialect": "hive",
  "target_dialect": "spark",
  "converted_sql": "SELECT * FROM t",
  "elapsed_ms": 12,
  "diagnostics": []
}
```

第一版前端页面以这个契约为目标设计。

## 10. 页面交互流程

### 10.1 标准流程

1. 用户进入 `Convert` 页面
2. 选择源方言与目标方言
3. 在左侧输入或粘贴 SQL
4. 点击 `Convert`
5. 右侧显示转换结果和 Diff
6. 用户查看诊断
7. 用户复制或继续编辑目标 SQL

### 10.2 快捷操作

建议支持：

- `Swap`：源目标方言互换，左右 SQL 对调
- `Copy Target`
- `Load Example`
- `Clear`
- `Convert Again`

## 11. 验收标准

前端页面第一版验收建议如下：

- 左侧导航存在 `Convert` 入口
- 点击后进入独立次页面，不影响原工作台
- 页面有源/目标方言选择器
- 页面有源 SQL 编辑区
- 页面有目标 SQL 展示区
- 页面支持 Diff 对比
- 页面能显示转换状态与诊断
- 页面支持 `Hive / Spark / StarRocks`
- 页面布局在桌面端和窄屏下都可用

## 12. 视觉与布局建议

为了保持与现有系统一致，建议延续当前工作台风格：

- 左侧仍保留窄导航条
- 主内容区采用双栏
- 使用现有按钮、badge、panel-head 风格

但转换页应和血缘页有明确区分：

- 页面标题明确写 `SQL Dialect Convert`
- 右侧区域默认突出 `Diff`
- 诊断区文案强调“兼容性/转换提示”，而非“血缘诊断”

## 13. 推荐实现顺序

### 第一阶段

- 左侧导航增加入口
- `App.tsx` 页面级切换
- 新建 `DialectConvertPage`
- 搭好双编辑器页面骨架

### 第二阶段

- 接 `/api/sql/convert`
- 接 Monaco DiffEditor
- 展示转换结果和诊断

### 第三阶段

- `Swap`
- `Copy`
- `Load Example`
- `Target Only / Split Diff` 切换

## 14. 当前结论

这项功能前端适合做成 **独立次页面**，而不是当前主血缘工作台里的一个小弹窗或一个 Drawer tab。

编辑器方案上，第一版推荐：

- **继续使用 Monaco**
- **Diff 使用 Monaco DiffEditor**

这是当前项目里成本最低、风格最统一、后续扩展最稳的方案。
