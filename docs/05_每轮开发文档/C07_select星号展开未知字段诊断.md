# C07｜select * 展开、unknown 与 ambiguous 诊断

## 1. 本轮目标

让系统面对真实 SQL 中最常见的不确定性：`select *`、未知字段、歧义字段。

```text
后端能力：基于 SQLite 元数据展开 select *，并结构化诊断 unknown / ambiguous
前端效果：unknown 节点、ambiguous warning、诊断面板可见
学习重点：不确定性建模比硬猜更重要
```

---

## 2. 支持范围

支持：

```sql
select * from dwd_order_di
select o.* from dwd_order_di o
select order_no from dwd_order_di
select user_id from t1 join t2
```

---

## 3. 诊断规则

| 场景 | code | status |
|---|---|---|
| 表不存在元数据 | METADATA_MISSING | partial |
| 字段不存在 | UNKNOWN_COLUMN | partial |
| 多表都有同名字段且 SQL 未限定 | AMBIGUOUS_COLUMN | partial |
| `select *` 无元数据可展开 | SELECT_STAR_METADATA_REQUIRED | partial |

---

## 4. 前端对接文档

前端必须展示：

```text
1. unknown 节点不能隐藏
2. ambiguous 诊断要进入 diagnostics panel
3. partial 结果仍可展示已确认的图
4. 用户能区分“分析失败”和“部分未知”
```

---

## 5. 测试验收

```text
有元数据：select * from dwd_order_di 展开为所有字段
无元数据：select * 返回 partial + SELECT_STAR_METADATA_REQUIRED
未知字段：返回 UNKNOWN_COLUMN
歧义字段：返回 AMBIGUOUS_COLUMN
已确认字段仍正常生成血缘边
```

---

## 6. 禁止越界

不要为了“看起来成功”而：

```text
随便从第一张表取字段
把 unknown 字段删掉
把 ambiguous 当成 high confidence
```

---

## 7. 给 OpenCode 的单轮提示词

```text
请只实现 C07：基于 SQLite 元数据的 select * 展开，以及 unknown / ambiguous 诊断。
不确定信息必须保留为 diagnostics 和 unknown 节点，不允许静默丢弃。
前端应能展示 partial 图、unknown 节点和 warning。
实现后补齐 select *、UNKNOWN_COLUMN、AMBIGUOUS_COLUMN 的测试。
```
