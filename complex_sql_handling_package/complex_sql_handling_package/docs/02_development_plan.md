# 复杂 SQL 处理开发计划

## 1. 总目标

让项目可以面对 1000 行级 Hive/Spark SQL 时：

```text
不崩溃
不误报
可局部解析
可定位问题
可输出 partial lineage
可持续用 Golden Case 回归
```

---

## 2. 迭代阶段

## P0：复杂 SQL 预处理与容错解析骨架

### 目标

先让系统具备复杂 SQL 的输入保护、分段和诊断能力。

### 后端任务

| 编号 | 任务 | 验收 |
|---|---|---|
| P0-1 | 增加三文本模型 | 返回 original_sql / normalized_sql / analysis_sql |
| P0-2 | 实现 PreflightChecker | 能识别长度、行数、括号、引号风险 |
| P0-3 | 实现 LiteralShield | 复杂正则、JSONPath 不干扰分段 |
| P0-4 | 实现 TemplateShield | `${...}`、`#{...}` 被替换为 placeholder |
| P0-5 | 实现 SqlSegmenter | 能切出 cte/main_select/from_join/where 等段 |
| P0-6 | 实现 ParserAdapter | sqlglot 可选；未安装时返回诊断 |
| P0-7 | 实现 ComplexSqlAnalyzer | 编排预检、屏蔽、分段、解析尝试 |
| P0-8 | 加 unittest | 核心 shield/segment/analyzer 测试通过 |

### 不做事项

```text
不做完整字段血缘
不做复杂表达式语义理解
不做 SQL 自动修复
不修改 original_sql
```

---

## P1：接入字段血缘引擎

### 目标

让复杂 SQL 处理层为字段血缘提供稳定输入。

### 后端任务

| 编号 | 任务 | 验收 |
|---|---|---|
| P1-1 | segments 接入 ScopeResolver | CTE / main query 可分别构建 scope |
| P1-2 | placeholder mapping 接入 SourceLocation | 图谱点击仍能回到 original_sql |
| P1-3 | lateral view 初步建模 | explode 输出虚拟字段 |
| P1-4 | UDF 黑盒依赖建模 | UDF 输入字段可追踪，内部不展开 |
| P1-5 | partial lineage API | 单段失败不影响其他段输出 |

---

## P2：生产 SQL 语料库与降级策略

### 目标

用真实生产 SQL 驱动能力增强。

### 后端任务

| 编号 | 任务 | 验收 |
|---|---|---|
| P2-1 | 建生产 SQL 匿名化工具 | 表名/字段名/业务值可脱敏 |
| P2-2 | 建复杂度评分 | 输出 sql_complexity_score |
| P2-3 | 建 stage_statuses | 每阶段耗时、状态、失败原因可观测 |
| P2-4 | 扩展 Golden Case | 覆盖 100+ 个复杂 SQL 场景 |
| P2-5 | 超时保护 | 单 SQL 超时返回 partial_result |

---

## 3. 关键验收用例

### Case 1：复杂正则不破坏解析

```sql
select regexp_extract(url, 'https?://([^/]+)/([^?]+)\\?.*', 2) as path
from log_table
where dt='${DATE}'
```

验收：

```text
1. 正则字符串被 shield。
2. ${DATE} 被 shield。
3. from 表可识别。
4. status 至少 partial，不得 failed。
```

### Case 2：lateral view explode

```sql
select t.order_id, item.amount
from order_table t
lateral view explode(t.refund_items) e as item
where t.dt='20260604'
```

验收：

```text
1. 识别 lateral_view segment。
2. refund_items 标记为 row expanding input。
3. item 标记为 virtual column。
```

### Case 3：多层 CTE

```sql
with a as (...), b as (...), c as (...)
select ... from c
```

验收：

```text
1. CTE block 被识别。
2. 主查询被识别。
3. 单个 CTE 内部失败不影响主查询分段结果。
```

---

## 4. Definition of Done

```text
1. 所有新增代码有 unittest。
2. original_sql 不被修改。
3. placeholder 可回溯 raw_text 和 offset。
4. parse 失败必须有 diagnostic。
5. 对复杂 SQL 默认返回 partial，而不是直接 failed。
6. API response 包含 stage_statuses、diagnostics、capabilities。
```
