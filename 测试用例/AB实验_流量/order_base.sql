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
select order_date
         ,ab_version
         ,ab_rule_version
         ,a.country_name
         ,a.city_name
         ,case when order_date = b.min_order_date then '新客' else '老客' end as user_type
         ,if(no_user_id is null,'正常用户','大单用户') is_big_order_user
         ,count(distinct order_no) order_no_q
         ,count(distinct case when (first_cancelled_time is null or date(first_cancelled_time) > order_date)
        and (first_rejected_time is null or date(first_rejected_time) > order_date)
        and (refund_time is null or date(refund_time) > order_date)
                                  then order_no end) no_t0_cancel_order_no_q
    from mdw_order_v3_international a
             left join user_type b on a.user_id = b.user_id
             left join temp.temp_yiquny_zhang_ihotel_area_region_forever e on a.country_name = e.country_name
             left join no_user on a.user_id = no_user.no_user_id
             right join ab_rule t on t.ab_exp_value =  a.user_info['orig_device_id']
    where dt = '20260414'
      and (province_name in ('台湾','澳门','香港') or a.country_name !='中国')
      and terminal_channel_type = 'app'
      and is_valid='1'
      and order_date = '2026-04-14'
      and order_no <> '103576132435'
      and case when order_date = b.min_order_date then '新客' else '老客' end = '新客'
    --       and t1.country_name
--       and t1.city_name
--       and t1.user_type
--       and t1.is_big_order_user
    group by 1,2,3,4,5,6,7
