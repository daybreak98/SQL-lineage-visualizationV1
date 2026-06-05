export const exampleSql = `with order_base as (
  select
    o.user_id,
    o.order_no,
    o.order_amount,
    case when o.is_valid = 1 then o.order_no end as valid_order_no,
    o.dt,
    u.country_name
  from dwd_order_di o
  left join dim_user_df u
    on o.user_id = u.user_id
  where o.dt = '2026-05-27'
    and o.terminal_channel = 'app'
),
valid_order_subq as (
  select
    country_name,
    valid_order_no,
    user_id,
    order_amount
  from order_base
  where valid_order_no is not null
),
metric_base as (
  select
    country_name,
    count(distinct valid_order_no) as order_cnt,
    count(distinct user_id) as user_cnt,
    sum(order_amount) as gmv
  from valid_order_subq
  group by country_name
)
select
  country_name,
  order_cnt,
  user_cnt,
  gmv,
  gmv / nullif(order_cnt, 0) as avg_order_amount
from metric_base;`;
