# C04｜Join 别名字段归属与诊断

## 1. 本轮目标

支持常见 Join SQL 中的表别名和字段归属。

```sql
select u.country_name, o.order_no
from dim_user_df u
join dwd_order_di o on u.user_id = o.user_id
```

生成：

```text
dim_user_df.country_name → output.country_name
dwd_order_di.order_no   → output.order_no
```

---

## 2. 后端能力

本轮新增：

```text
表别名映射：u -> dim_user_df, o -> dwd_order_di
限定字段解析：u.country_name
未限定字段解析：country_name
unknown 字段诊断
ambiguous 字段诊断的雏形
```

---

## 3. 允许创建

```text
backend/app/services/name_resolver.py
backend/app/domain/diagnostics_model.py
backend/tests/test_name_resolver.py
backend/tests/integration/test_analyze_api_c04.py
```

---

## 4. 字段归属规则

| 场景 | 处理方式 |
|---|---|
| `u.country_name` | 通过 alias 找到 `dim_user_df.country_name` |
| `country_name` 且只有一个表可能拥有 | 暂时归属该表；无元数据时可 unknown |
| `country_name` 且多表可能拥有 | 返回 `AMBIGUOUS_COLUMN` |
| `x.country_name` 但 x 不是表别名 | 返回 `UNKNOWN_TABLE_ALIAS` |

C04 如果还没有 SQLite 元数据，对未限定字段可以保守处理，不要瞎猜。

---

## 5. 前端对接文档

前端效果：

```text
1. 多表字段节点能在画布上区分表来源
2. unknown / ambiguous 诊断显示在诊断区域
3. unknown 节点可以展示，但要有特殊状态
```

节点建议：

```text
physical_column:dim_user_df.country_name
physical_column:dwd_order_di.order_no
unknown_column:country_name
```

---

## 6. 测试验收

必须通过：

```text
select u.country_name from dim_user_df u → dim_user_df.country_name
select o.order_no from dwd_order_di o → dwd_order_di.order_no
select x.a from t → UNKNOWN_TABLE_ALIAS
select a from t1 join t2 → 没有元数据时 partial，不伪装准确
```

---

## 7. 禁止越界

不要做：

```text
SQLite 元数据导入
select * 展开
完整表达式解析
复杂 CTE 字段穿透
```

---

## 8. 给 OpenCode 的单轮提示词

```text
请只实现 C04：Join 场景下的表别名字段归属与基础诊断。
重点实现 alias -> table 的映射，支持 u.col / o.col。
无法确认的未限定字段必须进入 diagnostics，不允许猜成成功血缘。
前端应能看到多表字段节点和 unknown / ambiguous 诊断。
不要实现 SQLite 元数据和 CTE。
```
