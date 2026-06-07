select
  sum(order_amount) as gmv,
  count(distinct order_no) as order_cnt,
  sum(order_amount) / count(distinct order_no) as adr
from dwd_order_di;
