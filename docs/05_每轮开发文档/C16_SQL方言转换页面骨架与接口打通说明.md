# C16 SQL方言转换页面骨架与接口打通说明

日期：2026-06-09  
阶段：实现中  
状态：待开发

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
