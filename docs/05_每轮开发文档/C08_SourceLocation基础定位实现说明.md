# C08 SourceLocation 基础定位实现说明

## 本轮目标

C08 的目标是把 `source_locations` 链路真正打通：后端返回 SQL 位置，前端把位置收进状态，用户选中字段后可以在详情面板和 Locate SQL 流程中使用这份位置数据。

## 后端实现

新增：

```text
backend/app/services/source_location_service.py
```

核心函数：

```text
build_source_locations(sql, output_column_names)
```

它做了四步：

1. 找到最终 SELECT。
2. 找到最终 SELECT 对应的 FROM。
3. 按顶层逗号拆分 SELECT 输出项。
4. 为每个输出字段生成 `source_locations["output_column:<name>"]`。

返回格式匹配当前前端消费模型：

```json
{
  "output_column:uid": {
    "entityId": "output_column:uid",
    "line": 3,
    "col": 3,
    "rangeType": "exact",
    "raw": "user_id as uid"
  }
}
```

坐标规则：

- `line` 和 `col` 都是 1-based，兼容 Monaco。
- 简单字段、alias、表达式 alias 返回 `exact`。
- `select *` 展开后的字段共用 `*` 的位置，标记为 `approximate`。

## API 接入

修改：

```text
backend/app/api/analyze_controller.py
```

Analyze 现在会在 `analysis_options.include_source_location = true` 时填充：

```text
source_locations
```

同时新增 `source_location` stage_status。定位失败或近似定位不会影响主流程成功/失败。

版本号同步升级：

```text
schema_version = 0.3.0-c08
analysis_id = analysis:c08
```

## 前端接入

修改：

```text
frontend/src/types/lineage.ts
frontend/src/App.tsx
```

前端 `BackendAnalysisResult` 新增：

```text
source_locations?: Record<string, SourceLocation>
```

Analyze 成功后写入：

```text
state.sourceLocations = result.source_locations ?? {}
```

因此现有 `DetailPanel`、`LineageCanvas/highlight.ts`、`SqlEditorPanel` 的 Locate SQL 链路可以拿到真实后端位置。

## 测试覆盖

新增：

```text
backend/tests/test_source_location_service.py
backend/tests/integration/test_analyze_api_c08.py
```

覆盖：

- `select a as aa from t` 能定位到 `output_column:aa`
- 多行 SELECT 使用 1-based line/col
- `select *` 展开字段返回 approximate 位置
- CTE SQL 定位最终 SELECT，而不是 CTE 内部 SELECT
- API 尊重 `include_source_location = false`

前端补充：

```text
frontend/src/__tests__/analyzeFlow.test.tsx
```

验证后端返回的 `source_locations` 会进入前端状态，并在字段详情中显示位置。

## 当前边界

已完成：

- 最终 SELECT 输出项基础定位
- 简单字段、alias、表达式 alias 的 raw 片段定位
- `select *` approximate 定位
- 前后端 source_locations 链路贯通

暂不宣称完成：

- 嵌套子查询中每一层字段的精确定位
- 中文别名 UTF-16 精确 offset
- SQL formatter 后的位置映射
- 表达式内部每个依赖字段的位置拆分
