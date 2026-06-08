select
    x.user_id,
    x.order_no
from (
    select
        o.user_id,
        o.order_no
    from dwd_order_di o
    where o.dt = '${dt}'
) x
left join dim_user u
    on x.user_id = u.user_id;
