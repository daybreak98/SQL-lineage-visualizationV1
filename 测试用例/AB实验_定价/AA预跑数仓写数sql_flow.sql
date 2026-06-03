-- AA预跑数仓写数: flow 明细
-- 假设目标表 ihotel_default.dw_ihotel_aa_index_order_di 的非分区列顺序如下:
-- mdd, user_type, user_id, init_gmv, order_no, room_night, batch_series, highlowstar,
-- coupon_id, is_user_coupon, init_commission_after, pricing_subsidy_amount,
-- coupon_subsidy_amount, voucher_pack_income, point_subsidy_amount,
-- multi_point_subsidy_amount, follow_price_subsidy_amount, bp_adv_amount_realized,
-- is_big_order_user, flow_mdd, flow_user_type, flow_user_id, flow_user_name,
-- flow_is_big_order_user, flow_search_pv, flow_detail_pv, flow_booking_pv,
-- flow_order_pv, country_name, city_name

with order_90 as (
    select
        order_date,
        user_id,
        count(order_no) as order_nos_90,
        sum(room_night) as room_nights_90
    from default.mdw_order_v3_international
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
      and (province_name in ('台湾', '澳门', '香港') or country_name != '中国')
      and terminal_channel_type = 'app'
      and is_valid = '1'
      and order_status not in ('CANCELLED', 'REJECTED')
      and order_date >= '${zdt.addDay(-90).format("yyyy-MM-dd")}'
      and order_date <= '${zdt.addDay(-1).format("yyyy-MM-dd")}'
    group by 1, 2
),
no_user as (
    select distinct
        user_id as no_user_id
    from order_90
    where room_nights_90 >= 15
),
user_first_order as (
    select
        user_id,
        min(order_date) as min_order_date
    from default.mdw_order_v3_international
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
      and (province_name in ('台湾', '澳门', '香港') or country_name != '中国')
      and terminal_channel_type in ('www', 'app', 'touch')
      and order_status not in ('CANCELLED', 'REJECTED')
      and is_valid = '1'
    group by 1
)

insert overwrite table ihotel_default.dw_ihotel_aa_index_order_di
partition (
    dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}',
    type = 'flow'
)
select
    null as mdd,
    null as user_type,
    null as user_id,
    null as init_gmv,
    null as order_no,
    null as room_night,
    null as batch_series,
    case
        when cast(a.hotel_grade as int) >= 4 then 'high_star'
        when cast(a.hotel_grade as int) = 3 then 'middle_star'
        else 'low_star'
    end as highlowstar,
    null as coupon_id,
    null as is_user_coupon,
    null as init_commission_after,
    null as pricing_subsidy_amount,
    null as coupon_subsidy_amount,
    null as voucher_pack_income,
    null as point_subsidy_amount,
    null as multi_point_subsidy_amount,
    null as follow_price_subsidy_amount,
    null as bp_adv_amount_realized,
    null as is_big_order_user,
    case
        when a.province_name in ('澳门', '香港') then a.province_name
        when a.country_name in ('泰国', '日本', '韩国', '新加坡', '马来西亚', '美国', '印度尼西亚', '俄罗斯')
            then a.country_name
        when e.area in ('欧洲', '亚太', '美洲') then e.area
        else '其他'
    end as flow_mdd,
    case
        when b.min_order_date is not null
            and a.dt > substr(cast(b.min_order_date as string), 1, 10) then '老客'
        else '新客'
    end as flow_user_type,
    a.user_id as flow_user_id,
    a.user_name as flow_user_name,
    if(no_user.no_user_id is null, '正常用户', '大单用户') as flow_is_big_order_user,
    coalesce(a.search_pv, 0) as flow_search_pv,
    coalesce(a.detail_pv, 0) as flow_detail_pv,
    coalesce(a.booking_pv, 0) as flow_booking_pv,
    coalesce(a.order_pv, 0) as flow_order_pv,
    a.country_name,
    a.city_name
from ihotel_default.mdw_user_app_log_sdbo_di_v1 a
left join temp.temp_yiquny_zhang_ihotel_area_region_forever e
    on a.country_name = e.country_name
left join user_first_order b
    on a.user_id = b.user_id
left join no_user
    on a.user_id = no_user.no_user_id
where a.dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
  and a.business_type = 'hotel'
  and (a.province_name in ('台湾', '澳门', '香港') or a.country_name != '中国')
  and (
      coalesce(a.search_pv, 0)
      + coalesce(a.detail_pv, 0)
      + coalesce(a.booking_pv, 0)
      + coalesce(a.order_pv, 0)
  ) > 0
  and a.user_id is not null
  and a.user_id not in ('null', 'NULL', '', ' ');
