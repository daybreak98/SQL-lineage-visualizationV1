select user_id
from dim_user_df u
join dwd_order_di o
  on u.user_id = o.user_id;
