# 复杂 SQL 处理总架构设计

## 1. 背景与问题定义

生产环境 SQL 的复杂度主要体现在：

| 类型 | 示例 | 风险 |
|---|---|---|
| 超长 SQL | 1000 行、多层 CTE | 单次 parse 失败导致全局失败 |
| 多 join | 十几到几十张表 | 字段归属、join context、同名字段消歧困难 |
| 复杂函数 | explode、posexplode、json_tuple、UDF | 行展开、虚拟字段、黑盒表达式 |
| 复杂正则 | regexp_extract(url, '^[^?]+', 0) | 正则特殊字符干扰简单扫描器 |
| 字符串复杂 | 单引号、双引号、反斜杠、JSONPath | 暴力替换会破坏 SQL 原文语义 |
| 模板变量 | ${DATE}、${zdt...}、<#if> | 非 Hive/Spark 标准语法，但生产常见 |
| 方言差异 | Hive/Spark 函数和 lateral view | 通用 SQL parser 易误判 |

核心判断：

```text
生产 SQL 解析不是追求永远 parse 成功，
而是失败时不崩、不瞎猜、可局部恢复、可解释 partial。
```

---

## 2. 总体架构

```text
AnalyzeController
  ↓
ComplexSqlAnalyzer
  ├─ PreflightChecker
  │   ├─ 长度 / 行数 / 字符编码检查
  │   ├─ 括号 / 引号粗校验
  │   └─ 风险特征识别
  │
  ├─ DirtySqlPreprocessor
  │   ├─ CommentScanner
  │   ├─ LiteralShield
  │   ├─ TemplateShield
  │   ├─ HintShield
  │   ├─ DialectNormalizer
  │   └─ PlaceholderMapping
  │
  ├─ SqlSegmenter
  │   ├─ CTE Segment
  │   ├─ SELECT Segment
  │   ├─ FROM/JOIN Segment
  │   ├─ WHERE/GROUP/HAVING Segment
  │   └─ UNION Branch Segment
  │
  ├─ ParserAdapter
  │   ├─ sqlglot parse dialect=spark/hive
  │   ├─ normalized_sql fallback
  │   └─ segment-level fallback
  │
  └─ ComplexSqlAnalysisResult
      ├─ text_bundle
      ├─ preflight_report
      ├─ segments
      ├─ parse_attempts
      ├─ diagnostics
      └─ capability / confidence
```

---

## 3. 三文本模型

必须同时维护三份 SQL 文本：

| 文本 | 说明 | 用途 |
|---|---|---|
| `original_sql` | 用户输入原文，禁止修改 | 展示、SourceLocation、SQL diff |
| `normalized_sql` | 可逆规范化 SQL | parser 更稳定解析 |
| `analysis_sql` | 字符串、模板、hint 屏蔽后的 SQL | 分段、容错解析 |

示例：

```sql
regexp_extract(url, '^[^?]+', 0) as url_path
```

在 `analysis_sql` 中可变为：

```sql
regexp_extract(url, __STR_0001__, 0) as url_path
```

同时保存：

```json
{
  "__STR_0001__": {
    "kind": "string_literal",
    "raw_text": "'^[^?]+'",
    "start_offset": 22,
    "end_offset": 30
  }
}
```

---

## 4. DirtySqlPreprocessor 设计

### 4.1 CommentScanner

识别但不直接丢弃：

```sql
-- line comment
/* block comment */
/*+ MAPJOIN(t) */
```

Hint 必须保留，因为可能影响 join 策略解释。

### 4.2 LiteralShield

屏蔽以下内容：

```text
普通字符串
双引号字符串
正则字符串
JSONPath 字符串
URL 字符串
包含转义符的字符串
```

原则：

```text
不理解正则语义，只保护正则文本。
字段血缘只需要知道 regexp_extract 的输入字段。
```

### 4.3 TemplateShield

识别：

```text
${DATE}
${zdt.addDay(-1).format("yyyyMMdd")}
#{param}
<#if xxx> ... </#if>
<#list xxx as item> ... </#list>
```

处理策略：

| 模板类型 | 策略 |
|---|---|
| `${...}` | 替换为 `__TPL_xxxx__` |
| `#{...}` | 替换为 `__TPL_xxxx__` |
| `<#if>` 块 | 标记 `CONDITIONAL_SQL_TEMPLATE` |
| `<#list>` 块 | 标记 `LOOP_SQL_TEMPLATE` |

---

## 5. 分段解析策略

### 5.1 不按行切分

错误做法：

```text
每 100 行切一次
```

正确做法：

```text
按 token + 括号深度 + 顶层 clause 切分
```

### 5.2 分段类型

| segment_type | 说明 |
|---|---|
| `statement` | 单条 SQL statement |
| `cte_block` | WITH 块整体 |
| `cte_item` | 单个 CTE |
| `main_select` | 主 SELECT |
| `select_list` | SELECT 字段区 |
| `from_join` | FROM/JOIN 区 |
| `where` | WHERE 区 |
| `group_by` | GROUP BY 区 |
| `having` | HAVING 区 |
| `union_branch` | UNION 分支 |
| `lateral_view` | lateral view 块 |

### 5.3 partial 策略

如果完整 SQL parse 失败：

```text
1. 尝试 normalized_sql。
2. 尝试 analysis_sql。
3. 尝试 CTE / main query 分段。
4. 尝试 from/join 局部抽取表级血缘。
5. 返回 partial，不直接 failed。
```

---

## 6. 方言 Profile

```python
@dataclass
class DialectProfile:
    name: str
    parser_dialect: str
    double_quote_mode: str
    backtick_mode: str
    template_enabled: bool
    lateral_view_enabled: bool
    raw_string_enabled: bool
```

默认配置：

| 方言 | parser_dialect | 说明 |
|---|---|---|
| hive | hive | Hive SQL |
| spark | spark | Spark SQL |

---

## 7. 字段血缘与复杂函数处理原则

复杂函数分三类：

| 类型 | 示例 | 血缘策略 |
|---|---|---|
| 透明函数 | cast、coalesce、nvl、trim | 输入字段 → expression → 输出字段 |
| 结构展开函数 | explode、posexplode、inline | 输入字段 → udtf → 虚拟字段，并标记行展开 |
| 黑盒函数 | 自定义 UDF | 输入字段 → udf → 输出字段，confidence=medium |

---

## 8. 诊断体系

建议新增诊断码：

```text
SQL_TOO_LONG
UNBALANCED_PARENTHESES
UNBALANCED_QUOTES
TEMPLATE_SQL_DETECTED
CONDITIONAL_SQL_TEMPLATE
STRING_LITERAL_SHIELDED
HINT_DETECTED
SQLGLOT_NOT_INSTALLED
PARSE_ERROR
SEGMENT_PARSE_ERROR
PARTIAL_PARSE_RESULT
UNSUPPORTED_LATERAL_VIEW
BLACK_BOX_UDF
LOW_CONFIDENCE_LINEAGE
ANALYSIS_TIMEOUT
```

---

## 9. 接入现有项目的边界

新增 `ComplexSqlAnalyzer` 不替代现有血缘引擎，而是作为前置层。

```text
ComplexSqlAnalyzer 输出：
- original_sql
- normalized_sql
- analysis_sql
- placeholder mapping
- segments
- parse attempts
- diagnostics

现有 LineageEngine 继续负责：
- ScopeResolver
- NameResolver
- LineageIR
- GraphViewModel
```

这样可以避免一次性重构过大。
