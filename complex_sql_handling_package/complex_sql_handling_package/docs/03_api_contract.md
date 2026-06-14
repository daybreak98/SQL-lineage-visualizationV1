# API / 数据模型契约

## 1. Analyze 请求

```json
{
  "sql": "select ...",
  "dialect": "spark",
  "metadata_version": "default",
  "options": {
    "enable_literal_shield": true,
    "enable_template_shield": true,
    "enable_segment_parse": true,
    "max_sql_chars": 200000,
    "max_segments": 500
  }
}
```

---

## 2. Complex SQL 分析结果

```json
{
  "status": "success | partial | failed",
  "dialect": "spark",
  "text_bundle": {
    "original_sql": "...",
    "normalized_sql": "...",
    "analysis_sql": "...",
    "placeholders": []
  },
  "preflight_report": {
    "line_count": 1000,
    "char_count": 120000,
    "risk_flags": []
  },
  "segments": [],
  "parse_attempts": [],
  "diagnostics": [],
  "capabilities": {
    "full_parse": false,
    "segment_parse": true,
    "literal_shield": true,
    "template_shield": true
  },
  "confidence": {
    "parse": 0.75,
    "segment": 0.9,
    "lineage_ready": 0.7
  }
}
```

---

## 3. Placeholder 契约

```json
{
  "placeholder": "__STR_0001__",
  "kind": "string_literal | quoted_identifier | template | comment | hint",
  "raw_text": "'^[^?]+'",
  "start_offset": 42,
  "end_offset": 50,
  "start_line": 3,
  "start_col": 22,
  "end_line": 3,
  "end_col": 30
}
```

---

## 4. Segment 契约

```json
{
  "segment_id": "seg_0001",
  "segment_type": "cte_block | main_select | from_join | where | group_by | lateral_view | unknown",
  "raw_text": "from table_a a left join table_b b on ...",
  "start_offset": 100,
  "end_offset": 300,
  "parse_status": "not_attempted | success | partial | failed",
  "diagnostics": []
}
```

---

## 5. Diagnostic 契约

```json
{
  "code": "PARSE_ERROR",
  "severity": "info | warning | error",
  "message": "解析失败，已进入分段解析",
  "location": {
    "start_line": 10,
    "start_col": 5,
    "end_line": 10,
    "end_col": 20
  },
  "stage": "parse",
  "confidence": 0.5,
  "extra": {}
}
```

---

## 6. 与字段血缘模块的输入契约

字段血缘模块不直接使用用户输入 SQL，而应使用：

```text
1. text_bundle.original_sql     # 定位和展示
2. text_bundle.analysis_sql     # 解析友好的 SQL
3. placeholders                 # 回源映射
4. segments                     # 分段解析输入
5. diagnostics                  # 不确定性继承
```

---

## 7. 状态约定

| status | 含义 |
|---|---|
| `success` | 完整解析成功 |
| `partial` | 局部成功，可继续输出部分血缘 |
| `failed` | 无法提供有效结构 |

生产场景中应优先返回 `partial`，除非 SQL 完全不可识别。
