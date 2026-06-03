with base_data as (
    select
        dt,
        type,
        ab_version,
        ab_rule_version,
        search_request_uid,
        orig_device_id,
        is_display,
        hotel_seq,
        sort_v2_price,
        qpayprice,
        medal_type,
        detail_log_id,
        rank,
        order_info_order_no,
        total_hotels,
        click_rank,
        order_rank,
        product_range,
        intention1,
        order_init_gmv,
        order_room_night,
        order_order_commission
    from ihotel_default.dw_ihotel_abtest_index_searchlist_di
    where dt >= '${start_day}' and dt <= '${end_day}'
      and ab_exp_id = '${testCode}' -- 渠道默认APP
      and user_id_type = '${user_id_type}'

        <#if country_name?exists>
      and country_name in (
          <#list country_name as item>
          '${item}'<#if item_has_next>,</#if>
          </#list>
      )</#if>

      <#if city_name?exists>
      and city_name in (
          <#list city_name as item>
          '${item}'<#if item_has_next>,</#if>
          </#list>
      )</#if>

      <#if level_desc?exists>
      and level_desc in (
          <#list level_desc as item>
          '${item}'<#if item_has_next>,</#if> -- R1,R1_5,R2,R3,R4
          </#list>
      )</#if>

      <#if is_big_order_user?exists>
      and is_big_order_user = '${is_big_order_user}' -- 大单用户,正常用户
      </#if>

      <#if newolduser?exists>
      and newolduser = '${newolduser}' -- 老客,新客
      </#if>

      <#if highlowstar?exists>
      and highlowstar in (
          <#list highlowstar as item>
          '${item}'<#if item_has_next>,</#if> -- high_star,middle_star,low_star
          </#list>
      )</#if>

      <#if groups?exists>
      and ab_version in (
          <#list groups as item>
          '${item}'<#if item_has_next>,</#if>
          </#list>
      )</#if>
),
     search_src as (
         select *
         from base_data
         where type = 'searchlist'
     ),
     order_src as (
         select *
         from base_data
         where type = 'order'
     ),
     search_result as (
         select
             a.dt,
             a.ab_version,
             a.ab_rule_version,
             count(distinct a.search_request_uid) as search_times,
             count(distinct a.orig_device_id) as search_uv,
             count(case when a.is_display = '1' then a.hotel_seq else null end) as show_item,
             count(distinct case when a.is_display = '1' then a.search_request_uid else null end) as show_pv,
             count(case when a.is_display = '1' and abs(a.sort_v2_price - a.qpayprice) / a.qpayprice <= 0.000001 then a.hotel_seq else null end) as sort_right_show_item,
             count(case when a.is_display = '1' and a.medal_type = '挂牌酒店' then a.hotel_seq else null end) as medal_show_item,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null then a.orig_device_id else null end) as show_uv,
             count(case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.hotel_seq else null end) as click_item,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.search_request_uid else null end) as click_pv,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 1 then a.search_request_uid else null end) as top1_click_pv,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 3 then a.search_request_uid else null end) as top3_click_pv,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 5 then a.search_request_uid else null end) as top5_click_pv,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.rank <= 10 then a.search_request_uid else null end) as top10_click_pv,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null then a.orig_device_id else null end) as click_uv,
             count(distinct case when a.is_display = '1' and a.hotel_seq is not null and a.detail_log_id is not null and a.order_info_order_no is not null then a.orig_device_id else null end) as order_uv,
             count(distinct case when a.total_hotels is null or a.total_hotels = 0 then a.search_request_uid else null end) as no_result_times,
             count(case when a.is_display = 1 and a.qpayprice is null then a.hotel_seq else null end) as no_price_show_item,
             avg(a.click_rank) as avg_click_rank,
             avg(a.order_rank) as avg_order_rank,
             avg(case when a.is_display = '1' and a.hotel_seq is not null then a.qpayprice else null end) as show_adr,
             count(case when a.is_display = '1' and a.product_range = '产品力lose' and a.rank <= 3 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
                 / count(case when a.is_display = '1' and a.product_range != '其他' and a.rank <= 3 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as lose_rate_show_pv_3,
             count(case when a.is_display = '1' and a.product_range = '产品力lose' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
                 / count(case when a.is_display = '1' and a.product_range != '其他' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as lose_rate_show_pv_10,
             count(case when a.is_display = '1' and a.product_range != '其他' and a.rank <= 3 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
                 / count(case when a.is_display = '1' and a.rank <= 3 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as cover_rate_show_pv_3,
             count(case when a.is_display = '1' and a.product_range != '其他' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end)
                 / count(case when a.is_display = '1' and a.rank <= 10 and a.intention1 != '3酒店/集团' then a.hotel_seq else null end) as cover_rate_show_pv_10,
             count(distinct a.order_info_order_no) as order_num,
             count(distinct case when a.order_info_order_no is not null then a.search_request_uid else null end) as order_pv,
             count(distinct case when a.rank <= 1 and a.order_info_order_no is not null then a.search_request_uid else null end) as top1_order_pv,
             count(distinct case when a.rank <= 3 and a.order_info_order_no is not null then a.search_request_uid else null end) as top3_order_pv,
             count(distinct case when a.rank <= 5 and a.order_info_order_no is not null then a.search_request_uid else null end) as top5_order_pv,
             count(distinct case when a.rank <= 10 and a.order_info_order_no is not null then a.search_request_uid else null end) as top10_order_pv
         from search_src a
         group by 1,2,3
     ),
     order_result as (
         select
             a.dt,
             a.ab_version,
             a.ab_rule_version,
             sum(a.order_init_gmv) as total_gmv,
             sum(a.order_room_night) as total_room_night,
             sum(a.order_init_gmv) / sum(a.order_room_night) as order_adr,
             sum(a.order_order_commission) as total_order_commission
         from order_src a
         group by 1,2,3
     )
select
    a.dt as dt,
    a.ab_version as ab_type,
    cast(b.total_order_commission / a.show_uv as decimal(20,2)) as revenue_per_uv, -- 单UV收益
    round(a.click_uv / a.show_uv, 6) as s2d, -- S2D
    round(a.order_uv / a.show_uv, 6) as s2o, -- S2O
    round(a.click_pv / a.show_pv, 6) as click_rate_pv, -- 搜索点击率_pv
    round(a.order_pv / a.show_pv, 6) as booking_rate_pv, -- 搜索预定率_pv
    round(a.no_result_times / a.search_times, 6) as no_result_rate, -- 搜索无结果率
    round(a.no_price_show_item / a.show_item, 6) as no_stock_traffic_rate, -- 无库存流量占比
    round(a.top1_click_pv / a.click_pv, 6) as top1_click_share_pv, -- TOP1点击命中率_PV
    round(a.top1_order_pv / a.order_pv, 6) as top1_booking_share_pv, -- TOP1预定命中率_PV
    round(a.top3_click_pv / a.click_pv, 6) as top3_click_share_pv, -- TOP3点击命中率_PV
    round(a.top3_order_pv / a.order_pv, 6) as top3_booking_share_pv, -- TOP3预定命中率_PV
    round(a.top5_click_pv / a.click_pv, 6) as top5_click_share_pv, -- TOP5点击命中率_PV
    round(a.top5_order_pv / a.order_pv, 6) as top5_booking_share_pv, -- TOP5预定命中率_PV
    round(a.top10_click_pv / a.click_pv, 6) as top10_click_share_pv, -- TOP10点击命中率_PV
    round(a.top10_order_pv / a.order_pv, 6) as top10_booking_share_pv, -- TOP10预定命中率_PV
    cast(b.order_adr as decimal(20,2)) as order_adr, -- 订单ADR
    cast(a.show_adr as decimal(20,2)) as show_adr, -- 曝光ADR
    round((a.show_adr / b.order_adr - 1), 6) as show_order_adr_gap, -- 曝光与订单adr_gap
    b.total_order_commission AS total_order_commission,
    a.show_uv AS show_uv,
    a.click_uv AS click_uv,
    a.order_uv AS order_uv,
    a.order_pv AS order_pv,
    a.show_pv AS show_pv,
    a.click_pv AS click_pv,
    a.no_result_times AS no_result_times,
    a.search_times AS search_times,
    a.no_price_show_item AS no_price_show_item,
    a.show_item AS show_item,
    a.top1_click_pv AS top1_click_pv,
    a.click_pv AS click_pv,
    a.top1_order_pv AS top1_order_pv,
    a.order_num AS order_num,
    a.top3_click_pv AS top3_click_pv,
    a.top3_order_pv AS top3_order_pv,
    a.top5_click_pv AS top5_click_pv,
    a.top5_order_pv AS top5_order_pv,
    a.top10_click_pv AS top10_click_pv,
    a.top10_order_pv AS top10_order_pv
from search_result a
         join order_result b
              on a.dt = b.dt
                  and a.ab_version = b.ab_version
                  and a.ab_rule_version = b.ab_rule_version
order by dt, ab_type
limit 1000