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
      and order_date >= date_sub('${zdt.addDay(-1).format("yyyy-MM-dd")}', 90)
      and order_date <= date_sub('${zdt.addDay(-1).format("yyyy-MM-dd")}', 1)
    group by
        order_date,
        user_id
),
no_user as (
    select distinct
        user_id as no_user_id
    from order_90
    where room_nights_90 >= 15
),
ab_rule as (
    select
        rule.ab_exp_id,
        rule.ab_version,
        rule.ab_rule_version,
        ab.device_id as ab_exp_value
    from (
        select
            ab_exp_id,
            ab_version,
            ab_rule_version
        from default.ods_abtest_rule_info
        where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
          and source = 'hotel'
          and ab_shuntbase = 'APP_UID'
          and ab_exp_id = '251204_ho_gj_ai_compare_price'
    ) rule
    join (
        select
            expid,
            version,
            ruleversion,
            clientcode as device_id
        from default.ods_abtest_sdk_log_endtime_hotel
        where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
          and clientcode is not null
          and expid is not null
          and version is not null
          and ruleversion is not null
          and expid != ''
          and version != ''
          and clientcode not in (
              '0',
              '00000000',
              '00000000000000',
              '000000000000000',
              '0000000000000000',
              '0000000000000000000000000000000000000000',
              '',
              'ctrip',
              'elong',
              '352284040670808'
          )
          and clientcode not like 'tc%'
          and clientcode not like 'wx%'
          and clientcode not like 'pd%'
    ) ab
        on ab.expid = rule.ab_exp_id
       and ab.version = rule.ab_version
       and ab.ruleversion = rule.ab_rule_version
    group by
        rule.ab_exp_id,
        rule.ab_version,
        rule.ab_rule_version,
        ab.device_id
),
user_type as (
    select
        user_id,
        min(order_date) as min_order_date
    from default.mdw_order_v3_international
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
      and (province_name in ('台湾', '澳门', '香港') or country_name != '中国')
      and terminal_channel_type in ('www', 'app', 'touch')
      and order_status not in ('CANCELLED', 'REJECTED')
      and is_valid = '1'
    group by
        user_id
),
q_order_app as (
    select
        a.order_date,
        t.ab_exp_id,
        t.ab_exp_value,
        t.ab_version,
        t.ab_rule_version,
        a.country_name,
        a.city_name,
        case
            when a.order_date = b.min_order_date then '新客'
            else '老客'
        end as user_type,
        if(no_user.no_user_id is null, '正常用户', '大单用户') as is_big_order_user,
        a.user_id,
        a.user_info['orig_device_id'] as orig_device_id,
        a.init_gmv,
        a.order_no,
        a.room_night,
        a.batch_series,
        a.hotel_grade,
        a.coupon_id,
        a.init_commission_after,
        case
            when a.coupon_id is not null
             and a.batch_series not in ('MacaoDisco_ZK_5e27de', '2night_ZK_952825', '3night_ZK_ad8c83')
             and a.batch_series not like '%23base_ZK_728810%'
             and a.batch_series not like '%23extra_ZK_ce6f99%'
                then 'Y'
            else 'N'
        end as is_user_conpon,
        case
            when a.batch_series like '%23base_ZK_728810%'
              or a.batch_series like '%23extra_ZK_ce6f99%'
                then a.init_commission_after
                   + coalesce(split(a.coupon_info['23base_ZK_728810'], '_')[1], 0)
                   + coalesce(split(a.coupon_info['23extra_ZK_ce6f99'], '_')[1], 0)
                   + coalesce(a.ext_plat_certificate, 0)
            else a.init_commission_after + coalesce(a.ext_plat_certificate, 0)
        end as final_commission_after,
        case
            when a.batch_series like '%23base_ZK_728810%'
              or a.batch_series like '%23extra_ZK_ce6f99%'
                then a.init_commission_after_new
                   + coalesce(split(a.coupon_info['23base_ZK_728810'], '_')[1], 0)
                   + coalesce(split(a.coupon_info['23extra_ZK_ce6f99'], '_')[1], 0)
                   + coalesce(a.ext_plat_certificate, 0)
            else a.init_commission_after_new + coalesce(a.ext_plat_certificate, 0)
        end as qyj,
        case
            when coalesce(a.four_a, a.third_a) is not null and a.dt <= '20221124'
                then round(
                    coalesce(
                        ((coalesce(a.second_a, a.first_a) - coalesce(a.four_a, a.third_a)) * a.room_night),
                        (((a.bp + a.final_cost) * (1 + a.p_i_incr) - coalesce(a.four_a, a.third_a)) * a.room_night)
                    ),
                    2
                )
            when coalesce(a.four_a, a.third_a) is not null and a.order_date <= '2024-03-29'
                then coalesce(a.four_a_reduce, a.third_a_reduce) * a.room_night
            else coalesce(a.cashbackmap['follow_price_amount'] * a.room_night, 0)
        end as zbj,
        coalesce(get_json_object(a.extendinfomap, '$.frame_amount'), 0) * a.room_night as xyb,
        coalesce(a.cashbackmap['framework_amount'], 0) as qb,
        coalesce(get_json_object(a.promotion_score_info, '$.deductionPointsInfoV2.exchangeAmount'), 0) as jf_amt,
        case
            when a.coupon_substract_summary is null
              or a.batch_series like '%23base_ZK_728810%'
              or a.batch_series like '%23extra_ZK_ce6f99%'
                then 0
            else coalesce(a.coupon_substract_summary, 0)
        end as coupon_substract_summary
    from default.mdw_order_v3_international a
    left join user_type b
        on a.user_id = b.user_id
    left join no_user
        on a.user_id = no_user.no_user_id
    right join ab_rule t
        on t.ab_exp_value = a.user_info['orig_device_id']
    where a.dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
      and (a.province_name in ('台湾', '澳门', '香港') or a.country_name != '中国')
      and a.terminal_channel_type = 'app'
      and (a.first_cancelled_time is null or date(a.first_cancelled_time) > a.order_date)
      and (a.first_rejected_time is null or date(a.first_rejected_time) > a.order_date)
      and (a.refund_time is null or date(a.refund_time) > a.order_date)
      and a.is_valid = '1'
      and a.order_date = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
      and a.order_no <> '103576132435'
),
q_order_info_app as (
    select
        order_date,
        ab_exp_id,
        ab_exp_value,
        ab_version,
        ab_rule_version,
        country_name,
        city_name,
        user_type,
        is_big_order_user,
        sum(final_commission_after) as q_commission_app,
        sum(qyj) + sum(zbj) + sum(xyb) + sum(qb) as q_commission_c_view_app,
        sum(init_gmv) as q_gmv_app,
        sum(coupon_substract_summary) as q_coupon_amount_app,
        count(distinct order_no) as q_order_cnt_app,
        count(distinct user_id) as q_order_user_cnt_app,
        sum(room_night) as q_room_night_app,
        count(distinct case when is_user_conpon = 'Y' then order_no end) as q_coupon_order_cnt_app
    from q_order_app
    group by
        order_date,
        ab_exp_id,
        ab_exp_value,
        ab_version,
        ab_rule_version,
        country_name,
        city_name,
        user_type,
        is_big_order_user
)
insert overwrite table ihotel_default.dw_ihotel_abtest_detail_flow_di
partition (
    dt = '${zdt.addDay(-1).format("yyyyMMdd")}',
type = 'flow',
user_id_type = 'uid'
)
select
    order_date,
    ab_exp_id,
    ab_exp_value,
    ab_version,
    ab_rule_version,
    country_name,
    city_name,
    user_type,
    is_big_order_user,
    null as flow_uv,
    null as flow_s_all_uv,
    null as flow_d_all_uv,
    null as flow_b_all_uv,
    null as flow_d_s_uv,
    null as flow_b_ds_uv,
    null as flow_o_ds_order,
    null as flow_s2d,
    null as flow_d2b,
    null as flow_b2o,
    null as flow_s2o,
    q_commission_app,
    q_commission_c_view_app,
    q_gmv_app,
    q_coupon_amount_app,
    q_order_cnt_app,
    q_order_user_cnt_app,
    q_room_night_app,
    q_coupon_order_cnt_app,
    null as order_no_q,
    null as no_t0_cancel_order_no_q
from q_order_info_app;
