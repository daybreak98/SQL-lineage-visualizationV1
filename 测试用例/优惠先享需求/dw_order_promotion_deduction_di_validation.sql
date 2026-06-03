-- Validation SQL for ihotel_default.dw_order_promotion_deduction_di

-- 1. Compare target row count with deduplicated task count.
with task_base as (
    select
        cast(order_id as string) as order_no,
        row_number() over (
            partition by cast(order_id as string)
            order by
                case when gmt_success is not null then 0 else 1 end,
                gmt_success desc,
                cast(performance_note_no as string) desc
        ) as rn
    from ihotel_default.ods_mkt_peach_promotion_task_merge_da
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
      and order_id is not null
)
select
    'target_vs_task' as check_name,
    (select count(1)
     from ihotel_default.dw_order_promotion_deduction_di
     where dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}') as target_cnt,
    (select count(1)
     from task_base
     where rn = 1) as task_cnt;


-- 2. Primary key uniqueness check at target grain.
select
    order_no,
    count(1) as row_cnt
from ihotel_default.dw_order_promotion_deduction_di
where dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
group by order_no
having count(1) > 1;


-- 3. Order join miss check.
select
    count(1) as total_rows,
    sum(case when order_date is null then 1 else 0 end) as null_order_date_rows,
    sum(case when user_id is null then 1 else 0 end) as null_user_id_rows
from ihotel_default.dw_order_promotion_deduction_di
where dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}';


-- 4. performance_type logic check.
select
    performance_type,
    case
        when performance_time is not null then 'has_performance_time'
        else 'no_performance_time'
    end as performance_time_flag,
    count(1) as row_cnt
from ihotel_default.dw_order_promotion_deduction_di
where dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
group by
    performance_type,
    case
        when performance_time is not null then 'has_performance_time'
        else 'no_performance_time'
    end;


-- 5. Payment field completeness check.
select
    sum(case when pay_notify_no is not null then 1 else 0 end) as pay_notify_no_cnt,
    sum(case when pay_time is not null then 1 else 0 end) as pay_time_cnt,
    sum(case when pay_source is not null then 1 else 0 end) as pay_source_cnt,
    sum(case when pay_source1 is not null then 1 else 0 end) as pay_source1_cnt,
    sum(case when pay_amount is not null then 1 else 0 end) as pay_amount_cnt
from ihotel_default.dw_order_promotion_deduction_di
where dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}';


-- 6. Placeholder fields expected to be null before source confirmation.
select
    sum(case when repayment_amount is not null then 1 else 0 end) as repayment_amount_nonnull_cnt,
    sum(case when over_due is not null then 1 else 0 end) as over_due_nonnull_cnt,
    sum(case when bad_debt is not null then 1 else 0 end) as bad_debt_nonnull_cnt
from ihotel_default.dw_order_promotion_deduction_di
where dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}';
