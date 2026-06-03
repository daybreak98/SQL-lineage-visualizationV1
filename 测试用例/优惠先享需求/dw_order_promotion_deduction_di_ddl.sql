-- Upstream sources:
-- 1. default.mdw_order_v3_international
-- 2. ihotel_default.ods_mkt_peach_promotion_task_merge_da
-- Downstream target:
-- 1. ihotel_default.dw_order_promotion_deduction_di
-- Input grain:
-- 1. mdw_order_v3_international: one row per order_no snapshot in dt
-- 2. ods_mkt_peach_promotion_task_merge_da: one row per order_id task snapshot in dt
-- Output grain:
-- 1. one row per joined order_no in each dt partition
-- Primary key:
-- 1. dt + order_no
-- Risk controls:
-- 1. join explosion risk: source SQL uses left join on order_no = order_id, validate one-to-one before load
-- 2. duplicate-count risk: check target uniqueness on dt + order_no after load
-- 3. filter-scope drift: keep mt.dt = 'yyyymmdd' and t1.dt = 'yyyy-MM-dd' filters aligned to the same business day
-- Note:
-- 1. The source SQL has a duplicate alias "performance_type" on line 16.
-- 2. This DDL keeps the first performance_type field only; the duplicate alias is not materialized.
drop table ihotel_default.dw_order_promotion_deduction_di
create external table if not exists ihotel_default.dw_order_promotion_deduction_di (
    order_no string comment 'order number',
    order_date string comment 'order date',
    user_id string comment 'user id',
    repayment_amount string comment 'repayment amount',
    performance_type string comment 'performance type',
    performance_time string comment 'performance time',
    repayment_type string comment 'repayment type',
    status string comment 'status',
    pay_notify_no string comment 'payment notify number',
    pay_time string comment 'payment time',
    pay_source string comment 'payment brand source',
    pay_source1 string comment 'payment method',
    pay_amount string comment 'payment amount',
    promotion_deduction_status string comment 'promotion_deduction_status'
)
comment 'daily snapshot for order promotion deduction'
partitioned by (
    dt string comment 'partition date in yyyy-MM-dd'
)
stored as orc;


insert overwrite table ihotel_default.dw_order_promotion_deduction_di
    partition (dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}')


select
    get_json_object(data,'$.orderExtension.trackData.enjoyFirstPromotionTaskInfo') as promotion_deduction_status  --履约|回收

from default.ods_qta_order_detail_inc a
where dt = '20260422'
  and section = 'main-order'
limit 10