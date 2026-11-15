# 开发说明：CTE ExpressionAnalyzer 接入 build_cte_schemas

## 1. 修改范围

建议只改：

```text
services/build_cte_schemas 相关文件
或当前承载 build_cte_schemas 的 service 文件
```

可以新增 helper 文件：

```text
cte_scope_resolver.py
expression_dependency_resolver.py
transform_type.py
```

不建议改：

```text
name_resolver.py
expression_analyzer.py
graph_builder.py
frontend
```

Controller 原则上不改。如果 `build_cte_schemas` 新增 diagnostics 后当前 assemble 无法透传，则仅做最小透传改动。

## 2. 实施步骤

### Step 1：确认 build_cte_schemas 当前输入输出

检查当前函数是否类似：

```python
build_cte_schemas(tree, metadata, cte_names)
```

或：

```python
build_cte_schemas(cte_structure, metadata)
```

目标是不破坏旧调用，必要时新增 optional 参数。

### Step 2：新增 CTE schema 数据模型

如果已有类似模型，优先复用；如果没有，参考：

```python
ColumnRef
ColumnDependency
RelationRef
CteSchemaBuildResult
```

### Step 3：新增 extract_select_scope

从当前 CTE body 的 FROM/JOIN 中提取：

```text
alias → real relation
relation name → real relation
```

示例：

```sql
from search_base a join dim_city c
```

产出：

```text
a → search_base
search_base → search_base
c → dim_city
dim_city → dim_city
```

### Step 4：保留 name_resolver 路径

原逻辑不删。先运行 name_resolver，把简单列映射写入 schema。

### Step 5：追加 ExpressionAnalyzer 路径

调用：

```python
expr_metrics = ExpressionAnalyzer().analyze_select(inner_select)
```

对每个 metric：

```text
如果 schema 已有该 output_column：跳过或只补 expression
否则解析 metric.depends_on
```

### Step 6：解析 depends_on

处理三种形态：

```text
a.col
relation.col
col
```

必须经过：

```text
scope + cte_schemas + metadata
```

不要只看 `cte_names`。

### Step 7：特殊表达式

`metric.depends_on` 为空时，不要一律报错。

根据表达式识别：

```text
count(*) → relation_rowset
constant → constant
current_date → system_function
```

### Step 8：补回归测试

至少覆盖 docs/03_regression_tests.md 里的用例。

## 3. 代码迁移注意事项

### 3.1 import 路径

本包 `core_code` 里的代码是参考实现，项目中需要根据实际包路径调整 import。

例如：

```python
from app.services.expression_analyzer import ExpressionAnalyzer
from app.services.name_resolver import resolve_column_lineage_names
from app.domain.diagnostics_model import AMBIGUOUS_COLUMN
```

### 3.2 sqlglot API 差异

不同 sqlglot 版本的 AST 字段可能略有差异。建议优先使用：

```python
select_expr.find_all(exp.Table)
select_expr.args.get("joins")
select_expr.args.get("from")
```

如果项目已有 `_table_references()` 或 alias 提取函数，优先复用，避免重复实现。

### 3.3 字段大小写

建议内部比较使用 lower-case key：

```python
relation_key = relation_name.lower()
column_key = column_name.lower()
```

但输出保留原始大小写。

### 3.4 不要过度承诺端到端

本改造只补齐 CTE schema。真正端到端血缘仍由 rollup 完成。

即本轮产物是：

```text
search_result.search_times → search_base.search_request_uid
```

最终能否变成：

```text
dwd_search_log.search_request_uid → search_result.search_times → output.search_times
```

取决于 rollup 是否已经能递归穿透 `search_base`。
