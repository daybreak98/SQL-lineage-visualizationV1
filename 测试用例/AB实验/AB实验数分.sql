-- intl_hotel_orders(order_id, user_id, hotel_id, agent_id, order_amount, currency, order_time, status)
with mt as (
    select agent_id,
           date_format(order_time, 'yyyyMM') dd,
           sum(order_amount*case
                   when currency = '美元' then 5
                   when currency = '欧元' then 7
                   else 1
                   end) gmv
    from intl_hotel_orders
    group by 1, 2
)
   , t1
       as (
    select agent_id,
           dd,

           gmv,
           if(dd = min(dd) over (partition by agent_id order by dd), gmv, 0)
               GMV_min,
           if(dd = max(dd) over (partition by agent_id order by dd desc), gmv, 0) GMV_max
    from mt
)
   , t2 as (
    select agent_id,
           gmv,
           sum(GMV_max) / sum(GMV_min) gmv_rate
    from t1
    group by 1, 2
)
   , t3 as (
    select agent_id,
           gmv,
           row_number() over (partition by agent_id order by gmv_rate desc) rnk
    from t2
)
select agent_id,
       gmv
from t3
where rnk <= 3