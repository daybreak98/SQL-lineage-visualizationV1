# API 与诊断说明

## 1. `/api/sql/analyze` 兼容策略

本次改造没有替换现有接口，而是在原有返回结构上做增量扩展。

### 保持兼容的字段
- `schema_version`
- `analysis_id`
- `status`
- `confidence_level`
- `elapsed_ms`
- `dialect`
- `stage_statuses`
- `unsupported_features`
- `diagnostics_report`
- `graph_view_model`
- `output_fields`
- `summary`

### 新增字段
- `analysis_sql`
- `diagnostics`
- `sql_text_bundle`
- `preflight_report`
- `segments`
- `parse_attempts`
- `capabilities`
- `confidence`

## 2. 响应结构补充说明

### `sql_text_bundle`

用于同时保留三份 SQL 文本与 placeholder 信息：

```json
{
  "original_sql": "...",
  "normalized_sql": "...",
  "analysis_sql": "...",
  "has_normalized_sql": true,
  "has_analysis_sql": true,
  "placeholder_count": 2,
  "placeholders": [],
  "offset_mapping": {}
}
```

### `preflight_report`

用于输出预检风险信号：

```json
{
  "char_count": 1234,
  "line_count": 45,
  "max_parentheses_depth": 3,
  "quote_balance_ok": true,
  "contains_templates": true,
  "contains_lateral_view": false,
  "contains_regex_functions": true,
  "contains_json_functions": true,
  "complexity_score": 9,
  "risk_flags": []
}
```

### `segments`

用于输出顶层 SQL 结构切段结果：

```json
{
  "segment_id": "seg_0001",
  "segment_type": "cte_item",
  "raw_text": "a as (select ...)",
  "start_offset": 10,
  "end_offset": 80,
  "parent_segment_id": "seg_0000",
  "parse_status": "success"
}
```

### `parse_attempts`

记录完整 parse 尝试顺序与结果：

- `original_sql`
- `normalized_sql`
- `analysis_sql`

必要时保留失败信息，用于评审和排障。

## 3. `status` 语义

### `success`
- 能拿到完整 parse tree
- 后续 graph / lineage 服务可继续走现有链路

### `partial`
- 完整 parse 失败，但 segment fallback 仍恢复出部分结构
- 返回 diagnostics 与 segments
- 不保证能产出完整 graph / lineage

### `failed`
- 既没有完整 parse tree，也没有有效 segment recovery
- 典型例子是简单但彻底非法的 SQL，如 `select from`

## 4. Diagnostics 说明

### 预检类
- `COMPLEX_SQL_DETECTED`
- `LONG_SQL_DETECTED`
- `TEMPLATE_SQL_DETECTED`
- `FREEMARKER_BLOCK_DETECTED`
- `UNBALANCED_PARENTHESES_WARNING`
- `UNBALANCED_QUOTES_WARNING`
- `ROW_EXPANDING_FUNCTION`
- `INVISIBLE_CHARACTER_DETECTED`

### Shield 类
- `LITERAL_SHIELD_APPLIED`
- `REGEX_LITERAL_SHIELD_APPLIED`
- `JSON_PATH_LITERAL_SHIELD_APPLIED`
- `HINT_SHIELD_APPLIED`

### Parse / fallback 类
- `SQLGLOT_PARSE_ERROR`
- `SQLGLOT_NOT_INSTALLED`
- `SEGMENT_PARSE_FALLBACK`
- `PARTIAL_PARSE_RESULT`
- `SQL_PARSE_ERROR`

### 能力边界类
- `UNSUPPORTED_SQL_STRUCTURE`
- `UNSUPPORTED_LATERAL_VIEW`
- `BLACK_BOX_UDF`
- `LOW_CONFIDENCE_LINEAGE`
- `ANALYSIS_TIMEOUT`

## 5. 评审时建议重点关注

- `status` 是否能区分坏 SQL 与可降级复杂 SQL
- 新增字段是否足够支撑后续字段级血缘扩展
- diagnostics 是否能说明“为什么 partial / 为什么降级”
- `lateral view / explode` 是否做到“宁可降级，不造假结果”

