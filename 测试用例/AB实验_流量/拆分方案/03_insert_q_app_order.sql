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
      and order_date >= date_sub(${zdt.addDay(-89).format("yyyy-MM-dd")}, 90)
      and order_date <= date_sub(${zdt.addDay(-1).format("yyyy-MM-dd")}, 1)
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
q_app_order as (
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
        count(distinct a.order_no) as order_no_q,
        count(
            distinct case
                when (a.first_cancelled_time is null or date(a.first_cancelled_time) > a.order_date)
                 and (a.first_rejected_time is null or date(a.first_rejected_time) > a.order_date)
                 and (a.refund_time is null or date(a.refund_time) > a.order_date)
                    then a.order_no
            end
        ) as no_t0_cancel_order_no_q
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
      and a.is_valid = '1'
      and a.order_date = ${zdt.addDay(-1).format("yyyy-MM-dd")}
      and a.order_no <> '103576132435'
    group by
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
        end,
        if(no_user.no_user_id is null, '正常用户', '大单用户')
)
insert overwrite table ihotel_default.dw_ihotel_abtest_detail_flow_di
partition (
    dt = '${zdt.addDay(-1).format("yyyyMMdd")}',
type = 'order_base',
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
    null as uv,
    null as s_all_uv,
    null as d_all_uv,
    null as b_all_uv,
    null as d_s_uv,
    null as b_ds_uv,
    null as o_ds_order,
    null as s2d,
    null as d2b,
    null as b2o,
    null as s2o,
    null as q_commission_app,
    null as q_commission_c_view_app,
    null as q_gmv_app,
    null as q_coupon_amount_app,
    null as q_order_cnt_app,
    null as q_order_user_cnt_app,
    null as q_room_night_app,
    null as q_coupon_order_cnt_app,
    order_no_q,
    no_t0_cancel_order_no_q
from q_app_order;
