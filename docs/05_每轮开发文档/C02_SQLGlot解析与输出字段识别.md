# C02｜SQLGlot 解析与输出字段识别

## 1. 本轮目标

接入 SQLGlot，但只做“能否解析 SQL”和“最终 SELECT 输出字段识别”。

```text
后端能力：parse SQL，识别 output_fields
前端效果：Analyze 后输出字段入口 / 搜索框可看到字段名
学习重点：第三方库封装、解析失败处理、不要暴露 AST
```

---

## 2. 本轮允许创建

```text
backend/app/adapters/sqlglot_adapter.py
backend/app/services/sql_parse_service.py
backend/tests/test_sql_parse_service.py
backend/tests/integration/test_analyze_api_c02.py
```

可以修改：

```text
backend/app/api/analyze_controller.py
```

---

## 3. 后端实现范围

输入：

```sql
select country_name, count(order_no) as order_cnt from dwd_order_di group by country_name
```

输出：

```json
"output_fields": [
  {
    "name": "country_name",
    "display_name": "country_name",
    "expression": "country_name",
    "source_type": "unknown"
  },
  {
    "name": "order_cnt",
    "display_name": "order_cnt",
    "expression": "COUNT(order_no)",
    "source_type": "expression"
  }
]
```

本轮只识别最终输出字段，不要求知道字段来自哪张表。

---

## 4. 失败处理

SQLGlot 解析失败时：

```json
{
  "status": "failed",
  "diagnostics_report": {
    "diagnostics": [
      {
        "code": "SQL_PARSE_ERROR",
        "level": "error",
        "message": "..."
      }
    ],
    "error_count": 1
  },
  "graph_view_model": { "nodes": [], "edges": [] }
}
```

---

## 5. 前端对接文档

前端 Analyze 成功后：

```text
1. Search / Output selector 使用 result.output_fields
2. 不输入搜索词时，可展示 default outputs
3. 点击输出字段暂时只选中字段，不要求出现血缘路径
```

错误 SQL：

```text
页面进入 failed
Search 禁用
诊断面板展示 SQL_PARSE_ERROR
```

---

## 6. 测试验收

必须通过：

```text
select a from t → output_fields = [a]
select a as aa from t → output_fields = [aa]
select count(*) as cnt from t → output_fields = [cnt]
错误 SQL → status = failed, code = SQL_PARSE_ERROR
```

---

## 7. 禁止越界

本轮不要：

```text
推断字段来自哪张表
生成字段血缘边
做 CTE 递归
做 SQLite 元数据
```

---

## 8. 给 OpenCode 的单轮提示词

```text
请只实现 C02：接入 SQLGlot 解析并识别最终 SELECT 输出字段。
不要做字段来源归属，不要生成血缘边。
Analyze 响应中填充 output_fields；解析失败必须返回 failed 和 SQL_PARSE_ERROR。
前端应能用 output_fields 展示输出字段入口。
实现后补充 parse service 单测和 analyze API 集成测试。
```
