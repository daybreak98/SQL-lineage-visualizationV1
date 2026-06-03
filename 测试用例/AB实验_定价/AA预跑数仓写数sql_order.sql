-- AA预跑数仓写数: order 明细
-- 与 flow SQL 共用同一张 AA 事实表，列顺序必须完全一致。

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
    type = 'order'
)
select
    case
        when a.province_name in ('澳门', '香港') then a.province_name
        when a.country_name in ('泰国', '日本', '韩国', '新加坡', '马来西亚', '美国', '印度尼西亚', '俄罗斯')
            then a.country_name
        when e.area in ('欧洲', '亚太', '美洲') then e.area
        else '其他'
    end as mdd,
    case
        when b.min_order_date is not null and a.order_date > b.min_order_date then '老客'
        else '新客'
    end as user_type,
    a.user_id as user_id,
    a.init_gmv as init_gmv,
    a.order_no as order_no,
    a.room_night as room_night,
    a.batch_series as batch_series,
    case
        when cast(a.hotel_grade as int) >= 4 then 'high_star'
        when cast(a.hotel_grade as int) = 3 then 'middle_star'
        else 'low_star'
    end as highlowstar,
    a.coupon_id as coupon_id,
    case
        when a.coupon_id is not null
            and a.batch_series not in ('MacaoDisco_ZK_5e27de', '2night_ZK_952825', '3night_ZK_ad8c83')
            and a.batch_series not like '%23base_ZK_728810%'
            and a.batch_series not like '%23extra_ZK_ce6f99%'
            then 'Y'
        else 'N'
    end as is_user_coupon,
    cast(
        case
            when a.batch_series like '%23base_ZK_728810%' or a.batch_series like '%23extra_ZK_ce6f99%'
                then a.init_commission_after
                    + cast(coalesce(split(a.coupon_info['23base_ZK_728810'], '_')[1], '0') as decimal(20, 2))
                    + cast(coalesce(split(a.coupon_info['23extra_ZK_ce6f99'], '_')[1], '0') as decimal(20, 2))
                    + coalesce(a.ext_plat_certificate, 0)
            else a.init_commission_after + coalesce(a.ext_plat_certificate, 0)
        end as decimal(20, 2)
    ) as init_commission_after,
    cast(coalesce(get_json_object(a.extendinfomap, '$.V2_BEAT_AMOUNT_AF'), '0') as decimal(20, 2)) * a.room_night as pricing_subsidy_amount,
    case
        when a.coupon_substract_summary is null
            or a.batch_series like '%23base_ZK_728810%'
            or a.batch_series like '%23extra_ZK_ce6f99%'
            then 0
        else coalesce(a.coupon_substract_summary, 0)
    end as coupon_subsidy_amount,
    coalesce(a.cashbackmap['voucher_pack_price'], 0) as voucher_pack_income,
    cast(coalesce(get_json_object(a.promotion_score_info, '$.deductionPointsInfoV2.exchangeAmount'), '0') as decimal(20, 2)) as point_subsidy_amount,
    case
        when array_contains(a.supplier_promotion_code, '2913') and a.qta_supplier_id = '1615667'
            then cast(coalesce(get_json_object(a.promotion_score_info, '$.deductionPointsInfoV2.exchangeAmount'), '0') as decimal(20, 2))
        else 0
    end as multi_point_subsidy_amount,
    case
        when a.supplier_code in (
            'hca9008oc4l', 'hca908oh60s', 'hca908oh60t', 'hca9008pb7m', 'hca9008pb7k', 'hca908pb70p',
            'hca908pb70o', 'hca908pb70q', 'hca908pb70s', 'hca908pb70r', 'hca908lp9aj', 'hca908lp9ag',
            'hca908lp9ai', 'hca908lp9ah', 'hca9008lp9v', 'hca908lp9ak', 'hca908lp9al', 'hca908lp9am',
            'hca908lp9an', 'hca1f71a00i', 'hca1f71a00j'
        ) then coalesce(a.follow_price_amount, 0)
        else 0
    end as follow_price_subsidy_amount,
    cast(coalesce(get_json_object(a.extendinfomap, '$.bp_adv_amount_realized'), '0') as decimal(20, 2)) * a.room_night as bp_adv_amount_realized,
    if(no_user.no_user_id is null, '正常用户', '大单用户') as is_big_order_user,
    null as flow_mdd,
    null as flow_user_type,
    null as flow_user_id,
    null as flow_user_name,
    null as flow_is_big_order_user,
    null as flow_search_pv,
    null as flow_detail_pv,
    null as flow_booking_pv,
    null as flow_order_pv,
    a.country_name,
    a.city_name
from default.mdw_order_v3_international a
left join user_first_order b
    on a.user_id = b.user_id
left join temp.temp_yiquny_zhang_ihotel_area_region_forever e
    on a.country_name = e.country_name
left join no_user
    on a.user_id = no_user.no_user_id
where a.dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
  and (a.province_name in ('台湾', '澳门', '香港') or a.country_name != '中国')
  and a.terminal_channel_type = 'app'
  and (a.first_cancelled_time is null or date(a.first_cancelled_time) > a.order_date)
  and (a.first_rejected_time is null or date(a.first_rejected_time) > a.order_date)
  and (a.refund_time is null or date(a.refund_time) > a.order_date)
  and a.is_valid = '1'
  and a.order_date = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
  and a.order_no <> '103576132435';
