# C01｜Analyze 占位响应与前端按钮打通

## 1. 本轮目标

让前端 Analyze 按钮真正调用后端，但后端暂不做真实 SQL 血缘。

```text
后端能力：POST /api/sql/analyze 返回稳定 AnalysisResult 空图
前端效果：点击 Analyze 后展示 partial 状态和 info 诊断
学习重点：POST 请求、Pydantic 请求体、稳定响应契约
```

---

## 2. 本轮允许创建

```text
backend/app/api/analyze_controller.py
backend/tests/integration/test_analyze_api_c01.py
```

可以少量修改：

```text
backend/app/main.py
```

---

## 3. API 契约

请求：

```http
POST /api/sql/analyze
```

响应核心：

```json
{
  "schema_version": "0.3.0-c01",
  "analysis_id": "analysis:c01",
  "status": "partial",
  "confidence_level": "unknown",
  "diagnostics_report": {
    "diagnostics": [
      {
        "code": "C01_PLACEHOLDER",
        "level": "info",
        "message": "Analyze endpoint is available. SQL parsing starts from C02."
      }
    ],
    "error_count": 0,
    "warning_count": 0,
    "info_count": 1
  },
  "graph_view_model": {
    "view_mode": "column",
    "nodes": [],
    "edges": []
  },
  "output_fields": []
}
```

---

## 4. 前端对接文档

前端点击 Analyze 后：

```text
1. 按钮进入 loading / analyzing
2. 请求 POST /api/sql/analyze
3. 返回 partial 后，页面进入 analyzed-with-warning 或 analyzed 状态
4. 诊断面板展示 C01_PLACEHOLDER
5. 画布为空，但不能报错
```

前端不要因为 nodes 为空就认为失败。

---

## 5. 测试验收

后端测试：

```text
POST /api/sql/analyze 返回 200
status == partial
graph_view_model.nodes == []
graph_view_model.edges == []
diagnostics_report.info_count == 1
```

前端验收：

```text
点击 Analyze 不再 404
Network 中能看到 /api/sql/analyze
页面显示“后端接口已接通，但 SQL 解析后续实现”类似信息
```

---

## 6. 禁止越界

本轮不要：

```text
调用 SQLGlot
构造 fake 字段血缘
返回 success
改前端图谱算法
```

---

## 7. 给 OpenCode 的单轮提示词

```text
请只实现 C01：POST /api/sql/analyze 占位响应。
要求返回稳定 AnalysisResult 空图契约，status 必须是 partial，不允许伪装 success。
前端点击 Analyze 应能收到响应并展示 info 诊断。
不要接入 SQLGlot，不要生成假图。
实现后运行 C00 和 C01 测试，并说明前端 Network 与页面如何验收。
```
