select
    o.order_no,
    custom_udf_with_bad_syntax(o.user_id, <#if enable_x> 'x' </#if>) as user_tag
from dwd_order_di o
left join dim_user u
    on o.user_id = u.user_id
where o.dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
  and ${dynamic_condition};
