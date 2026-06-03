-- 定价实验 AA 预跑 SQL
-- 使用方式:
-- 1. 替换 testcode / 起止日期
-- 2. 按需要打开 flow_base / order_base 里的筛选条件
-- 3. 先确认 AA 底表已写入完成:
--    ihotel_default.dw_ihotel_aa_index_order_di

with ab_user as (
    select
        dt,
        ab_group,
        clientcode as exp_user_id
    from f_abt.ab_division_hive_result
    where testcode = '请替换为AA实验testcode'
      and dt between '2026-05-01' and '2026-05-01'
    group by 1, 2, 3
),
flow_base as (
    select
        dt,
        flow_user_id,
        flow_user_type,
        flow_is_big_order_user,
        highlowstar,
        country_name,
        city_name,
        coalesce(flow_search_pv, 0) as flow_search_pv,
        coalesce(flow_detail_pv, 0) as flow_detail_pv,
        coalesce(flow_booking_pv, 0) as flow_booking_pv,
        coalesce(flow_order_pv, 0) as flow_order_pv
    from ihotel_default.dw_ihotel_aa_index_order_di
    where dt between '2026-05-01' and '2026-05-01'
      and type = 'flow'
      -- and flow_user_type = '新客'
      -- and flow_is_big_order_user = '正常用户'
      -- and highlowstar = 'low_star'
      -- and country_name = '韩国'
      -- and city_name = '首尔'
),
order_base as (
    select
        dt,
        user_id,
        user_type,
        is_big_order_user,
        highlowstar,
        country_name,
        city_name,
        coalesce(init_gmv, 0) as init_gmv,
        coalesce(room_night, 0) as room_night,
        order_no,
        is_user_coupon,
        coalesce(init_commission_after, 0) as init_commission_after,
        coalesce(pricing_subsidy_amount, 0) as pricing_subsidy_amount,
        coalesce(coupon_subsidy_amount, 0) as coupon_subsidy_amount,
        coalesce(voucher_pack_income, 0) as voucher_pack_income,
        coalesce(point_subsidy_amount, 0) as point_subsidy_amount,
        coalesce(multi_point_subsidy_amount, 0) as multi_point_subsidy_amount,
        coalesce(follow_price_subsidy_amount, 0) as follow_price_subsidy_amount,
        coalesce(bp_adv_amount_realized, 0) as bp_adv_amount_realized
    from ihotel_default.dw_ihotel_aa_index_order_di
    where dt between '2026-05-01' and '2026-05-01'
      and type = 'order'
      -- and user_type = '新客'
      -- and is_big_order_user = '正常用户'
      -- and highlowstar = 'low_star'
      -- and country_name = '韩国'
      -- and city_name = '首尔'
),
flow_result as (
    select
        ab.dt as ab_dt,
        ab.ab_group,
        count(distinct f.flow_user_id) as flow_uv,
        sum(f.flow_search_pv) as search_pv,
        sum(f.flow_detail_pv) as detail_pv,
        sum(f.flow_booking_pv) as booking_pv,
        sum(f.flow_order_pv) as flow_order_pv
    from ab_user ab
    left join flow_base f
        on ab.exp_user_id = f.flow_user_id
       and ab.dt = f.dt
    where f.flow_user_id is not null
    group by 1, 2
),
order_result as (
    select
        ab.dt as ab_dt,
        ab.ab_group,
        count(distinct o.user_id) as order_uv,
        count(distinct o.order_no) as order_num,
        count(distinct case when o.is_user_coupon = 'Y' then o.order_no end) as coupon_order_num,
        sum(o.init_gmv) as total_gmv,
        sum(o.room_night) as total_room_night,
        sum(o.init_commission_after) as total_commission,
        sum(o.pricing_subsidy_amount) as total_pricing_subsidy,
        sum(o.coupon_subsidy_amount) as total_coupon_subsidy,
        sum(o.voucher_pack_income) as total_voucher_pack_income,
        sum(o.point_subsidy_amount) as total_point_subsidy,
        sum(o.multi_point_subsidy_amount) as total_multi_point_subsidy,
        sum(o.follow_price_subsidy_amount) as total_follow_price_subsidy,
        sum(o.bp_adv_amount_realized) as total_bp_adv_amount_realized
    from ab_user ab
    left join order_base o
        on ab.exp_user_id = o.user_id
       and ab.dt = o.dt
    where o.user_id is not null
    group by 1, 2
)
select
    coalesce(f.ab_dt, o.ab_dt) as ab_dt,
    coalesce(f.ab_group, o.ab_group) as ab_group,
    f.flow_uv,
    f.search_pv,
    f.detail_pv,
    f.booking_pv,
    f.flow_order_pv,
    o.order_uv,
    o.order_num,
    o.coupon_order_num,
    o.total_gmv,
    o.total_room_night,
    cast(case when o.total_room_night = 0 then null else o.total_gmv / o.total_room_night end as decimal(20, 2)) as order_adr,
    o.total_commission,
    o.total_pricing_subsidy,
    o.total_coupon_subsidy,
    o.total_voucher_pack_income,
    o.total_point_subsidy,
    o.total_multi_point_subsidy,
    o.total_follow_price_subsidy,
    o.total_bp_adv_amount_realized,
    cast(
        case
            when f.flow_uv = 0 then null
            else o.total_commission / f.flow_uv
        end as decimal(20, 2)
    ) as revenue_per_uv,
    cast(
        case
            when o.order_num = 0 then null
            else o.total_pricing_subsidy / o.order_num
        end as decimal(20, 2)
    ) as pricing_subsidy_per_order,
    cast(
        case
            when o.order_num = 0 then null
            else o.total_coupon_subsidy / o.order_num
        end as decimal(20, 2)
    ) as coupon_subsidy_per_order,
    cast(
        case
            when f.flow_uv = 0 then null
            else (
                o.total_commission
                + o.total_voucher_pack_income
                - o.total_pricing_subsidy
                - o.total_coupon_subsidy
                - o.total_point_subsidy
                - o.total_multi_point_subsidy
                - o.total_follow_price_subsidy
                - o.total_bp_adv_amount_realized
            ) / f.flow_uv
        end as decimal(20, 2)
    ) as net_income_per_uv,
    concat(
        round(
            case when f.search_pv = 0 then null else f.detail_pv / f.search_pv * 100 end,
            2
        ),
        '%'
    ) as search_to_detail_rate,
    concat(
        round(
            case when f.search_pv = 0 then null else f.booking_pv / f.search_pv * 100 end,
            2
        ),
        '%'
    ) as search_to_booking_rate,
    concat(
        round(
            case when f.search_pv = 0 then null else f.flow_order_pv / f.search_pv * 100 end,
            2
        ),
        '%'
    ) as search_to_order_rate,
    concat(
        round(
            case when o.total_gmv = 0 then null else o.total_pricing_subsidy / o.total_gmv * 100 end,
            2
        ),
        '%'
    ) as pricing_subsidy_rate,
    concat(
        round(
            case when o.total_gmv = 0 then null else o.total_coupon_subsidy / o.total_gmv * 100 end,
            2
        ),
        '%'
    ) as coupon_subsidy_rate,
    concat(
        round(
            case when o.order_num = 0 then null else o.coupon_order_num / o.order_num * 100 end,
            2
        ),
        '%'
    ) as coupon_order_share
from flow_result f
full outer join order_result o
    on f.ab_dt = o.ab_dt
   and f.ab_group = o.ab_group
order by 1 desc, 2;
