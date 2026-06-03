with order_90 as (select order_date,
                         user_id,
                         count(order_no) as order_nos_90,
                         sum(room_night) as room_nights_90
                  from default.mdw_order_v3_international
                  where dt = '20260414'
                    and (province_name in ('台湾', '澳门', '香港') or country_name != '中国')
                    and terminal_channel_type = 'app'
                    and is_valid = '1'
                    and order_status not in ('CANCELLED', 'REJECTED')
                    and order_date >= date_sub('2026-04-15', 90)
                    and order_date <= date_sub('2026-04-15', 1)
                  group by 1, 2)
   , no_user as (select distinct user_id no_user_id
                 from order_90
                 where room_nights_90 >= 15)
   , ab_rule as (select ab_exp_id
                      , ab_version
                      , ab_rule_version
                      , device_id as ab_exp_value
                 from (select ab_exp_id,
                              ab_version,
                              ab_rule_version
                       from default.ods_abtest_rule_info
                       where dt = '20260414'
                         and source = 'hotel'
                         and ab_shuntbase = 'APP_UID'
                         and ab_exp_id = '251204_ho_gj_ai_compare_price'
                      ) rule
                          join
                      (select expid, version, ruleversion, clientcode as device_id, dt, logdate
                       from default.ods_abtest_sdk_log_endtime_hotel
                       where dt = '20260414'
                         and clientcode is not NULL
                         and expid is not NULL
                         and version is not NULL
                         and ruleversion is not NULL
                         and expid != ''
                         and version != ''
                         and clientcode not in ('0', '00000000', '00000000000000', '000000000000000', '0000000000000000',
                                                '0000000000000000000000000000000000000000', '', 'ctrip', 'elong',
                                                '352284040670808')
                         and (clientcode not like 'tc%' and clientcode not like 'wx%' and clientcode not like 'pd%')) ab
                      on ab.expid = rule.ab_exp_id and ab.version = rule.ab_version and
                         ab.ruleversion = rule.ab_rule_version
                 group by 1, 2, 3, 4)
   , user_type as (
    select user_id
         ,min(order_date) as min_order_date
    from default.mdw_order_v3_international   --- 海外订单表
    where dt = '20260414'
      and (province_name in ('台湾', '澳门', '香港') or country_name != '中国')
      and terminal_channel_type in ('www', 'app', 'touch')
      and order_status not in ('CANCELLED', 'REJECTED')
      and is_valid = '1'
    group by 1
)
   , uv as (----分日去重活跃用户
    select  dt
         ,t.ab_version
         ,t.ab_rule_version
         ,a.country_name
         ,a.city_name
         ,case when dt > b.min_order_date then '老客' else '新客' end as user_type
         , if(no_user_id is null,'正常用户','大单用户') as is_big_order_user
         ,a.user_id
--          ,a.orig_device_id
--          ,a.user_name
         ,sum(search_pv) search_pv
         ,sum(detail_pv) detail_pv
         ,sum(booking_pv) booking_pv
         ,sum(order_pv) order_pv
    from ihotel_default.mdw_user_app_log_sdbo_di_v1 a
             left join temp.temp_yiquny_zhang_ihotel_area_region_forever e on a.country_name = e.country_name
             left join user_type b on a.user_id = b.user_id
             left join no_user on a.user_id = no_user.no_user_id
             right join ab_rule t on t.ab_exp_value = a.orig_device_id
    where dt = '2026-04-14'
      and business_type = 'hotel'
      and (province_name in ('台湾', '澳门', '香港') or a.country_name != '中国')
      and (search_pv + detail_pv + booking_pv + order_pv) > 0
      and a.user_name is not null and a.user_name not in ('null', 'NULL', '', ' ')
      and a.user_id is not null and a.user_id not in ('null', 'NULL', '', ' ')
    group by 1,2,3,4,5,6,7,8
)
   ,q_order_app as (----订单明细表包含取消  分目的地、新老维度 app
    select order_date
         ,t.ab_version
         ,t.ab_rule_version
         ,a.country_name
         ,a.city_name
         ,case when order_date = b.min_order_date then '新客' else '老客' end as user_type
         ,if(no_user_id is null,'正常用户','大单用户') is_big_order_user
         ,a.user_id
         ,a.user_info['orig_device_id']     --和user_id不共存
         ,a.order_no
    from default.mdw_order_v3_international a
             left join user_type b on a.user_id = b.user_id
             left join temp.temp_yiquny_zhang_ihotel_area_region_forever e on a.country_name = e.country_name
             left join no_user on a.user_id = no_user.no_user_id
             right join ab_rule t on t.ab_exp_value =  a.user_info['orig_device_id']
    where dt = '20260414'
      and (province_name in ('台湾','澳门','香港') or a.country_name !='中国')
      and terminal_channel_type = 'app'
      and (first_cancelled_time is null or date(first_cancelled_time) > order_date)
      and (first_rejected_time is null or date(first_rejected_time) > order_date)
      and (refund_time is null or date(refund_time) > order_date)
      and is_valid='1'
      and order_date = '2026-04-14'
      and order_no <> '103576132435'
)
    select t1.dt
         ,ab_version
         ,ab_rule_version
         ,t1.country_name
         ,t1.city_name
         ,t1.user_type
         ,t1.is_big_order_user
         ,q_uv uv
         ,s_all_UV
         ,d_s_UV
         ,b_ds_UV
         ,o_ds_order
         ,d_s_UV / s_all_UV   s2d
         ,b_ds_UV / d_s_UV   d2b
         ,o_ds_order / b_ds_UV  b2o
         ,o_ds_order / s_all_UV  s2o

    from(
            select  dt
                 ,a.ab_version
                 ,a.ab_rule_version
                 ,a.country_name
                 ,a.city_name
                 ,a.user_type
                 ,a.is_big_order_user
                 ,sum(s_all_UV) s_all_UV
                 ,sum(d_s_UV) d_s_UV
                 ,sum(b_ds_UV) b_ds_UV
                 ,sum(o_ds_order) o_ds_order
                 ,sum(q_uv) q_uv
            from (
                     select
                         a.dt
                          ,a.ab_version
                          ,a.ab_rule_version
                          ,a.country_name
                          ,a.city_name
                          ,a.user_type
                          ,a.is_big_order_user
                          ,count(distinct case when search_pv >0 then  a.user_id else null end )s_all_UV
                          ,count(distinct case when detail_pv >0 and search_pv >0 then a.user_id else null end) d_s_UV
                          ,count(distinct case when booking_pv >0 and detail_pv >0 and search_pv >0 then  a.user_id else null end ) b_ds_UV
                          ,count(distinct case when b.user_id is not null and detail_pv >0 and search_pv >0 then order_no else null end ) o_ds_order
                          ,count(distinct a.user_id) q_uv
                     from  uv a  -- 流量表
                               left join q_order_app b
                                         on a.dt=b.order_date
                                             and a.ab_version=b.ab_version
                                             and a.ab_rule_version=b.ab_rule_version
                                             and a.country_name=b.country_name
                                             and a.city_name=b.city_name
                                             and a.user_type=b.user_type
                                             and a.is_big_order_user=b.is_big_order_user
                                             and a.user_id=b.user_id
                     group by 1,2,3,4,5,6,7
                 ) a
            group by 1,2,3,4,5,6,7
        )t1
