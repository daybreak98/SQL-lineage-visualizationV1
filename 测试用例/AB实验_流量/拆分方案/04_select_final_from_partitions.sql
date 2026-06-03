with q_flow_info as (
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
        uv,
        s_all_uv,
        d_all_uv,
        b_all_uv,
        d_s_uv,
        b_ds_uv,
        o_ds_order,
        s2d,
        d2b,
        b2o,
        s2o
    from default.dw_ihotel_abtest_detail_flow_di
    where dt = '%(DATE)s'
      and data_type = 'q_flow_info'
      and ('%(ORDER_DATE)s' = '' or order_date = '%(ORDER_DATE)s')
      and ('%(AB_EXP_ID)s' = '' or ab_exp_id = '%(AB_EXP_ID)s')
      and ('%(AB_EXP_VALUE)s' = '' or ab_exp_value = '%(AB_EXP_VALUE)s')
      and ('%(AB_VERSION)s' = '' or ab_version = '%(AB_VERSION)s')
      and ('%(AB_RULE_VERSION)s' = '' or ab_rule_version = '%(AB_RULE_VERSION)s')
      and ('%(COUNTRY_NAME)s' = '' or country_name = '%(COUNTRY_NAME)s')
      and ('%(CITY_NAME)s' = '' or city_name = '%(CITY_NAME)s')
      and ('%(USER_TYPE)s' = '' or user_type = '%(USER_TYPE)s')
      and ('%(IS_BIG_ORDER_USER)s' = '' or is_big_order_user = '%(IS_BIG_ORDER_USER)s')
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
        q_commission_app,
        q_commission_c_view_app,
        q_gmv_app,
        q_coupon_amount_app,
        q_order_cnt_app,
        q_order_user_cnt_app,
        q_room_night_app,
        q_coupon_order_cnt_app
    from default.dw_ihotel_abtest_detail_flow_di
    where dt = '%(DATE)s'
      and data_type = 'q_order_info_app'
      and ('%(ORDER_DATE)s' = '' or order_date = '%(ORDER_DATE)s')
      and ('%(AB_EXP_ID)s' = '' or ab_exp_id = '%(AB_EXP_ID)s')
      and ('%(AB_EXP_VALUE)s' = '' or ab_exp_value = '%(AB_EXP_VALUE)s')
      and ('%(AB_VERSION)s' = '' or ab_version = '%(AB_VERSION)s')
      and ('%(AB_RULE_VERSION)s' = '' or ab_rule_version = '%(AB_RULE_VERSION)s')
      and ('%(COUNTRY_NAME)s' = '' or country_name = '%(COUNTRY_NAME)s')
      and ('%(CITY_NAME)s' = '' or city_name = '%(CITY_NAME)s')
      and ('%(USER_TYPE)s' = '' or user_type = '%(USER_TYPE)s')
      and ('%(IS_BIG_ORDER_USER)s' = '' or is_big_order_user = '%(IS_BIG_ORDER_USER)s')
),
q_app_order as (
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
        order_no_q,
        no_t0_cancel_order_no_q
    from default.dw_ihotel_abtest_detail_flow_di
    where dt = '%(DATE)s'
      and data_type = 'q_app_order'
      and ('%(ORDER_DATE)s' = '' or order_date = '%(ORDER_DATE)s')
      and ('%(AB_EXP_ID)s' = '' or ab_exp_id = '%(AB_EXP_ID)s')
      and ('%(AB_EXP_VALUE)s' = '' or ab_exp_value = '%(AB_EXP_VALUE)s')
      and ('%(AB_VERSION)s' = '' or ab_version = '%(AB_VERSION)s')
      and ('%(AB_RULE_VERSION)s' = '' or ab_rule_version = '%(AB_RULE_VERSION)s')
      and ('%(COUNTRY_NAME)s' = '' or country_name = '%(COUNTRY_NAME)s')
      and ('%(CITY_NAME)s' = '' or city_name = '%(CITY_NAME)s')
      and ('%(USER_TYPE)s' = '' or user_type = '%(USER_TYPE)s')
      and ('%(IS_BIG_ORDER_USER)s' = '' or is_big_order_user = '%(IS_BIG_ORDER_USER)s')
),
keys as (
    select
        order_date,
        ab_exp_id,
        ab_exp_value,
        ab_version,
        ab_rule_version,
        country_name,
        city_name,
        user_type,
        is_big_order_user
    from q_flow_info
    union
    select
        order_date,
        ab_exp_id,
        ab_exp_value,
        ab_version,
        ab_rule_version,
        country_name,
        city_name,
        user_type,
        is_big_order_user
    from q_order_info_app
    union
    select
        order_date,
        ab_exp_id,
        ab_exp_value,
        ab_version,
        ab_rule_version,
        country_name,
        city_name,
        user_type,
        is_big_order_user
    from q_app_order
)
select
    k.order_date,
    k.ab_exp_id,
    k.ab_exp_value,
    k.ab_version,
    k.ab_rule_version,
    k.country_name,
    k.city_name,
    k.user_type,
    k.is_big_order_user,
    case
        when coalesce(f.uv, 0) > 0
            then 1.0 * coalesce(o.q_commission_app, 0) / f.uv
        else 0
    end as subsidy_per_uv,
    coalesce(f.uv, 0) as uv,
    coalesce(f.s_all_uv, 0) as s_all_uv,
    coalesce(f.d_all_uv, 0) as d_all_uv,
    coalesce(f.b_all_uv, 0) as b_all_uv,
    coalesce(f.d_s_uv, 0) as d_s_uv,
    coalesce(f.b_ds_uv, 0) as b_ds_uv,
    coalesce(f.o_ds_order, 0) as o_ds_order,
    coalesce(f.s2d, 0) as s2d,
    coalesce(f.d2b, 0) as d2b,
    coalesce(f.b2o, 0) as b2o,
    coalesce(f.s2o, 0) as s2o,
    case
        when coalesce(f.uv, 0) > 0
            then 1.0 * coalesce(o.q_order_cnt_app, 0) / f.uv
        else 0
    end as cr,
    case
        when coalesce(f.uv, 0) > 0
            then 1.0 * coalesce(o.q_order_user_cnt_app, 0) / f.uv
        else 0
    end as u2o,
    case
        when coalesce(a.order_no_q, 0) > 0
            then 1.0 * (coalesce(a.order_no_q, 0) - coalesce(a.no_t0_cancel_order_no_q, 0)) / a.order_no_q
        else 0
    end as cancel_rate,
    coalesce(o.q_gmv_app, 0) as gmv,
    coalesce(o.q_commission_app, 0) as commission,
    coalesce(o.q_room_night_app, 0) as room_night,
    coalesce(o.q_order_cnt_app, 0) as order_cnt,
    coalesce(o.q_order_user_cnt_app, 0) as order_user_cnt,
    case
        when coalesce(o.q_room_night_app, 0) > 0
            then 1.0 * coalesce(o.q_gmv_app, 0) / o.q_room_night_app
        else 0
    end as adr,
    case
        when coalesce(o.q_order_cnt_app, 0) > 0
            then 1.0 * coalesce(o.q_room_night_app, 0) / o.q_order_cnt_app
        else 0
    end as avg_rn_per_order,
    coalesce(o.q_coupon_amount_app, 0) as coupon_amount,
    coalesce(o.q_coupon_order_cnt_app, 0) as coupon_order_cnt,
    case
        when coalesce(o.q_gmv_app, 0) > 0
            then 1.0 * coalesce(o.q_coupon_amount_app, 0) / o.q_gmv_app
        else 0
    end as subsidy_rate,
    case
        when coalesce(o.q_order_cnt_app, 0) > 0
            then 1.0 * coalesce(o.q_coupon_order_cnt_app, 0) / o.q_order_cnt_app
        else 0
    end as coupon_order_rate,
    coalesce(o.q_commission_c_view_app, 0) as commission_c_view_app,
    coalesce(a.order_no_q, 0) as order_no_q,
    coalesce(a.no_t0_cancel_order_no_q, 0) as no_t0_cancel_order_no_q
from keys k
left join q_flow_info f
    on k.order_date = f.order_date
   and k.ab_exp_id = f.ab_exp_id
   and k.ab_exp_value = f.ab_exp_value
   and k.ab_version = f.ab_version
   and k.ab_rule_version = f.ab_rule_version
   and k.country_name = f.country_name
   and k.city_name = f.city_name
   and k.user_type = f.user_type
   and k.is_big_order_user = f.is_big_order_user
left join q_order_info_app o
    on k.order_date = o.order_date
   and k.ab_exp_id = o.ab_exp_id
   and k.ab_exp_value = o.ab_exp_value
   and k.ab_version = o.ab_version
   and k.ab_rule_version = o.ab_rule_version
   and k.country_name = o.country_name
   and k.city_name = o.city_name
   and k.user_type = o.user_type
   and k.is_big_order_user = o.is_big_order_user
left join q_app_order a
    on k.order_date = a.order_date
   and k.ab_exp_id = a.ab_exp_id
   and k.ab_exp_value = a.ab_exp_value
   and k.ab_version = a.ab_version
   and k.ab_rule_version = a.ab_rule_version
   and k.country_name = a.country_name
   and k.city_name = a.city_name
   and k.user_type = a.user_type
   and k.is_big_order_user = a.is_big_order_user
order by
    k.order_date,
    k.ab_exp_id,
    k.ab_exp_value,
    k.ab_version,
    k.ab_rule_version,
    k.country_name,
    k.city_name,
    k.user_type,
    k.is_big_order_user;
