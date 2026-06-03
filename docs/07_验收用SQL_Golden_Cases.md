# 07｜验收用 SQL Golden Cases

---

## C02｜输出字段识别

```sql
select
  country_name,
  count(order_no) as order_cnt
from dwd_order_di
group by country_name;
```

期望：

```text
output_fields 包含 country_name、order_cnt
```

---

## C03｜单表字段血缘

```sql
select
  order_no,
  user_id as uid
from dwd_order_di;
```

期望：

```text
dwd_order_di.order_no → output.order_no
dwd_order_di.user_id  → output.uid
```

---

## C04｜Join 别名

```sql
select
  u.country_name,
  o.order_no
from dim_user_df u
join dwd_order_di o
  on u.user_id = o.user_id;
```

期望：

```text
dim_user_df.country_name → output.country_name
dwd_order_di.order_no    → output.order_no
```

---

## C05｜CTE 结构依赖

```sql
with order_base as (
  select
    user_id,
    order_no,
    order_amount
  from dwd_order_di
),
metric_base as (
  select
    user_id,
    count(order_no) as order_cnt,
    sum(order_amount) as gmv
  from order_base
  group by user_id
)
select
  user_id,
  order_cnt,
  gmv
from metric_base;
```

期望：

```text
dwd_order_di → order_base → metric_base → Query Result
view_mode = subquery_dependency
```

---

## C06｜元数据 JSON

```json
{
  "metadata_version": "golden-001",
  "tables": [
    {
      "catalog": "default",
      "schema": "default",
      "table_name": "dwd_order_di",
      "comment": "订单明细表",
      "columns": [
        { "name": "order_no", "data_type": "string", "comment": "订单号" },
        { "name": "user_id", "data_type": "string", "comment": "用户ID" },
        { "name": "order_amount", "data_type": "double", "comment": "订单金额" }
      ]
    },
    {
      "catalog": "default",
      "schema": "default",
      "table_name": "dim_user_df",
      "comment": "用户维表",
      "columns": [
        { "name": "user_id", "data_type": "string", "comment": "用户ID" },
        { "name": "country_name", "data_type": "string", "comment": "国家名称" }
      ]
    }
  ]
}
```

---

## C07｜select * 展开

```sql
select * from dwd_order_di;
```

期望：

```text
有 metadata 时展开 order_no、user_id、order_amount
无 metadata 时返回 partial + SELECT_STAR_METADATA_REQUIRED
```

---

## C08｜SourceLocation

```sql
select
  order_no,
  user_id as uid,
  sum(order_amount) as gmv
from dwd_order_di
group by order_no, user_id;
```

期望：

```text
output_column:order_no 有 source_location
output_column:uid 有 source_location
output_column:gmv 有 source_location
```

---

## C09｜表达式依赖

```sql
select
  sum(order_amount) as gmv,
  count(distinct order_no) as order_cnt,
  sum(order_amount) / count(distinct order_no) as adr
from dwd_order_di;
```

期望：

```text
gmv depends_on dwd_order_di.order_amount
order_cnt depends_on dwd_order_di.order_no
adr depends_on dwd_order_di.order_amount and dwd_order_di.order_no
```
