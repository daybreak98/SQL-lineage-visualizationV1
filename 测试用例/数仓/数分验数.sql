with user_type as
    (
        select  user_id
             ,case when level_desc='大众' then 'R1'
                   when level_desc='白银' then 'R1_5'
                   when level_desc='黄金' then 'R2'
                   when level_desc='铂金' then 'R3'
                   when level_desc='钻石' then 'R4' end as level_desc
        from pub.dim_user_profile_nd
        group by 1,2
    )
   , hotel_info as
    (
        select  hotel_seq
             ,attrs['ctripRecommendLevel'] AS medal
        FROM ihotel_default.ods_qhotel_intl_hotel_info_publish
        WHERE dt = '20260414'
          and attrs['ctripRecommendLevel'] is not null
        group by 1,2
    )
   ,ab_rule as (
    select
        ab_exp_id
         ,ab_version
         ,ab_rule_version
         ,device_id as ab_exp_value
    from
        (
            select
                ab_exp_id,
                ab_version,
                ab_rule_version
            from default.ods_abtest_rule_info
            where dt = '20260414'
              and source = 'hotel'
              and ab_shuntbase='APP_UID'
              and ab_exp_id = '260402_ho_gj_comment_limit'
        ) rule
            join
        (
            select  expid, version, ruleversion, clientcode as device_id, dt,logdate
            from default.ods_abtest_sdk_log_endtime_hotel
            where dt='20260414'
              and clientcode is not NULL
              and expid is not NULL
              and version is not NULL
              and ruleversion is not NULL
              and expid !=''
              and version !=''
              and clientcode not in ('0','00000000','00000000000000','000000000000000','0000000000000000','0000000000000000000000000000000000000000','','ctrip','elong','352284040670808')
              and (clientcode not like 'tc%' and clientcode not like 'wx%' and clientcode not like 'pd%')
        )ab
        on ab.expid=rule.ab_exp_id and ab.version=rule.ab_version and ab.ruleversion=rule.ab_rule_version
    group by 1,2,3,4
)
   ,product as
    (
        select *
        from
            (
                select
                    *
                     ,row_number() over (partition by uniq_id,hotel_seq order by qprice asc,cprice asc) as rn
                from
                    (
                        select  dt
                             ,crawl_time --抓取时间
                             ,uniq_id
                             ,id
                             ,identity as level_desc -- 用户身份
                             ,hotel_seq --酒店id
                             ,check_in  --入住时间
                             ,check_out --离店时间
                             --,qunar_physical_room_id
                             --,ctrip_physical_room_id
                             ,a.qunar_pay_price as qprice -- q价
                             ,a.ctrip_pay_price as cprice -- c价
                             ,case when qunar_pay_price > ctrip_pay_price then '0'
                                   when qunar_pay_price = ctrip_pay_price then '1'
                                   when qunar_pay_price < ctrip_pay_price then '2'
                            end as is_lose -- 产品力分类
                        from default.dwd_hotel_cq_compare_price_result_intl_hi a
                        WHERE dt = '20260414' -- 自定义日期
                          --where substr(dt,1,6) = '202509'
                          and business_type = 'intl_crawl_cq_spa' -- 抓取口径
                          --and compare_type = 'HOTEL_LOWEST'
                          and compare_type = 'PHYSICAL_ROOM_TYPE_LOWEST'
                          and room_type_cover = 'Qmeet'
                          and ctrip_room_status = 'true'
                          and qunar_room_status = 'true'
                    )a
            )b
        where rn =1
    )
   ,search_list as
    (
        select *
        from
            (
                select concat(substr(a.dt,1,4),'-',substr(a.dt,5,2),'-',substr(a.dt,7,2)) as datee,
                    search_request_uid,a.hotel_seq,a.user_id,detail_log_id,detail_device_id,
                    device_id,orig_device_id,rank,sort_price,order_info_device_id,is_display,
                    render_price,cast(a.qpayprice as decimal(20,0)) as qpayprice,a.cpayprice,is_query,is_same_city,
                    is_filter,intention,suggest_type,a.country_name,a.province_name,checkin_date,checkout_date,log_datetime,total_hotels
                     ,case when is_query = '0' and is_filter='0' and is_same_city=0 then '0异地空搜'
                           when is_query = '0' and is_filter='0' and is_same_city=1 then '1本地空搜'
                           when is_query = '1' and is_filter='0' and intention = 'poi' then '2poi'
                           when is_query = '1' and is_filter='0' and (intention = 'brand' or (suggest_type = 'brand' and intention is null)
                               or (suggest_type = 'group' and intention is null) or intention = 'group'
                               or (intention = 'hotelName' or (suggest_type = 'hotelName' and intention is null))
                               ) then '3酒店/集团'
                           when is_query = '1' and is_filter='0' and intention = 'bizZone' then '4商业区'
                           else '5其他' end as intention1
                     ,case when a.province_name in ('澳门','香港') then province_name
                           when a.country_name in ('泰国','日本','韩国','新加坡','马来西亚','美国','印度尼西亚','俄罗斯') then a.country_name
                           when e.area in ('欧洲','亚太','美洲') then e.area  else '其他' end as country
                     ,case when d.is_lose = '0' then '产品力lose'
                           when d.is_lose = '1' or (d.is_lose = '2' and 1-d.qprice/d.cprice < 0.02) then '产品力beat0-2'
                           when d.is_lose = '2' and (1-d.qprice/d.cprice >= 0.02 and 1-d.qprice/d.cprice < 0.05) then '产品力beat2-5'
                           when d.is_lose = '2' and 1-d.qprice/d.cprice >= 0.05 then '产品力beat5以上'
                           else '其他' end as product_range
                     ,case when render_price = '2147483647' then null else render_price end as new_render_price
                     ,case when sort_price = '2147483647' then null else sort_price end as new_sort_price
                     ,order_info_order_no
                     ,case when detail_log_id is not null then rank else null end as click_rank
                     ,case when order_info_order_no is not null then rank else null end as order_rank
                     ,case when c.medal in ('5','6') then '挂牌酒店'
                           else '无牌酒店' end as medal_type
                     ,commission_map['bu_commission'] as show_commission
                     ,cast(sort_v2_map[map_keys(sort_v2_map)[0]] as decimal(20,0)) AS sort_v2_price
                     ,row_number() over (partition by a.search_request_uid, a.qtrace_id,a.orig_device_id,a.detail_log_id,a.order_order_no,a.order_info_order_no,a.hotel_seq, a.checkin_date, a.checkout_date, b.level_desc order by abs(unix_timestamp(crawl_time)-unix_timestamp(log_datetime)) asc) as rn
                from default.dwd_ihotel_flow_app_searchlist_di a
                         left join temp.temp_yiquny_zhang_ihotel_area_region_forever e
                                   on a.country_name = e.country_name
                         left join user_type b
                                   on a.user_id = b.user_id
                         left join hotel_info c
                                   on a.hotel_seq = c.hotel_seq
                         left join product d
                                   on a.dt =d.dt and b.level_desc = d.level_desc and a.hotel_seq = d.hotel_seq and a.checkin_date = d.check_in and a.checkout_date = d.check_out
                where a.dt = '20260414' --自定义日期
                  --where substr(a.dt,1,6) = '202509'
                  and ( a.province_name in ('台湾', '澳门', '香港') or a.country_name != '中国' )
                  and orig_device_id is not null
                  and orig_device_id != ''
                  and search_type in (0, 16, 17)
            )a
        where rn = 1
    )
   ,order_detail as
    (
        select  a.order_date as datee
             --,element_at(user_info,'orig_device_id') as orig_device_id
             ,a.user_info['orig_device_id'] as orig_device_id
             ,a.user_id
             ,a.order_no
             ,a.hotel_seq
             ,a.room_night
             ,a.checkin_date
             ,a.checkout_date
             ,a.init_gmv
             ,cast((case when (batch_series like '%23base_ZK_728810%' or batch_series like '%23extra_ZK_ce6f99%')
                             then (init_commission_after+nvl(split(coupon_info['23base_ZK_728810'],'_')[1],0)+nvl(split(coupon_info['23extra_ZK_ce6f99'],'_')[1],0)+nvl(ext_plat_certificate,0))
                         else init_commission_after+nvl(ext_plat_certificate,0) end) as decimal(20,0)) as order_commission
        from mdw_order_v3_international a
                 inner join (select  order_info_order_no from search_list where order_info_order_no is not null group by 1) b
                            on a.order_no = b.order_info_order_no
        where a.dt = '20260414' -- 最新分区
          and (a.province_name in ('台湾', '澳门', '香港') or a.country_name != '中国')
          and a.terminal_channel_type = 'app'
          and (a.first_cancelled_time is null or date(a.first_cancelled_time) > order_date)
          and (a.first_rejected_time is null or date(a.first_rejected_time) > order_date)
          and (a.refund_time is null or date(a.refund_time) > order_date)
          and a.is_valid = '1'
          and substr(cast(a.order_date as string),1,10) = '2026-04-14' -- 自定义日期
        --and substr(cast(order_date as string),1,10) between '2025-07-11' and '2025-07-25'
        group by 1,2,3,4,5,6,7,8,9,10
    )
   ,search_result as
    (
        select a.datee
             ,a.ab_version
             ,count(distinct a.search_request_uid) as search_times
             ,count(distinct a.orig_device_id) as search_uv
             ,count(case when a.is_display = '1' then a.hotel_seq else null end) as show_item
             ,count(distinct case when a.is_display = '1' then a.search_request_uid else null end) as show_pv
             ,count(case when a.is_display = '1' and abs(a.sort_v2_price- a.qpayprice)/a.qpayprice <= 0.000001 then a.hotel_seq else null end) as sort_right_show_item
             ,count(case when a.is_display = '1' and a.medal_type = '挂牌酒店' then a.hotel_seq else null end) as medal_show_item
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null then a.orig_device_id else null end) as show_uv
             ,count(case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.hotel_seq else null end) as click_item
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.search_request_uid else null end) as click_pv
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 1 then a.search_request_uid else null end) as top1_click_pv
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 3 then a.search_request_uid else null end) as top3_click_pv
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 5 then a.search_request_uid else null end) as top5_click_pv
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 10 then a.search_request_uid else null end) as top10_click_pv
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.orig_device_id else null end) as click_uv
             ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.order_info_order_no is not null then a.orig_device_id else null end) as order_uv
             ,count(distinct case when a.total_hotels is null or a.total_hotels = 0 then a.search_request_uid else null end) as no_result_times
--              ,count(case when a.is_display = '1' and a.new_render_price is null and a.new_sort_price is not null then a.hotel_seq else null end) as no_price_show_item
             ,count(case when a.is_display = 1 and a.qpayprice is null then a.hotel_seq else null end) as no_price_show_item
             ,avg(a.click_rank) as avg_click_rank
             ,avg(a.order_rank) as avg_order_rank
             ,avg(case when a.is_display = '1' and a.hotel_seq is not null then a.qpayprice else null end) as show_adr
             ,count(case when  a.is_display = '1' and a.product_range = '产品力lose' and a.rank <= 3 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
            /count(case when  a.is_display = '1' and a.product_range != '其他' and a.rank <= 3  and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as lose_rate_show_pv_3
             ,count(case when  a.is_display = '1' and a.product_range = '产品力lose' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
            /count(case when  a.is_display = '1' and a.product_range != '其他' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as lose_rate_show_pv_10
             ,count(case when a.is_display = '1' and a.product_range != '其他' and a.rank <= 3 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
            /count(case when a.is_display = '1' and a.rank <= 3 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as cover_rate_show_pv_3
             ,count(case when a.is_display = '1' and a.product_range != '其他' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
            /count(case when a.is_display = '1' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as cover_rate_show_pv_10
             ,count(distinct a.order_info_order_no) as order_num
             ,count(distinct case when a.order_info_order_no is not null then a.search_request_uid else null end ) as order_pv
             ,count(distinct case when a.rank<= 1 and a.order_info_order_no is not null then a.search_request_uid else null end) as top1_order_pv
             ,count(distinct case when a.rank<= 3 and a.order_info_order_no is not null then a.search_request_uid else null end) as top3_order_pv
             ,count(distinct case when a.rank<= 5 and a.order_info_order_no is not null then a.search_request_uid else null end) as top5_order_pv
             ,count(distinct case when a.rank<= 10 and a.order_info_order_no is not null then a.search_request_uid else null end) as top10_order_pv
        from
--             search_list a
(select * from
    ab_rule left join search_list
                      on ab_rule.ab_exp_value = search_list.orig_device_id) a
        group by 1,2
    )
   ,order_result as
    (
        select a.datee
             ,a.ab_version
             ,sum(a.init_gmv) as total_gmv
             ,sum(a.room_night) as total_room_night
             ,sum(a.init_gmv)/sum(a.room_night) as order_adr
             ,sum(a.order_commission) as total_order_commission
        from
--             order_detail a
(select * from
    ab_rule left join order_detail
                      on ab_rule.ab_exp_value = order_detail.orig_device_id) a
        group by 1,2
    )


select
--     a.datee
     a.ab_version
     ---- S级报表
     ,cast (b.total_order_commission/a.show_uv as decimal(20,2)) as `单UV收益`
     ,concat(round(a.click_uv/a.show_uv*100,2),'%') as `S2D`
     ,concat(round(a.order_uv/a.show_uv*100,2),'%') as `S2O`
     ,concat(round(a.click_pv/a.show_pv*100,2),'%') as `搜索点击率_pv`
     ,concat(round(a.order_pv/a.show_pv*100,2),'%') as `搜索预定率_pv`
     ,concat(round(a.no_result_times/a.search_times*100,2),'%')  as `搜索无结果率`
     ,concat(round(a.no_price_show_item/a.show_item*100,2),'%')  as `无库存流量占比`

     ,concat(round(a.top1_click_pv/a.click_pv*100,2),'%') as `TOP1点击命中率_PV`
     ,concat(round(a.top1_order_pv/a.order_num*100,2),'%') as `TOP1预定命中率_PV`
     ,concat(round(a.top3_click_pv/a.click_pv*100,2),'%') as `TOP3点击命中率_PV`
     ,concat(round(a.top3_order_pv/a.order_num*100,2),'%') as `TOP3预定命中率_PV`
     ,concat(round(a.top5_click_pv/a.click_pv*100,2),'%') as `TOP5点击命中率_PV`
     ,concat(round(a.top5_order_pv/a.order_num*100,2),'%') as `TOP5预定命中率_PV`
     ,concat(round(a.top10_click_pv/a.click_pv*100,2),'%') as `TOP10点击命中率_PV`
     ,concat(round(a.top10_order_pv/a.order_num*100,2),'%') as `TOP10预定命中率_PV`

     ,cast(b.order_adr as decimal(20,2)) as `订单ADR`
     ,cast(a.show_adr as decimal(20,2)) as `曝光ADR`
     ,concat(round((a.show_adr/b.order_adr-1)*100,2),'%')  as `曝光与订单adr_gap`
from
    search_result a
        join order_result b
             on a.datee = b.datee
                 and a.ab_version = b.ab_version
order by 1 desc