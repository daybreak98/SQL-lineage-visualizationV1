# C10 Golden Case 回归冻结实现说明

## 本轮目标

C10 不新增大型血缘能力，重点是把已经完成的核心路径固化成可重复运行的回归基线。

这轮做的事情可以理解为：把几条最重要的 SQL 和 metadata 保存成标准样例，然后让测试每次都用真实 API 跑一遍，确认返回契约、图节点、图边和诊断没有被后续开发破坏。

## 新增 Golden Case 资产

新增目录：

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

初学者理解：

- `.sql` 文件就是验收样例，后续改代码时不要临时在测试里拼字符串。
- `c06_metadata.json` 是元数据样例，给 `select *` 展开、字段存在性校验、歧义字段判断使用。
- 把样例文件独立出来后，人和测试都能读同一份输入，减少“测试里藏逻辑”的问题。

## 新增后端回归测试

新增文件：

```text
backend/tests/integration/test_analyze_api_c10.py
```

覆盖能力：

```text
metadata commit/query
output_fields parse
single-table column lineage
join alias lineage
CTE structure graph
select * expansion
UNKNOWN_COLUMN diagnostic
AMBIGUOUS_COLUMN diagnostic
expression SQL current partial behavior
```

每个 analyze case 都会统一检查 GraphViewModel 完整性：

```text
node id 不能重复
edge id 不能重复
每条 edge.source 必须存在于 nodes
每条 edge.target 必须存在于 nodes
```

初学者理解：

血缘图最容易出现的问题不是“没有图”，而是“边指向了不存在的节点”。这种坏图前端会表现成线丢失、布局异常、点击详情找不到对象。C10 把这个作为所有 Golden Case 的共同底线。

## 关于 C09 表达式用例

`c09_expression_metric.sql` 已加入 Golden Case，但当前后端还没有真正实现表达式依赖穿透。

所以本轮测试冻结的是当前真实行为：

```text
能解析输出字段 gmv/order_cnt/adr
返回 partial
返回 UNSUPPORTED_COMPLEX_QUERY 诊断
不生成断裂的字段血缘边
```

等后续真正实现 C09 表达式依赖时，再把这个 case 的预期升级为：

```text
gmv -> dwd_order_di.order_amount
order_cnt -> dwd_order_di.order_no
adr -> dwd_order_di.order_amount + dwd_order_di.order_no
```

## 验证结果

本轮验证命令：

```text
backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_analyze_api_c10.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
npm test -- --run
npm run typecheck
npm run build
```

结果：

```text
C10 backend integration: 8 passed
Backend full suite: 126 passed, 1 warning
Frontend tests: 97 passed
Frontend typecheck: passed
Frontend build: passed
```

## 本轮开发路径

1. 阅读 C10 文档和验收 SQL，确认本轮是回归冻结，不是扩功能。
2. 把 SQL 和 metadata 独立为 Golden Case 文件。
3. 新增 C10 API 集成测试，全部走真实 FastAPI TestClient。
4. 抽出通用 graph integrity 检查，所有 case 共享。
5. 对每条关键 SQL 写最小但稳定的预期。
6. 跑 C10 单测、后端全量测试、前端测试、类型检查和构建。

## 当前冻结边界

已经冻结：

- C03 单表字段血缘
- C04 Join 别名字段归属
- C05 CTE 结构依赖图
- C06 metadata 导入查询
- C07 select * 展开与 unknown/ambiguous 诊断
- GraphViewModel 节点边完整性

尚未宣称完成：

- C08 SourceLocation 精确定位
- C09 表达式依赖穿透
- 多层嵌套子查询字段级穿透
- 生产级超长 SQL 的完整字段血缘还原
