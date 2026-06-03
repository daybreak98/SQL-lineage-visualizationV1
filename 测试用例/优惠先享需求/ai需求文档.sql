
select
    order_no,
    order_date,
    mt.user_id,
    null as repayment_amount,
    if(gmt_success is not null,1,0) as performance_type,
    gmt_success as performance_time,
    ext_flag_map['active_promotion_flag'] repayment_type,
    ext_flag_map['promotion_from_user_flag'] status,
    ext_flag_map['promotion_single_trade_no'] pay_notify_no,
    ext_flag_map['promotion_deduction_success_time'] pay_time,
    ext_flag_map['promotion_deduction_pay_brand_name'] pay_source,
    ext_flag_map['promotion_deduction_pay_method_name'] pay_source1,
    ext_flag_map['promotion_deduction_amount'] pay_amount,
    ext_flag_map['promotion_deduction_success_time'] performance_type
from default.mdw_order_v3_international mt
         left join ihotel_default.ods_mkt_peach_promotion_task_merge_da t1
                   on mt.order_no = t1.order_id and t1.dt = '2026-04-21'
where mt.dt = '20260421'



