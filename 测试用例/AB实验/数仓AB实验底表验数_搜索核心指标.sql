-- 目的：
-- 1. 使用 AB 规则底表 + AB 搜索明细底表，复刻 AB实验数分.sql 中 search_result 的核心搜索指标；
-- 2. 输出到 dt + ab_version 粒度，便于和数分结果逐个版本对比；
-- 3. 保留规则侧实验值覆盖情况，辅助排查实验命中问题。
--
-- 使用说明：
-- 1. 默认按单日验证，可把 where 条件改成日期区间；
-- 2. 如需只看某个版本，可在 final select 增加 ab_version 过滤。

with rule_base as (
    select
        dt,
        ab_version,
        count(distinct concat_ws('||', user_id_type, ab_exp_value)) as rule_ab_value_cnt
    from ihotel_default.dwd_abtest_rule_info_di
    where dt = '2026-03-31'
    group by 1,2
),
search_base_raw as (
    select
        dt,
        user_id_type,
        ab_version,
        ab_exp_value,
        search_request_uid,
        hotel_seq,
        detail_log_id,
        orig_device_id,
        rank,
        is_display,
        qpayprice,
        total_hotels,
        order_info_order_no,
        click_rank,
        order_rank,
        medal_type,
        product_range,
        intention1,
        sort_v2_price
    from ihotel_default.dw_ihotel_abtest_detail_searchlist_di
    where dt = '2026-03-31'
),
search_base as (
    select distinct
        dt,
        ab_version,
        search_request_uid,
        hotel_seq,
        detail_log_id,
        orig_device_id,
        rank,
        is_display,
        qpayprice,
        total_hotels,
        order_info_order_no,
        click_rank,
        order_rank,
        medal_type,
        product_range,
        intention1,
        sort_v2_price
    from search_base_raw
    where search_request_uid is not null
),
search_hit as (
    select
        dt,
        ab_version,
        count(distinct case when search_request_uid is not null then concat_ws('||', user_id_type, ab_exp_value) end) as hit_ab_value_cnt
    from search_base_raw
    group by 1,2
),
search_result as (
    select
        dt,
        ab_version,
        count(distinct search_request_uid) as search_times,
        count(distinct orig_device_id) as search_uv,
        count(case when is_display = '1' then hotel_seq end) as show_item,
        count(distinct case when is_display = '1' then search_request_uid end) as show_pv,
        count(
            case
                when is_display = '1'
                 and qpayprice is not null
                 and abs(sort_v2_price - qpayprice) / qpayprice <= 0.000001
                then hotel_seq
            end
        ) as sort_right_show_item,
        count(case when is_display = '1' and medal_type = '挂牌酒店' then hotel_seq end) as medal_show_item,
        count(distinct case when is_display = '1' and hotel_seq is not null then orig_device_id end) as show_uv,
        count(case when is_display = '1' and hotel_seq is not null and detail_log_id is not null then hotel_seq end) as click_item,
        count(distinct case when is_display = '1' and hotel_seq is not null and detail_log_id is not null then search_request_uid end) as click_pv,
        count(distinct case when is_display = '1' and hotel_seq is not null and detail_log_id is not null and rank <= 3 then search_request_uid end) as top3_click_pv,
        count(distinct case when is_display = '1' and hotel_seq is not null and detail_log_id is not null then orig_device_id end) as click_uv,
        count(distinct case when is_display = '1' and hotel_seq is not null and detail_log_id is not null and order_info_order_no is not null then orig_device_id end) as order_uv,
        count(distinct case when total_hotels is null or total_hotels = 0 then search_request_uid end) as no_result_times,
        count(case when is_display = '1' and qpayprice is null then hotel_seq end) as no_price_show_item,
        avg(click_rank) as avg_click_rank,
        avg(order_rank) as avg_order_rank,
        avg(case when is_display = '1' and hotel_seq is not null then qpayprice end) as show_adr,
        case
            when count(case when is_display = '1' and product_range != '其他' and rank <= 3 and intention1 != '3酒店/集团' then hotel_seq end) = 0 then null
            else count(case when is_display = '1' and product_range = '产品力lose' and rank <= 3 and intention1 != '3酒店/集团' then hotel_seq end) * 1.0
               / count(case when is_display = '1' and product_range != '其他' and rank <= 3 and intention1 != '3酒店/集团' then hotel_seq end)
        end as lose_rate_show_pv_3,
        case
            when count(case when is_display = '1' and product_range != '其他' and rank <= 10 and intention1 != '3酒店/集团' then hotel_seq end) = 0 then null
            else count(case when is_display = '1' and product_range = '产品力lose' and rank <= 10 and intention1 != '3酒店/集团' then hotel_seq end) * 1.0
               / count(case when is_display = '1' and product_range != '其他' and rank <= 10 and intention1 != '3酒店/集团' then hotel_seq end)
        end as lose_rate_show_pv_10,
        case
            when count(case when is_display = '1' and rank <= 3 and intention1 != '3酒店/集团' then hotel_seq end) = 0 then null
            else count(case when is_display = '1' and product_range != '其他' and rank <= 3 and intention1 != '3酒店/集团' then hotel_seq end) * 1.0
               / count(case when is_display = '1' and rank <= 3 and intention1 != '3酒店/集团' then hotel_seq end)
        end as cover_rate_show_pv_3,
        case
            when count(case when is_display = '1' and rank <= 10 and intention1 != '3酒店/集团' then hotel_seq end) = 0 then null
            else count(case when is_display = '1' and product_range != '其他' and rank <= 10 and intention1 != '3酒店/集团' then hotel_seq end) * 1.0
               / count(case when is_display = '1' and rank <= 10 and intention1 != '3酒店/集团' then hotel_seq end)
        end as cover_rate_show_pv_10,
        count(distinct order_info_order_no) as order_num,
        count(distinct case when order_info_order_no is not null then search_request_uid end) as order_pv,
        count(distinct case when rank <= 3 and order_info_order_no is not null then search_request_uid end) as top3_order_pv
    from search_base
    group by 1,2
)
select
    r.dt,
    r.ab_version,
    r.rule_ab_value_cnt,
    h.hit_ab_value_cnt,
    case
        when r.rule_ab_value_cnt = 0 then null
        else round(h.hit_ab_value_cnt * 100.0 / r.rule_ab_value_cnt, 2)
    end as ab_value_hit_rate,
    s.search_times,
    s.search_uv,
    s.show_item,
    s.show_pv,
    s.sort_right_show_item,
    s.medal_show_item,
    s.show_uv,
    s.click_item,
    s.click_pv,
    s.top3_click_pv,
    s.click_uv,
    s.order_uv,
    s.no_result_times,
    s.no_price_show_item,
    s.avg_click_rank,
    s.avg_order_rank,
    s.show_adr,
    s.lose_rate_show_pv_3,
    s.lose_rate_show_pv_10,
    s.cover_rate_show_pv_3,
    s.cover_rate_show_pv_10,
    s.order_num,
    s.order_pv,
    s.top3_order_pv
from rule_base r
left join search_hit h
    on  r.dt = h.dt
    and r.ab_version = h.ab_version
left join search_result s
    on  r.dt = s.dt
    and r.ab_version = s.ab_version
order by r.dt, r.ab_version
;
