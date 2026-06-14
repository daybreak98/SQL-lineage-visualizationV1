# Golden Case 与回归测试方案

## 1. 目标

复杂 SQL 支持不能靠人工感觉，需要通过 Golden Case 固化。

```text
每新增一个复杂能力，必须增加对应 Golden Case。
每修复一个解析 bug，必须增加回归用例。
每次升级 sqlglot 或预处理逻辑，必须跑全量 Golden Case。
```

---

## 2. 目录结构

```text
golden_cases/
  dirty_regex_template_001/
    input.sql
    metadata.json
    expected.complex_sql_result.json
    README.md
```

---

## 3. Case 元信息

README.md 必须包含：

| 字段 | 说明 |
|---|---|
| case_id | 用例 ID |
| difficulty | S0/S1/S2/S3 |
| dialect | hive/spark |
| covered_features | 覆盖能力 |
| expected_behavior | 期望行为 |
| allowed_partial | 是否允许 partial |
| known_limitations | 已知限制 |

---

## 4. 复杂 SQL 特征覆盖矩阵

| 特征 | 优先级 | 说明 |
|---|---|---|
| 单表 alias | P0 | 字段血缘基础 |
| 多 join 同名字段 | P0 | 字段消歧基础 |
| 复杂正则 | P0 | LiteralShield 必须覆盖 |
| JSONPath | P0 | get_json_object 常见 |
| 模板变量 | P0 | 生产 SQL 常见 |
| 多层 CTE | P1 | 复杂 SQL 主体 |
| from 子查询 | P1 | 作用域回溯 |
| lateral view explode | P1 | Hive/Spark 常见 |
| union all | P1 | 字段对齐 |
| case when | P1 | 指标口径常见 |
| window function | P2 | 去重和排序口径 |
| 自定义 UDF | P2 | 黑盒依赖 |
| Freemarker | P2 | 模板化 SQL |
| 超长 SQL | P2 | 性能与降级 |

---

## 5. 回归标准

```text
1. P0 case 必须 success 或预期 partial。
2. 不允许新增未知 failed。
3. placeholder 数量和类型应稳定。
4. segment 数量允许小幅变化，但主结构必须存在。
5. diagnostics code 变化必须人工确认。
```
