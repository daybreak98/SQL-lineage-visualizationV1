-- Upstream sources:
-- 1. ihotel_default.ods_mkt_peach_promotion_task_merge_da
-- 2. default.mdw_order_v3_international
-- Downstream target:
-- 1. ihotel_default.dw_order_promotion_deduction_di
-- Input grain:
-- 1. task table: one row per order task event, keyed by order_id
-- 2. order table: one row per order_no after local dedup
-- Output grain:
-- 1. one row per order_no in each dt partition
-- Primary key:
-- 1. order_no
-- Risk controls:
-- 1. join explosion risk: dedup task by order_id and dedup order by order_no before join
-- 2. duplicate-count risk: row_number keeps one record instead of select distinct masking issues
-- 3. filter-scope drift: target partition is loaded from task dt scope only

create external table if not exists ihotel_default.dw_order_promotion_deduction_di (
    order_no string comment 'order number',
    order_date string comment 'order date',
    user_id string comment 'user id',
    performance_note_no string comment 'performance note number',
    repayment_no string comment 'repayment number',
    repayment_amount string comment 'repayment amount',
    performance_type string comment '0=completed on time, 1=deduction required',
    performance_time string comment 'performance success time',
    repayment_type string comment 'repayment type',
    over_due string comment 'overdue flag',
    bad_debt string comment 'bad debt flag',
    status string comment 'repayment status',
    pay_notify_no string comment 'payment notify number',
    pay_time string comment 'deduction success time',
    pay_source string comment 'payment brand',
    pay_source1 string comment 'payment method',
    pay_amount string comment 'payment amount'
)
comment 'order promotion deduction daily snapshot'
partitioned by (
    dt string comment 'partition date in yyyy-MM-dd'
)
stored as orc;


insert overwrite table ihotel_default.dw_order_promotion_deduction_di
partition (dt='${zdt.addDay(-1).format("yyyy-MM-dd")}')
with task_base as (
    select
        cast(t.order_id as string) as order_no,
        cast(t.performance_note_no as string) as performance_note_no,
        cast(t.order_id as string) as repayment_no,
        cast(t.gmt_success as string) as performance_time,
        row_number() over (
            partition by cast(t.order_id as string)
            order by
                case when t.gmt_success is not null then 0 else 1 end,
                t.gmt_success desc,
                cast(t.performance_note_no as string) desc
        ) as rn
    from ihotel_default.ods_mkt_peach_promotion_task_merge_da t
    where t.dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
      and t.order_id is not null
),
task_dedup as (
    select
        order_no,
        performance_note_no,
        repayment_no,
        performance_time
    from task_base
    where rn = 1
),
order_base as (
    select
        order_no,
        order_date,
        user_id,
        repayment_type,
        status,
        pay_notify_no,
        pay_time,
        pay_source,
        pay_source1,
        pay_amount
    from (
        select
            cast(o.order_no as string) as order_no,
            cast(o.order_date as string) as order_date,
            cast(o.user_id as string) as user_id,
            cast(
                coalesce(
                    o.ext_flag_map['active_promotion_flag'],
                    o.ext_flag_map['activePromotionFlag']
                ) as string
            ) as repayment_type,
            cast(
                coalesce(
                    o.ext_flag_map['promotion_from_user_flag'],
                    o.ext_flag_map['promotionFromUserFlag']
                ) as string
            ) as status,
            cast(
                coalesce(
                    o.ext_flag_map['promotion_single_trade_no'],
                    o.ext_flag_map['promotionSingleTradeNo']
                ) as string
            ) as pay_notify_no,
            cast(
                coalesce(
                    o.ext_flag_map['promotion_deduction_success_time'],
                    o.ext_flag_map['promotionDeductionSuccessTime']
                ) as string
            ) as pay_time,
            cast(
                coalesce(
                    o.ext_flag_map['promotion_deduction_pay_brand_name'],
                    o.ext_flag_map['promotionDeductionPayBrandName']
                ) as string
            ) as pay_source,
            cast(
                coalesce(
                    o.ext_flag_map['promotion_deduction_pay_method_name'],
                    o.ext_flag_map['promotionDeductionPayMethodName']
                ) as string
            ) as pay_source1,
            cast(
                coalesce(
                    o.ext_flag_map['promotion_deduction_amount'],
                    o.ext_flag_map['promotionDeductionAmount']
                ) as string
            ) as pay_amount,
            row_number() over (
                partition by cast(o.order_no as string)
                order by cast(o.order_date as string) desc
            ) as rn
        from default.mdw_order_v3_international o
        join (
            select distinct
                order_no
            from task_dedup
        ) k
            on cast(o.order_no as string) = k.order_no
    ) s
    where rn = 1
)
select
    t.order_no as order_no,
    o.order_date as order_date,
    o.user_id as user_id,
    t.performance_note_no as performance_note_no,
    t.repayment_no as repayment_no,
    cast(null as string) as repayment_amount,
    case
        when t.performance_time is not null then '0'
        else '1'
    end as performance_type,
    t.performance_time as performance_time,
    o.repayment_type as repayment_type,
    cast(null as string) as over_due,
    cast(null as string) as bad_debt,
    o.status as status,
    o.pay_notify_no as pay_notify_no,
    o.pay_time as pay_time,
    o.pay_source as pay_source,
    o.pay_source1 as pay_source1,
    o.pay_amount as pay_amount
from task_dedup t
left join order_base o
    on t.order_no = o.order_no;
