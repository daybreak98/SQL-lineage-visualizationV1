# 回归测试清单

## Case 1：简单列 CTE 不回归

```sql
with order_base as (
  select o.user_id, o.order_no
  from dwd_order_di o
)
select user_id, order_no from order_base;
```

期望：

```text
order_base.user_id  depends_on dwd_order_di.user_id
order_base.order_no depends_on dwd_order_di.order_no
```

## Case 2：count distinct 表达式

```sql
with search_result as (
  select count(distinct a.search_request_uid) as search_times
  from search_base a
)
select search_times from search_result;
```

期望：

```text
search_result.search_times depends_on search_base.search_request_uid
transform_type = aggregate
origin = expression_analyzer
```

## Case 3：算术表达式

```sql
with order_metric as (
  select price * quantity as gmv
  from order_base
)
select gmv from order_metric;
```

期望：

```text
order_metric.gmv depends_on order_base.price
order_metric.gmv depends_on order_base.quantity
transform_type = expression
```

## Case 4：case when 表达式

```sql
with order_metric as (
  select case when order_status = 'DONE' then amount else 0 end as valid_amount
  from order_base
)
select valid_amount from order_metric;
```

期望：

```text
order_metric.valid_amount depends_on order_base.order_status
order_metric.valid_amount depends_on order_base.amount
transform_type = case_when
```

## Case 5：限定字段消歧

```sql
with metric as (
  select count(distinct o.user_id) as order_user_cnt
  from order_base o
  join user_base u on o.user_id = u.user_id
)
select order_user_cnt from metric;
```

期望：

```text
metric.order_user_cnt depends_on order_base.user_id
```

## Case 6：裸字段多表歧义

```sql
with metric as (
  select count(distinct user_id) as user_cnt
  from order_base o
  join user_base u on o.user_id = u.user_id
)
select user_cnt from metric;
```

如果 `order_base` 和 `user_base` 都有 `user_id`，期望：

```text
AMBIGUOUS_COLUMN
不要猜测 order_base.user_id 或 user_base.user_id
```

## Case 7：count(*)

```sql
with metric as (
  select count(*) as order_cnt
  from order_base
)
select order_cnt from metric;
```

期望：

```text
metric.order_cnt transform_type = aggregate
metric.order_cnt dependency_type = relation_rowset
不生成 unknown.*
```

## Case 8：常量字段

```sql
with flags as (
  select 1 as is_valid
  from order_base
)
select is_valid from flags;
```

期望：

```text
flags.is_valid transform_type = constant
input_columns = []
```

## Case 9：多层 CTE 穿透

```sql
with order_base as (
  select order_no, amount
  from dwd_order_di
),
order_metric as (
  select sum(amount) as total_amount
  from order_base
)
select total_amount from order_metric;
```

期望：

```text
order_metric.total_amount depends_on order_base.amount
rollup 后可继续穿透到 dwd_order_di.amount
```
