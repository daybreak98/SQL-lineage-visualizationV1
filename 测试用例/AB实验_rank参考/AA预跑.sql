with search_result as
    (
        select ab_dt
             ,a.ab_group
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
    select ab.dt ab_dt,ab_group,clientcode,a.* from
        (select dt,ab_group,clientcode
         from f_abt.ab_division_hive_result
         where testcode = '260413_ho_gj_upstaost'
           and dt between '2026-04-12' and '2026-04-12'
         group by 1,2,3) ab
            left join (
            select * from
                ihotel_default.dw_ihotel_aa_index_searchlist_di
            where dt = '2026-04-12'
              and type = 'searchlist'
              and newolduser = '新客' --老客,新客
              and highlowstar = 'low_star' --high_star,middle_star,low_star
        ) a
                      on ab.clientcode = a.user_id --user_id,uid
                          and ab.dt = a.dt
    where a.user_id is not null
) a
        group by 1,2
    )
   ,order_result as
    (
        select ab_dt
             ,a.ab_group
             ,sum(a.order_init_gmv) as total_gmv
             ,sum(a.order_room_night) as total_room_night
             ,sum(a.order_init_gmv)/sum(a.order_room_night) as order_adr
             ,sum(a.order_order_commission) as total_order_commission
        from
--             order_detail a
(
    select ab.dt ab_dt,ab_group,clientcode,a.* from
        (select dt,ab_group,clientcode
         from f_abt.ab_division_hive_result
         where testcode = '260413_ho_gj_upstaost'
           and dt between '2026-04-12' and '2026-04-12'
         group by 1,2,3) ab
            left join (
            select * from
                ihotel_default.dw_ihotel_aa_index_searchlist_di
            where dt = '2026-04-12'
              and type = 'order'
              and newolduser = '新客' --老客,新客
              and highlowstar = 'low_star' --high_star,middle_star,low_star
        ) a
                      on ab.clientcode = a.order_user_id--order_user_id,order_uid
                          and ab.dt = a.dt
    where a.order_user_id is not null
) a
        group by 1,2
    )


select
    a.ab_dt
     ,a.ab_group
     ---- S级报表
     , cast(b.total_order_commission / a.show_uv as decimal(20, 2))    as `revenue_per_uv`
     , concat(round(a.click_uv / a.show_uv * 100, 2), '%')             as `s2d`
     , concat(round(a.order_uv / a.show_uv * 100, 2), '%')             as `s2o`
from
    search_result a
        join order_result b
             on a.ab_dt= b.ab_dt
                 and a.ab_group = b.ab_group
order by 1 desc