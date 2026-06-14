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
