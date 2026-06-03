# 03｜后端最小契约：AnalysisResult 稳定版

> 本文定义 C01 起就应稳定下来的最小响应结构。后续功能只往里面填内容，不随意改字段名。

---

## 1. Analyze 请求体

```json
{
  "sql": "select a from t",
  "dialect": "spark",
  "analysis_level": "column",
  "default_catalog": "default",
  "default_schema": "default",
  "metadata_version": "latest",
  "case_sensitive": false,
  "analysis_options": {
    "include_graph": true,
    "include_semantics": false,
    "include_diagnostics": true,
    "include_source_location": true,
    "include_expression_lineage": false
  }
}
```

初学者实现时，C01-C03 可以先只真正使用：

```text
sql
dialect
analysis_options.include_graph
```

其他字段先接收并透传，不强制实现功能。

---

## 2. Analyze 响应体最小结构

```json
{
  "schema_version": "0.3.0-beginner",
  "analysis_id": "analysis:xxx",
  "status": "success | partial | failed",
  "confidence_level": "high | medium | low | unknown",
  "confidence_reasons": [],
  "elapsed_ms": 12,
  "dialect": "spark",
  "normalized_sql": null,
  "stage_statuses": [],
  "unsupported_features": [],
  "diagnostics_report": {
    "diagnostics": [],
    "error_count": 0,
    "warning_count": 0,
    "info_count": 0
  },
  "graph_view_model": {
    "view_mode": "column",
    "nodes": [],
    "edges": []
  },
  "output_fields": [],
  "source_locations": {},
  "metadata_context": {},
  "semantics_report": null
}
```

---

## 3. 状态语义

| status | 语义 | 前端表现 |
|---|---|---|
| success | 本轮能力范围内分析成功 | 可正常展示图、搜索、详情 |
| partial | 接口成功，但有能力未实现或部分字段未知 | 展示图，同时展示 warning / info |
| failed | SQL 解析失败或服务异常 | 画布进入失败态，搜索禁用 |

禁止把未实现功能返回成 `success`。

---

## 4. GraphViewModel 最小节点

```json
{
  "id": "column:t.a",
  "node_type": "column",
  "label": "t.a",
  "title": "t.a",
  "subtitle": "physical column",
  "data": {
    "column_name": "a",
    "table_name": "t"
  }
}
```

推荐 node_type：

```text
table
physical_column
cte
cte_column
subquery
subquery_column
output
output_column
expression
unknown
query_result
```

---

## 5. GraphViewModel 最小边

```json
{
  "id": "edge:column:t.a->output:a",
  "source": "column:t.a",
  "target": "output:a",
  "edge_type": "column_lineage",
  "label": "lineage",
  "data": {
    "confidence": "high"
  }
}
```

要求：

1. `source` 必须指向已存在 node id。
2. `target` 必须指向已存在 node id。
3. 边不能悬空。
4. 不能为了前端好看伪造无证据的强血缘边。

---

## 6. diagnostics 最小结构

```json
{
  "diagnostic_id": "diag:001",
  "code": "UNKNOWN_COLUMN",
  "level": "warning",
  "message": "Column user_name cannot be resolved from known tables.",
  "suggestion": "Import metadata or check table alias."
}
```

推荐 level：

```text
info
warning
error
```

推荐 code：

```text
C01_PLACEHOLDER
SQL_PARSE_ERROR
UNKNOWN_COLUMN
AMBIGUOUS_COLUMN
UNSUPPORTED_SELECT_STAR
UNSUPPORTED_COMPLEX_QUERY
METADATA_MISSING
SOURCE_LOCATION_APPROXIMATE
```

---

## 7. stage_statuses 最小结构

```json
{
  "stage": "sql_parse",
  "status": "success",
  "elapsed_ms": 3,
  "diagnostic_codes": [],
  "message": "SQL parsed by SQLGlot."
}
```

推荐 stage：

```text
request
sql_parse
output_fields
single_table_lineage
join_alias_resolve
cte_subquery_rollup
metadata_lookup
source_location
expression_lineage
graph_build
contract_assemble
```

---

## 8. C01-C10 字段演进原则

| 轮次 | 可以新增/填充的字段 | 不应修改的字段 |
|---|---|---|
| C01 | 空 graph、placeholder diagnostics | status、graph_view_model 基本结构 |
| C02 | output_fields、parse diagnostics | graph node / edge 字段名 |
| C03 | nodes、edges | API 路径 |
| C04 | unknown diagnostics、alias 信息 | 前端交互状态不进后端 |
| C05 | view_mode=subquery_dependency | CTE 不伪装物理表 |
| C06 | metadata_context | Analyze 主契约不重写 |
| C07 | ambiguous / unknown | 不静默忽略错误 |
| C08 | source_locations | Monaco 使用 1-based line / column |
| C09 | semantics_report | 不把解释文字当血缘证据 |
| C10 | golden case snapshots | 不引入破坏性字段改名 |
