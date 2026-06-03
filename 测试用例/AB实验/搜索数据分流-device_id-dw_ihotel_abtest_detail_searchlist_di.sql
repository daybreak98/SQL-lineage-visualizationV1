with search_result as
    (
        select
--             ab_dt
--              ,a.ab_group
            a.dt
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
(
--     select ab.dt ab_dt,ab_group,clientcode,a.* from
--         (select dt,ab_group,clientcode
--          from f_abt.ab_division_hive_result
--          where testcode = '260413_ho_gj_upstaost'
--            and dt between '2026-04-12' and '2026-04-12'
--          group by 1,2,3) ab
--             left join (
    select * from
        ihotel_default.dw_ihotel_aa_index_searchlist_di
    where dt = '2026-04-12'
      and type = 'searchlist'
      and newolduser = '新客' --老客,新客
      and highlowstar = 'low_star' --high_star,middle_star,low_star
) a
        --                       on ab.clientcode = a.user_id --user_id,uid
--                           and ab.dt = a.dt
--     where a.user_id is not null
-- ) a
        group by 1
--                ,2
    )
   ,order_result as
    (
        select
--             ab_dt
--              ,a.ab_group
            a.dt
             ,sum(a.order_init_gmv) as total_gmv
             ,sum(a.order_room_night) as total_room_night
             ,sum(a.order_init_gmv)/sum(a.order_room_night) as order_adr
             ,sum(a.order_order_commission) as total_order_commission
        from
--             order_detail a
(
--     select ab.dt ab_dt,ab_group,clientcode,a.* from
--         (select dt,ab_group,clientcode
--          from f_abt.ab_division_hive_result
--          where testcode = '260413_ho_gj_upstaost'
--            and dt between '2026-04-12' and '2026-04-12'
--          group by 1,2,3) ab
--             left join (
    select * from
        ihotel_default.dw_ihotel_aa_index_searchlist_di
    where dt = '2026-04-12'
      and type = 'order'
      and newolduser = '新客' --老客,新客
      and highlowstar = 'low_star' --high_star,middle_star,low_star
) a
        --                       on ab.clientcode = a.order_user_id--order_user_id,order_uid
--                           and ab.dt = a.dt
--     where a.order_user_id is not null
-- ) a
        group by 1
--                ,2
    )


select
--     a.ab_dt
--      ,a.ab_group
    a.dt
     ---- S级报表
     , cast(b.total_order_commission / a.show_uv as decimal(20, 2))    as `revenue_per_uv`
     , concat(round(a.click_uv / a.show_uv * 100, 2), '%')             as `s2d`
     , concat(round(a.order_uv / a.show_uv * 100, 2), '%')             as `s2o`
     , concat(round(a.click_pv / a.show_pv * 100, 2), '%')             as `click_rate_pv`
     , concat(round(a.order_pv / a.show_pv * 100, 2), '%')             as `booking_rate_pv`
     , concat(round(a.no_result_times / a.search_times * 100, 2), '%') as `no_result_rate`
     , concat(round(a.no_price_show_item / a.show_item * 100, 2), '%') as `no_stock_traffic_rate`

     , concat(round(a.top1_click_pv / a.click_pv * 100, 2), '%')       as `top1_click_share_pv`
     , concat(round(a.top1_order_pv / a.order_num * 100, 2), '%')      as `top1_booking_share_pv`
     , concat(round(a.top3_click_pv / a.click_pv * 100, 2), '%')       as `top3_click_share_pv`
     , concat(round(a.top3_order_pv / a.order_num * 100, 2), '%')      as `top3_booking_share_pv`
     , concat(round(a.top5_click_pv / a.click_pv * 100, 2), '%')       as `top5_click_share_pv`
     , concat(round(a.top5_order_pv / a.order_num * 100, 2), '%')      as `top5_booking_share_pv`
     , concat(round(a.top10_click_pv / a.click_pv * 100, 2), '%')      as `top10_click_share_pv`
     , concat(round(a.top10_order_pv / a.order_num * 100, 2), '%')     as `top10_booking_share_pv`

     , cast(b.order_adr as decimal(20, 2))                             as `order_adr`
     , cast(a.show_adr as decimal(20, 2))                              as `show_adr`
     , concat(round((a.show_adr / b.order_adr - 1) * 100, 2), '%')     as `show_order_adr_gap`

     , b.total_order_commission                                        as total_order_commission
     , a.show_uv                                                       as show_uv
     , a.click_uv                                                      as click_uv
     , a.order_uv                                                      as order_uv
     , a.order_pv                                                      as order_pv
     , a.show_pv                                                       as show_pv
     , a.click_pv                                                      as click_pv
     , a.no_result_times                                               as no_result_times
     , a.search_times                                                  as search_times
     , a.no_price_show_item                                            as no_price_show_item
     , a.show_item                                                     as show_item
     , a.top1_click_pv                                                 as top1_click_pv
     , a.click_pv                                                      as click_pv
     , a.top1_order_pv                                                 as top1_order_pv
     , a.order_num                                                     as order_num
     , a.top3_click_pv                                                 as top3_click_pv
     , a.top3_order_pv                                                 as top3_order_pv
     , a.top5_click_pv                                                 as top5_click_pv
     , a.top5_order_pv                                                 as top5_order_pv
     , a.top10_click_pv                                                as top10_click_pv
     , a.top10_order_pv                                                as top10_order_pv

from
    search_result a
        join order_result b
        --              on a.ab_dt= b.ab_dt
--                  and a.ab_group = b.ab_group
             on a.dt = b.dt
order by 1 desc