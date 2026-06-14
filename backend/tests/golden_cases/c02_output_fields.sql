select
  country_name,
  count(order_no) as order_cnt
from dwd_order_di
group by country_name;
