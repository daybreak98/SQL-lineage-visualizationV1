with
    search_list as
        (
            select a.*
            from ihotel_default.dw_ihotel_abtest_index_searchlist_di a
            where a.dt >= '2026-03-31'
              and dt <= '2026-03-31'
              and type = 'searchlist'
              and user_id_type = 'user_id'
        )

select ab_version
     ,count(distinct a.search_request_uid) as search_times
     ,count(distinct a.orig_device_id) as search_uv
     ,count(case when a.is_display = '1' then a.hotel_seq else null end) as show_item
     ,count(distinct case when a.is_display = '1' then a.search_request_uid else null end) as show_pv
     ,count(case when a.is_display = '1' and abs(a.sort_v2_price- a.qpayprice)/a.qpayprice <= 0.000001 then a.hotel_seq else null end) as sort_right_show_item
     ,count(case when a.is_display = '1' and a.medal_type = '挂牌酒店' then a.hotel_seq else null end) as medal_show_item
     ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null then a.orig_device_id else null end) as show_uv
     ,count(case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.hotel_seq else null end) as click_item
     ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.search_request_uid else null end) as click_pv
     ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 3 then a.search_request_uid else null end) as top3_click_pv
     ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.orig_device_id else null end) as click_uv
     ,count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.order_info_order_no is not null then a.orig_device_id else null end) as order_uv
     ,count(distinct case when a.total_hotels is null or a.total_hotels = 0 then a.search_request_uid else null end) as no_result_times
     ,count(case when a.is_display = '1' and a.new_render_price is null and a.new_sort_price is not null then a.hotel_seq else null end) as no_price_show_item
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
     ,count(distinct case when a.rank<= 3 and a.order_info_order_no is not null then a.search_request_uid else null end) as top3_order_pv
from search_list a
group by 1
