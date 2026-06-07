select
  u.country_name,
  o.order_no
from dim_user_df u
join dwd_order_di o
  on u.user_id = o.user_id;
