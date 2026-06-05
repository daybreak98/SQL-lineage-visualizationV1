# dirty_regex_template_001

| 字段 | 值 |
|---|---|
| difficulty | S1 |
| dialect | spark/hive |
| covered_features | regexp_extract, JSONPath, template variable, CTE |
| allowed_partial | true |

期望：复杂正则、JSONPath、模板变量被 shield，SQL 至少可以完成分段并返回 partial 或 success。
