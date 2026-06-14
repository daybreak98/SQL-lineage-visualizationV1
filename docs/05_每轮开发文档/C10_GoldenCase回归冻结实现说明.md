# C10 Golden Case 回归冻结实现说明

## 本轮目标

C10 的目标是把已经稳定的核心 SQL 场景沉淀成可重复运行的 Golden Case 回归基线。

它不是新增大功能，而是保证后续开发不会破坏：

```text
1. output_fields 解析
2. 单表字段血缘
3. Join 别名字段归属
4. CTE 结构依赖
5. metadata 导入与查询
6. select * 展开
7. UNKNOWN_COLUMN / AMBIGUOUS_COLUMN 诊断
8. 表达式退化字段依赖
9. GraphViewModel 节点和边完整性
```

## Golden Case 资产

目录：

```text
backend/tests/golden_cases/
```

包含：

```text
c02_output_fields.sql
c03_single_table.sql
c04_join_alias.sql
c05_cte_metric.sql
c06_metadata.json
c07_select_star.sql
c07_unknown_column.sql
c07_ambiguous_column.sql
c09_expression_metric.sql
```

这些文件是后续回归的稳定输入，不再把关键 SQL 临时写在测试函数里。

## 后端回归测试

测试文件：

```text
backend/tests/integration/test_analyze_api_c10.py
```

覆盖：

```text
metadata commit/query
output_fields parse
single-table column lineage
join alias lineage
CTE structure graph
select * expansion
UNKNOWN_COLUMN diagnostic
AMBIGUOUS_COLUMN diagnostic
expression SQL degraded column dependencies
```

所有 Golden Case 都会检查图完整性：

```text
node id 不重复
edge id 不重复
edge.source 必须存在于 nodes
edge.target 必须存在于 nodes
```

## 关于表达式 SQL

`c09_expression_metric.sql` 当前冻结的是“退化字段依赖”能力，而不是完整 C09 表达式语义。

示例：

```sql
SELECT
  SUM(order_amount) AS gmv,
  COUNT(DISTINCT order_no) AS order_cnt,
  SUM(order_amount) / COUNT(DISTINCT order_no) AS adr
FROM dwd_order_di
```

当前预期：

```text
status: success
outputs: gmv, order_cnt, adr
不返回 UNSUPPORTED_COMPLEX_QUERY
不要求 expression 节点
不要求 semantics_report.metrics
```

字段依赖：

```text
dwd_order_di.order_amount -> gmv
dwd_order_di.order_no     -> order_cnt
dwd_order_di.order_amount -> adr
dwd_order_di.order_no     -> adr
```

完整表达式语义仍暂缓：

```text
expression 节点
expression_dependency 边
expression_to_output 边
口径详情
聚合函数 / distinct / 除法语义解释
```

## 当前验证结果

本轮后端验证：

```text
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
143 passed, 1 warning
```

## 当前冻结边界

已冻结：

```text
C03 单表字段血缘
C04 Join 别名字段归属
C05 CTE 结构依赖图
C06 metadata 导入查询
C07 select * 展开与 unknown/ambiguous 诊断
C08 SourceLocation 基础定位
表达式退化字段依赖
GraphViewModel 节点边完整性
```

尚未宣称完成：

```text
完整 C09 表达式语义
多层嵌套子查询字段穿透
生产级超长 SQL 的完整字段血缘
```
