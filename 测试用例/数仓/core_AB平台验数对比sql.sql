with search_result as
    (
        select a.dt
             ,a.ab_exp_id
             ,a.ab_version
             ,a.ab_rule_version
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
            (
                select * from
                    ihotel_default.dw_ihotel_abtest_index_searchlist_di
                where dt >= '2026-04-14' and dt <= '2026-04-14'
                  and ab_exp_id = '260402_ho_gj_comment_limit' -- 渠道默认APP
                  and user_id_type = 'uid'
                  and is_big_order_user = '正常用户' -- 大单用户,正常用户
                  and type = 'searchlist'
            ) a
        group by 1,2,3,4
    )
   ,order_result as
    (
        select a.dt
             ,a.ab_exp_id
             ,a.ab_version
             ,a.ab_rule_version
             ,sum(a.order_init_gmv) as total_gmv
             ,sum(a.order_room_night) as total_room_night
             ,sum(a.order_init_gmv)/sum(a.order_room_night) as order_adr
             ,sum(a.order_order_commission) as total_order_commission
        from
--             order_detail a
(
    select * from
        ihotel_default.dw_ihotel_abtest_index_searchlist_di
    where dt >= '2026-04-14' and dt <= '2026-04-14'
      and ab_exp_id = '260402_ho_gj_comment_limit' -- 渠道默认APP
      and user_id_type = 'uid'
      and is_big_order_user = '正常用户' -- 大单用户,正常用户
      and type = 'order'

) a
        group by 1,2,3,4
    )


select
    a.dt
     ,a.ab_exp_id
     ,a.ab_version
     ,a.ab_rule_version
     ,cast (b.total_order_commission/a.show_uv as decimal(20,2)) as revenue_per_uv --`单UV收益`
     ,concat(round(a.click_uv/a.show_uv*100,2),'%') as s2d --`S2D`
     ,concat(round(a.order_uv/a.show_uv*100,2),'%') as s2o --`S2O`
     ,concat(round(a.click_pv/a.show_pv*100,2),'%') as click_rate_pv --`搜索点击率_pv`
     ,concat(round(a.order_pv/a.show_pv*100,2),'%') as booking_rate_pv --`搜索预定率_pv`
     ,concat(round(a.no_result_times/a.search_times*100,2),'%')  as no_result_rate --`搜索无结果率`
     ,concat(round(a.no_price_show_item/a.show_item*100,2),'%')  as no_stock_traffic_rate --`无库存流量占比`

     ,concat(round(a.top1_click_pv/a.click_pv*100,2),'%') as top1_click_share_pv --`TOP1点击命中率_PV`
     ,concat(round(a.top1_order_pv/a.order_pv*100,2),'%') as top1_booking_share_pv --`TOP1预定命中率_PV`
     ,concat(round(a.top3_click_pv/a.click_pv*100,2),'%') as top3_click_share_pv --`TOP3点击命中率_PV`
     ,concat(round(a.top3_order_pv/a.order_pv*100,2),'%') as top3_booking_share_pv --`TOP3预定命中率_PV`
     ,concat(round(a.top5_click_pv/a.click_pv*100,2),'%') as top5_click_share_pv --`TOP5点击命中率_PV`
     ,concat(round(a.top5_order_pv/a.order_pv*100,2),'%') as top5_booking_share_pv --`TOP5预定命中率_PV`
     ,concat(round(a.top10_click_pv/a.click_pv*100,2),'%') as top10_click_share_pv --`TOP10点击命中率_PV`
     ,concat(round(a.top10_order_pv/a.order_pv*100,2),'%') as top10_booking_share_pv --`TOP10预定命中率_PV`

     ,cast(b.order_adr as decimal(20,2)) as order_adr --`订单ADR`
     ,cast(a.show_adr as decimal(20,2)) as show_adr --`曝光ADR`
     ,concat(round((a.show_adr/b.order_adr-1)*100,2),'%')  as show_order_adr_gap --`曝光与订单adr_gap`
from
    search_result a
        join order_result b
             on a.dt = b.dt
                 and a.ab_exp_id  = b.ab_exp_id
                 and a.ab_version = b.ab_version
                 and a.ab_rule_version  = b.ab_rule_version
order by dt desc