with order_90 as (
    select
        order_date,
        user_id,
        count(order_no) as order_nos_90,
        sum(room_night) as room_nights_90
    from default.mdw_order_v3_international
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
      and (province_name in ('台湾','澳门','香港') or country_name != '中国')
      and terminal_channel_type = 'app'
      and is_valid = '1'
      and order_status not in ('CANCELLED','REJECTED')
      and order_date >= '${zdt.addDay(-90).format("yyyy-MM-dd")}'
      and order_date <= '${zdt.addDay(-1).format("yyyy-MM-dd")}'
    group by 1,2
)
   ,no_user as (--- 大单用户
    select distinct user_id no_user_id
    from order_90
    where room_nights_90 >= 15
),
    user_type as
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
        WHERE dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
          and attrs['ctripRecommendLevel'] is not null
        group by 1,2
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
                        WHERE dt = '${zdt.addDay(-1).format("yyyyMMdd")}' -- 自定义日期
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
   , mdw_user_type as (select user_id
                            , min(order_date) as min_order_date
                       from default.mdw_order_v3_international
                       where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
                         and (province_name in ('台湾', '澳门', '香港') or country_name != '中国')
                         and terminal_channel_type in ('www', 'app', 'touch')
                         and order_status not in ('CANCELLED', 'REJECTED')
                         and is_valid = '1'
                       group by 1)
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

                     ,case when substr(log_datetime, 1, 10) > mdw.min_order_date then '老客' else '新客' end as newolduser
                     ,case
                          when (cast(hotel_grade as int) >= 4) then 'high_star'
                          when (cast(hotel_grade as int) = 3) then 'middle_star'
                          else 'low_star'
                    end as highlowstar
                from default.dwd_ihotel_flow_app_searchlist_di a
                         left join temp.temp_yiquny_zhang_ihotel_area_region_forever e
                                   on a.country_name = e.country_name
                         left join user_type b
                                   on a.user_id = b.user_id
                         left join hotel_info c
                                   on a.hotel_seq = c.hotel_seq
                         left join product d
                                   on a.dt =d.dt and b.level_desc = d.level_desc and a.hotel_seq = d.hotel_seq and a.checkin_date = d.check_in and a.checkout_date = d.check_out
                         left join mdw_user_type mdw on mdw.user_id = a.user_id
                where a.dt = '${zdt.addDay(-1).format("yyyyMMdd")}' --自定义日期
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
             ,b.newolduser
             ,b.highlowstar
             ,if(no_user_id is null,'正常用户','大单用户') is_big_order_user
        from mdw_order_v3_international a
                 inner join (select  order_info_order_no,newolduser,highlowstar from search_list where order_info_order_no is not null group by 1,2,3) b
                            on a.order_no = b.order_info_order_no
                 left join no_user on a.user_id = no_user.no_user_id
                 left join user_type on a.user_id = user_type.user_id
        where a.dt = '${zdt.addDay(-1).format("yyyyMMdd")}' -- 最新分区
          and (a.province_name in ('台湾', '澳门', '香港') or a.country_name != '中国')
          and a.terminal_channel_type = 'app'
          and (a.first_cancelled_time is null or date(a.first_cancelled_time) > order_date)
          and (a.first_rejected_time is null or date(a.first_rejected_time) > order_date)
          and (a.refund_time is null or date(a.refund_time) > order_date)
          and a.is_valid = '1'
          and substr(cast(a.order_date as string),1,10) = '${zdt.addDay(-1).format("yyyy-MM-dd")}' -- 自定义日期
        --and substr(cast(order_date as string),1,10) between '2025-07-11' and '2025-07-25'
        group by 1,2,3,4,5,6,7,8,9,10,11,12,13
    )
insert overwrite table ihotel_default.dw_ihotel_aa_index_searchlist_di
partition (dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}', type = 'order')
select
    null as datee,
    null as search_request_uid,
    null as hotel_seq,
    null as user_id,
    null as detail_log_id,
    null as detail_device_id,
    null as device_id,
    null as orig_device_id,
    null as rank,
    null as sort_price,
    null as order_info_device_id,
    null as is_display,
    null as render_price,
    null as qpayprice,
    null as cpayprice,
    null as is_query,
    null as is_same_city,
    null as is_filter,
    null as intention,
    null as suggest_type,
    null as country_name,
    null as province_name,
    null as checkin_date,
    null as checkout_date,
    null as log_datetime,
    null as total_hotels,
    null as intention1,
    null as country,
    null as product_range,
    null as new_render_price,
    null as new_sort_price,
    null as order_info_order_no,
    null as click_rank,
    null as order_rank,
    null as medal_type,
    null as show_commission,
    null as sort_v2_price,
    null as rn,
    newolduser,
    highlowstar,
    datee as order_datee,
    orig_device_id as order_orig_device_id,
    user_id as order_user_id,
    order_no as order_order_no,
    hotel_seq as order_hotel_seq,
    room_night as order_room_night,
    checkin_date as order_checkin_date,
    checkout_date as order_checkout_date,
    init_gmv as order_init_gmv,
    order_commission as order_order_commission,
    is_big_order_user
from
    order_detail
