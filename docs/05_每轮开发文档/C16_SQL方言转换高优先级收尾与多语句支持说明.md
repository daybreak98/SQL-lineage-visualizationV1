# C16 SQL方言转换高优先级收尾与多语句支持说明

日期：2026-06-11  
阶段：已实现  
状态：本轮完成

## 本轮目标

在不明显扩大代码体积的前提下，优先补齐 SQL 方言转换当前最影响验收和后续扩展的几项问题：

- 修复转换页顶部后端在线状态误判
- 清理转换相关前端乱码文案
- 让 SQL 方言转换页复用现有 Monaco 补全 / 悬浮能力
- 修复后端 `format / convert` 仅处理第一条 statement 的问题

## 本轮完成内容

### 1. 转换页后端状态判断修复

- 修复前 `ConvertTopBar` 通过是否包含固定版本号 `0.3.0` 判断在线状态
- 修复后改为基于 `Backend: ...` 状态文本判断，并排除 `offline / checking`

影响：

- 后端版本升级后，转换页不会错误显示离线

### 2. 转换页 Monaco 能力接入

- 抽出 Monaco 公共初始化逻辑到 `SqlEditor/providers.ts`
- 新增按 `model` 绑定 dialect 的机制，避免多个编辑器共享一套 provider 时互相覆盖方言
- 主工作台 `SqlEditorPanel` 改为复用同一套注册逻辑
- `DialectConvertPage` 的 Source / Target / DiffEditor 都已接入 provider 注册与方言绑定

当前效果：

- 转换页编辑器现在和主工作台一样，会走 `/api/editor/completion` 与 `/api/editor/hover`
- Compare 模式下的 diff 原始区和目标区可以按各自 dialect 取能力
- 不再复制一套新的 provider 注册代码

### 3. 前端乱码清理

- 清理了本轮触达文件中的乱码注释
- 修复 `App.tsx` 中转换相关状态文案里的乱码分隔符

本轮处理范围：

- `frontend/src/components/SqlEditor/providers.ts`
- `frontend/src/components/SqlEditorPanel.tsx`
- `frontend/src/App.tsx`

### 4. 后端多语句 format / convert 支持

- 新增 `_join_transpiled_sql(...)`
- `POST /api/sql/format` 不再只取 `transpile(...)[0]`
- `POST /api/sql/convert` 不再只取 `transpile(...)[0]`
- 多条 statement 现在会按 `;\n\n` 拼接返回
- 转换后的目标方言解析校验也从 `parse_one(...)` 改为 `parse(...)`

当前行为：

- 输入多条 SQL 时，返回结果会保留所有成功转译的 statement
- 不再出现“前端看起来只转换了第一条 SQL”的问题

## 设计取舍

- 没有给转换页单独复制一套 Monaco provider，而是复用主工作台能力，避免代码继续膨胀
- 没有引入新的状态管理层，仍保持转换页本地状态闭环
- 多语句支持先做“完整保留全部 statement”，没有额外引入复杂 statement 级诊断结构，保持接口改动最小

## 验证结果

- `npm test -- --run src/pages/__tests__/DialectConvertPage.test.tsx src/components/__tests__/ConvertTopBar.test.tsx src/components/SqlEditor/__tests__/providers.test.ts src/api/__tests__/client.test.ts src/__tests__/analyzeFlow.test.tsx`
  - `49 passed`
- `pytest backend/tests/integration/test_convert_api.py backend/tests/integration/test_format_api.py -q`
  - `9 passed`
- `npm run build`
  - passed

## 后续建议

- 下一轮优先补复杂 SQL 方言转换 golden cases，而不是继续扩前端交互
- 可以在后端新增 statement 级 diagnostics，精确指出是哪一条 SQL 转换失败或存在风险
- 可以把转换页的 SQL 编辑能力再向主工作台靠齐，例如快捷键、格式化提示、光标定位联动
