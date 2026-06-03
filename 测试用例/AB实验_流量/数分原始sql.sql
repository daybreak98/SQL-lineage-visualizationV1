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
         ,a.orig_device_id
         ,a.user_name
         ,search_pv
         ,detail_pv
         ,booking_pv
         ,order_pv
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

         ,init_gmv
         ,order_no
         ,room_night

         ,case when coupon_id is not null
        and batch_series not in ('MacaoDisco_ZK_5e27de','2night_ZK_952825','3night_ZK_ad8c83')
        and batch_series not like '%23base_ZK_728810%'
        and batch_series not like '%23extra_ZK_ce6f99%'
                   then 'Y' else 'N' end is_user_conpon   --- 是否用券

         ,case when (batch_series like '%23base_ZK_728810%' or batch_series like '%23extra_ZK_ce6f99%')
                   then (init_commission_after+coalesce(split(coupon_info['23base_ZK_728810'],'_')[1],0)+coalesce(split(coupon_info['23extra_ZK_ce6f99'],'_')[1],0)+coalesce(ext_plat_certificate,0))
               else init_commission_after+coalesce(ext_plat_certificate,0) end as final_commission_after  --- Q佣金

         --- qyj + zbj + xyb + qb = C视角Q佣金
         ,case when (batch_series like '%23base_ZK_728810%' or batch_series like '%23extra_ZK_ce6f99%')
                   then (init_commission_after_new+coalesce(split(coupon_info['23base_ZK_728810'],'_')[1],0)+coalesce(split(coupon_info['23extra_ZK_ce6f99'],'_')[1],0)+coalesce(ext_plat_certificate,0))
               else init_commission_after_new+coalesce(ext_plat_certificate,0) end as qyj  --- Q佣金
         ,case when coalesce(four_a, third_a) is not null and dt <= "20221124" then round(coalesce(((coalesce(second_a, first_a) - coalesce(four_a, third_a)) * room_night),(((bp + final_cost) *(1 + p_i_incr) - coalesce(four_a, third_a)) * room_night)),2)
               when coalesce(four_a, third_a) is not null and order_date <= "2024-03-29" then (coalesce(four_a_reduce, third_a_reduce)*room_night)
               else coalesce(cashbackmap['follow_price_amount']*room_night,0) end as zbj  --^ZJ^补
         ,coalesce(get_json_object(extendinfomap,'$.frame_amount'),0)*room_night as xyb  ---协议补
         ,coalesce(cashbackmap['framework_amount'],0) as qb  ---券补

         ,case when (coupon_substract_summary is null
        or batch_series like '%23base_ZK_728810%'
        or batch_series like '%23extra_ZK_ce6f99%') then 0
               else coalesce(coupon_substract_summary,0) end as coupon_substract_summary
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
   ,order_info_app as ( --- q app 订单汇总
    select order_date
         , ab_version
         , ab_rule_version
         ,t1.country_name
         ,t1.city_name
         ,t1.user_type
         ,t1.is_big_order_user
         ,sum(final_commission_after) as q_commission_app -- Q_佣金_app
         ,sum(qyj) + sum(zbj) + sum(xyb) + sum(qb) as q_commission_c_view_app -- Q_佣金（C视角）_app
         ,sum(init_gmv) as q_gmv_app -- Q_GMV_app
         ,sum(coupon_substract_summary) as q_coupon_amount_app -- Q_券额_app
         ,count(distinct order_no) as q_order_cnt_app -- Q_订单量_app
         ,count(distinct t1.user_id) as q_order_user_cnt_app -- Q_下单用户_app
         ,sum(room_night) as q_room_night_app -- Q_间夜量_app
         ,count(distinct case when is_user_conpon = 'Y' then order_no else null end)   as q_coupon_order_cnt_app -- Q_用券订单量_app
    from q_order_app t1
    group by 1,2,3
)
   ,qc_sdbo as (
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
                 ,sum(d_all_UV) d_all_UV
                 ,sum(b_all_UV) b_all_UV
                 ,sum(d_s_UV) d_s_UV
                 ,sum(b_ds_UV) b_ds_UV
                 ,sum(o_ds_order) o_ds_order
                 ,sum(q_uv) q_uv
                 ,sum(order_user_cnt) order_user_cnt
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
                          ,count(distinct case when detail_pv >0 then  a.user_id else null end )d_all_UV
                          ,count(distinct case when booking_pv >0 then a.user_id else null end )b_all_UV
                          ,count(distinct case when order_pv >0 then   a.user_id else null end )o_UV
                          ,count(distinct case when search_pv >0 or detail_pv>0 then  a.user_id else null end )sd_UV

                          ,count(distinct case when detail_pv >0 and search_pv >0 then a.user_id else null end) d_s_UV
                          ,count(distinct case when booking_pv >0 and detail_pv >0 and search_pv >0 then  a.user_id else null end ) b_ds_UV
                          ,count(distinct case when b.user_id is not null and detail_pv >0 and search_pv >0 then order_no else null end ) o_ds_order

                          ,count(distinct case when detail_pv >0 and search_pv <=0 then  a.user_id else null end )  d_z_UV
                          ,count(distinct case when booking_pv >0 and detail_pv >0 and search_pv <=0 then  a.user_id else null end )b_dz_UV
                          ,count(distinct case when b.user_id is not null and detail_pv >0 and search_pv <=0 then order_no else null end )o_dz_order
                          ,count(distinct a.user_id) q_uv
                          ,count(distinct b.user_id) order_user_cnt
                     from  uv a  -- 流量表
                               left join q_order_app b
                                   on a.dt=b.order_date
                                          and a.ab_version=b.ab_version
                                          and a.ab_rule_version=b.ab_rule_version
                                          and a.country_name=b.country_name
                                          and a.city_name=b.city_name
                                          and a.user_type=b.user_type
                                          and a.is_big_order_user=b.is_big_order_user
                     group by 1,2,3,4
                 ) a
            group by 1,2,3
        )t1
)
   ,q_app_order as (----订单明细表表包含取消  分目的地、新老维度 APP端
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
    group by 1
)
   ,q_data_info as (
    select t1.dt
         , t1.ab_version
         , t1.ab_rule_version
         , t1.country_name
         , t1.city_name
         , t1.user_type
         , t1.is_big_order_user
         , s2d
         , d2b
         , b2o
         ,coalesce(t1.uv, 0)   as uv
         ,coalesce(t4.q_room_night_app, 0)  as q_room_night_app -- Q_间夜量_app
         ,coalesce(t4.q_order_cnt_app, 0)  as q_order_cnt_app -- Q_订单量_app
         ,coalesce(t4.q_order_user_cnt_app, 0) as q_order_user_cnt_app -- Q_下单用户_app
         ,coalesce(t4.q_gmv_app, 0)      as q_gmv_app -- Q_GMV_app
         ,coalesce(t4.q_commission_app, 0)      as q_commission_app -- Q_佣金_app
         ,coalesce(t4.q_coupon_amount_app, 0)      as q_coupon_amount_app -- Q_券额_app
         ,coalesce(t4.q_order_cnt_app / t1.uv, 0)  as q_cr_app -- Q_CR_app
         ,coalesce(t4.q_room_night_app, 0) / coalesce(t4.q_order_cnt_app, 0) as q_avg_rn_per_order_app -- Q_单间夜_app
         ,coalesce(t4.q_commission_app, 0)  /  coalesce(t4.q_gmv_app, 0)   as q_take_rate_app -- Q_收益率_app
         ,coalesce(t4.q_coupon_amount_app, 0)  /  coalesce(t4.q_gmv_app, 0)   as q_subsidy_rate_app -- Q_券补贴率_app
         ,coalesce(t4.q_gmv_app, 0)  /  coalesce(t4.q_room_night_app, 0) as q_adr_app -- Q_ADR_app
         ,coalesce(t4.q_coupon_order_cnt_app, 0) / coalesce(t4.q_order_cnt_app, 0)  as q_coupon_order_rate_app -- Q_用券订单占比_app
         , t4.q_coupon_order_cnt_app as q_coupon_order_cnt_app
    from qc_sdbo t1
             left join order_info_app t4 on t1.dt=t4.order_date
        and t1.ab_version = t4.ab_version
        and t1.ab_rule_version = t4.ab_rule_version
--         and t1.country_name
--         and t1.city_name
--         and t1.user_type
--         and t1.is_big_order_user
             left join q_app_order t5 on t5.order_date = t1.dt
        and t1.ab_version = t5.ab_version
        and t1.ab_rule_version = t5.ab_rule_version
--         and t1.country_name
--         and t1.city_name
--         and t1.user_type
--         and t1.is_big_order_user
)

select q_commission_app / uv     revenue_per_uv                      ---单uv收益
     , uv
     , s2d
     , d2b
     , b2o

     , q_cr_app                                        -- Q_CR_app
     , q_order_user_cnt_app / uv as u2o                ---u2o
     , q_order_user_cnt_app                            -- Q_下单用户_app
     , q_gmv_app                                       -- Q_GMV_app
     , q_commission_app                                -- Q_佣金_app
     , q_room_night_app                                -- Q_间夜量_app
     , q_order_cnt_app                                 -- Q_订单量_app
     , q_adr_app                                       -- Q_ADR_app
     , q_avg_rn_per_order_app                          -- Q_单间夜_app
     , q_coupon_amount_app                             -- Q_券额_app
     , q_coupon_order_cnt_app                          -- Q_用券订单量_app
     , q_subsidy_rate_app           q_subsidy_rate_app -- Q_券补贴率_app
     , q_coupon_order_rate_app                         -- Q_用券订单占比_app

     , no_t0_cancel_order_no_q
     , order_no_q
     , no_t0_cancel_order_no_q / order_no_q            --T0取消率

from (---- 预定口径Q数据
         select dt
              ,uv
              , s2d
              , d2b
              , b2o
              ,q_room_night_app -- Q_间夜量_app
              ,q_order_cnt_app -- Q_订单量_app
              ,q_order_user_cnt_app -- Q_下单用户_app
              ,q_gmv_app -- Q_GMV_app
              ,q_commission_app -- Q_佣金_app
              ,q_coupon_amount_app -- Q_券额_app
              ,q_cr_app -- Q_CR_app
              ,q_avg_rn_per_order_app -- Q_单间夜_app
              ,q_take_rate_app -- Q_收益率_app
              ,q_subsidy_rate_app -- Q_券补贴率_app
              ,q_adr_app -- Q_ADR_app
              ,q_coupon_order_rate_app -- Q_用券订单占比_app
              ,q_coupon_order_cnt_app
              ,q_order_cnt_app
         from q_data_info
     ) t1
