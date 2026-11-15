# C16 SQL方言转换页面骨架与接口打通说明

日期：2026-06-09  
阶段：已实现  
状态：已完成第一版闭环

## 本轮目标

基于 `C16_SQL方言转换前端页面设计方案`，先完成第一版“可进入、可编辑、可转换、可看 Diff”的最小闭环：

- 左侧导航新增 `Convert` 入口
- `App.tsx` 支持页面级切换
- 新增 `DialectConvertPage`
- 页面使用 Monaco Editor / Monaco DiffEditor
- 后端新增 `POST /api/sql/convert`
- 前端接通 `Hive / Spark / StarRocks` 之间的转换调用

## 本轮范围

### 包含

- 前端次页面骨架
- 源方言 / 目标方言切换
- Convert / Swap / Copy / Clear / Load Example
- Diff 视图与 Target Only 视图切换
- 后端基础转换接口
- 前后端类型定义与客户端对接

### 不包含

- 复杂转换规则自定义
- 转换历史
- 下载文件
- 与血缘分析页面联动共享状态
- 复杂语义降级提示的精细分级

## 设计约束

- 不引入 Router
- 不污染现有 `WorkbenchState`
- 不复用运行期 mock 数据
- 尽量复用现有 Monaco 依赖
- 先以 `sqlglot` 的 transpile 能力为主

## 已完成内容

- 左侧导航新增 `Convert` 入口
- `App.tsx` 支持 `Workbench / Convert` 页面级切换
- 新增 `DialectConvertPage`
- 新增 `ConvertTopBar`
- 后端新增 `POST /api/sql/convert`
- 前端新增 `convertSql(...)` 客户端调用
- 支持 `Hive / Spark / StarRocks`
- 支持 `Swap / Load Example / Clear / Copy Target`
- 支持 `Split Diff / Target Only`

## 当前交互说明

- `Split Diff`
  - 使用 `Monaco DiffEditor`
  - 当前为只读对比模式
- `Target Only`
  - 使用普通 `Monaco Editor`
  - 允许用户继续修改目标 SQL

这样处理的原因是：

- Monaco DiffEditor 当前类型约束不直接提供本项目所需的受控编辑回写接口
- 第一版优先保证构建稳定和交互闭环

## 验证结果

- `pytest backend/tests/integration/test_convert_api.py -q`
  - `2 passed`
- `npm test -- --run src/pages/__tests__/DialectConvertPage.test.tsx src/api/__tests__/client.test.ts src/__tests__/analyzeFlow.test.tsx`
  - `37 passed`
- `npm run build`
  - passed
