/*
 * 案例 05：流量渠道多触点归因生产脏 SQL
 * 拓扑：Web/App/广告/搜索/社媒触点 UNION -> 身份解析 -> 30 分钟会话化 ->
 *       转化回溯候选 -> 首触/末触/线性/位置四模型分支 -> 模型集合 -> 渠道成本 -> 线下回补。
 * 噪声：中文注释、分号;、\\d、\\s、\\w、\\u4e00-\\u9fa5。
 */
WITH

-- 页面访问：URL、Campaign JSON 与页面标签集中清洗; 注释内 SELECT;
traffic_page_view_clean AS (
    SELECT
        cast(p.page_view_id AS string) AS page_touch_id,
        cast(p.visitor_id AS string) AS page_visitor_id,
        cast(p.anonymous_id AS string) AS page_anonymous_id,
        cast(p.view_time AS timestamp) AS page_touch_at,
        to_date(p.view_time) AS page_touch_date,
        regexp_replace(coalesce(p.raw_text, ''), '\\s+', ' ') AS page_text_normalized,
        regexp_extract(coalesce(p.page_url, ''), 'https?://([^/\\s]+)', 1) AS page_host_name,
        regexp_extract(coalesce(p.page_url, ''), '[?&]utm_source=([^&\\s]+)', 1) AS page_utm_source,
        regexp_extract(coalesce(p.page_url, ''), '[?&]utm_medium=([^&\\s]+)', 1) AS page_utm_medium,
        get_json_object(p.event_payload, '$.campaign.id') AS page_campaign_id,
        get_json_object(p.event_payload, '$.page.category') AS page_category,
        page_tag_lv.tag_name AS page_content_tag,
        CASE
            WHEN coalesce(p.raw_text, '') rlike '[\\u4e00-\\u9fa5]+' THEN 'cn'
            WHEN coalesce(p.raw_text, '') rlike '\\d{4,}' THEN 'numeric'
            ELSE 'ordinary'
        END AS page_text_pattern
    FROM prod_traffic.page_view_event_di p
    LATERAL VIEW OUTER explode(
        split(coalesce(p.tag_text, ''), ',')
    ) page_tag_lv AS tag_name
    WHERE p.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 广告点击：付费媒体触点，点击 ID 用于成本侧核对; 分号;
traffic_ad_click_clean AS (
    SELECT
        cast(a.click_id AS string) AS ad_touch_id,
        cast(a.visitor_id AS string) AS ad_visitor_id,
        cast(a.anonymous_id AS string) AS ad_anonymous_id,
        cast(a.click_time AS timestamp) AS ad_touch_at,
        to_date(a.click_time) AS ad_touch_date,
        cast(a.campaign_id AS string) AS ad_campaign_id,
        cast(a.creative_id AS string) AS ad_creative_id,
        coalesce(a.channel_code, 'paid_unknown') AS ad_channel_code,
        regexp_replace(coalesce(a.landing_url, ''), '[\\r\\n\\t]+', '') AS ad_landing_url_clean,
        regexp_extract(coalesce(a.landing_url, ''), '[?&]gclid=([^&\\s]+)', 1) AS ad_gclid_token,
        CASE WHEN a.is_valid_click = 1 THEN 1 ELSE 0 END AS ad_valid_click_flag
    FROM prod_traffic.ad_click_event_di a
    WHERE a.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- App 打开：移动端入口与 Web 页面形成不同触点分支
traffic_app_open_clean AS (
    SELECT
        cast(o.open_event_id AS string) AS app_touch_id,
        cast(o.visitor_id AS string) AS app_visitor_id,
        cast(o.device_id AS string) AS app_device_id,
        cast(o.open_time AS timestamp) AS app_touch_at,
        to_date(o.open_time) AS app_touch_date,
        coalesce(o.app_version, 'unknown') AS app_version_name,
        coalesce(o.install_source, 'organic') AS app_install_source,
        get_json_object(o.open_context_json, '$.push.campaign_id') AS app_push_campaign_id,
        CASE WHEN o.is_first_open = 1 THEN 'first_open' ELSE 'return_open' END AS app_open_type
    FROM prod_traffic.app_open_event_di o
    WHERE o.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 深链事件：DeepLink 将外部渠道带入 App; 注释中的 MERGE;
traffic_deep_link_clean AS (
    SELECT
        cast(d.deep_link_id AS string) AS deep_link_touch_id,
        cast(d.visitor_id AS string) AS deep_link_visitor_id,
        cast(d.device_id AS string) AS deep_link_device_id,
        cast(d.open_time AS timestamp) AS deep_link_touch_at,
        to_date(d.open_time) AS deep_link_touch_date,
        regexp_extract(coalesce(d.deep_link_url, ''), '^([A-Za-z][A-Za-z0-9+.-]*):', 1) AS deep_link_scheme,
        regexp_extract(coalesce(d.deep_link_url, ''), '[?&]source=([^&\\s]+)', 1) AS deep_link_source,
        regexp_extract(coalesce(d.deep_link_url, ''), '[?&]campaign=([^&\\s]+)', 1) AS deep_link_campaign_id,
        CASE WHEN d.open_result = 'success' THEN 1 ELSE 0 END AS deep_link_success_flag
    FROM prod_traffic.deep_link_event_di d
    WHERE d.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- UTM 触点：服务端日志补齐前端漏报; 大量反斜杠正则
traffic_utm_touch_clean AS (
    SELECT
        cast(u.trace_id AS string) AS utm_touch_id,
        cast(u.visitor_id AS string) AS utm_visitor_id,
        cast(u.trace_time AS timestamp) AS utm_touch_at,
        to_date(u.trace_time) AS utm_touch_date,
        regexp_extract(coalesce(u.query_string, ''), '(?:^|&)utm_source=([^&\\s]+)', 1) AS utm_source_code,
        regexp_extract(coalesce(u.query_string, ''), '(?:^|&)utm_medium=([^&\\s]+)', 1) AS utm_medium_code,
        regexp_extract(coalesce(u.query_string, ''), '(?:^|&)utm_campaign=([^&\\s]+)', 1) AS utm_campaign_code,
        regexp_extract(coalesce(u.query_string, ''), '(?:^|&)utm_content=([^&\\s]+)', 1) AS utm_content_code,
        CASE WHEN coalesce(u.query_string, '') rlike '(^|&)utm_\\w+=' THEN 1 ELSE 0 END AS utm_parameter_present_flag
    FROM prod_traffic.server_utm_trace_di u
    WHERE u.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- Referrer 触点：自然外链和站内跳转通过域名分组; 注释有分号;
traffic_referrer_clean AS (
    SELECT
        cast(r.referrer_event_id AS string) AS referrer_touch_id,
        cast(r.visitor_id AS string) AS referrer_visitor_id,
        cast(r.event_time AS timestamp) AS referrer_touch_at,
        to_date(r.event_time) AS referrer_touch_date,
        regexp_extract(coalesce(r.referrer_url, ''), 'https?://([^/\\s]+)', 1) AS referrer_host_name,
        regexp_extract(coalesce(r.target_url, ''), 'https?://([^/\\s]+)', 1) AS referrer_target_host,
        CASE
            WHEN coalesce(r.referrer_url, '') = '' THEN 'direct'
            WHEN r.referrer_url rlike 'search|baidu|bing|google' THEN 'organic_search'
            WHEN r.referrer_url rlike 'social|wechat|weibo' THEN 'organic_social'
            ELSE 'external_referral'
        END AS referrer_channel_group
    FROM prod_traffic.referrer_event_di r
    WHERE r.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 搜索触点：查询词需归一空白和中文标点; 搜索排名是价值信号
traffic_search_clean AS (
    SELECT
        cast(s.search_event_id AS string) AS search_touch_id,
        cast(s.visitor_id AS string) AS search_visitor_id,
        cast(s.search_time AS timestamp) AS search_touch_at,
        to_date(s.search_time) AS search_touch_date,
        regexp_replace(lower(coalesce(s.query_text, '')), '[\\s，。！？]+', ' ') AS search_query_normalized,
        regexp_extract(coalesce(s.result_url, ''), '/item/(\\d+)', 1) AS search_clicked_item_id,
        cast(coalesce(s.clicked_rank, 0) AS int) AS search_clicked_rank,
        coalesce(s.search_engine, 'internal') AS search_engine_name,
        CASE WHEN coalesce(s.clicked_rank, 0) BETWEEN 1 AND 3 THEN 1 ELSE 0 END AS search_top_rank_click_flag
    FROM prod_traffic.search_touch_event_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 社媒触点：帖子、达人和平台组成内容渠道; 不与广告点击混为一类
traffic_social_clean AS (
    SELECT
        cast(s.social_touch_id AS string) AS social_touch_id,
        cast(s.visitor_id AS string) AS social_visitor_id,
        cast(s.touch_time AS timestamp) AS social_touch_at,
        to_date(s.touch_time) AS social_touch_date,
        coalesce(s.platform_code, 'unknown') AS social_platform_code,
        cast(s.creator_id AS string) AS social_creator_id,
        cast(s.content_id AS string) AS social_content_id,
        regexp_replace(coalesce(s.content_title, ''), '\\s+', ' ') AS social_title_normalized,
        cast(coalesce(s.engagement_score, 0) AS decimal(20, 8)) AS social_engagement_score
    FROM prod_traffic.social_touch_event_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 转化事件：订单、注册、线索统一为转化锚点; 价值字段保留
traffic_conversion_clean AS (
    SELECT
        cast(c.conversion_id AS string) AS conversion_event_id,
        cast(c.visitor_id AS string) AS conversion_visitor_id,
        cast(c.conversion_time AS timestamp) AS conversion_occurred_at,
        to_date(c.conversion_time) AS conversion_date,
        coalesce(c.conversion_type, 'unknown') AS conversion_type_code,
        cast(coalesce(c.conversion_value, 0) AS decimal(20, 4)) AS conversion_value,
        CASE WHEN c.status = 'valid' THEN 1 ELSE 0 END AS valid_conversion_flag,
        get_json_object(c.conversion_json, '$.order.id') AS converted_order_id
    FROM prod_traffic.conversion_event_di c
    WHERE c.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 渠道维表：统一渠道组和付费属性; 注释内分号;
traffic_channel_dimension AS (
    SELECT
        coalesce(ch.channel_code, 'unknown') AS channel_key,
        coalesce(ch.channel_name, '未知渠道') AS channel_name,
        coalesce(ch.channel_group, 'other') AS channel_group_name,
        coalesce(ch.traffic_type, 'unknown') AS channel_traffic_type,
        cast(coalesce(ch.default_lookback_days, 7) AS int) AS channel_lookback_days,
        CASE WHEN ch.is_paid = 1 THEN 1 ELSE 0 END AS paid_channel_flag,
        to_date(ch.updated_at) AS channel_updated_date
    FROM prod_traffic.channel_dimension_df ch
    WHERE ch.is_active = 1
),

-- 媒体成本：渠道、活动、日期构成成本粒度; 后置连接归因结果
traffic_media_cost_clean AS (
    SELECT
        coalesce(mc.channel_code, 'unknown') AS media_cost_channel_code,
        cast(mc.campaign_id AS string) AS media_cost_campaign_id,
        to_date(mc.cost_date) AS media_cost_date,
        cast(coalesce(mc.click_cost, 0) AS decimal(20, 4)) AS media_click_cost,
        cast(coalesce(mc.impression_cost, 0) AS decimal(20, 4)) AS media_impression_cost,
        cast(coalesce(mc.service_fee, 0) AS decimal(20, 4)) AS media_service_fee,
        cast(
            coalesce(mc.click_cost, 0)
            + coalesce(mc.impression_cost, 0)
            + coalesce(mc.service_fee, 0)
            AS decimal(20, 4)
        ) AS media_total_cost
    FROM prod_traffic.media_cost_fact_di mc
    WHERE mc.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 身份映射：匿名 ID 和设备 ID 归并到 visitor; 最新置信映射优先
traffic_identity_map AS (
    SELECT
        cast(im.source_identity AS string) AS identity_source_key,
        coalesce(im.source_type, 'anonymous') AS identity_source_type,
        cast(im.visitor_id AS string) AS mapped_visitor_id,
        cast(coalesce(im.confidence_score, 0) AS decimal(12, 8)) AS mapping_confidence_score,
        cast(im.updated_at AS timestamp) AS mapping_updated_at,
        row_number() OVER (
            PARTITION BY im.source_type, im.source_identity
            ORDER BY im.confidence_score DESC, im.updated_at DESC
        ) AS mapping_recency_rank
    FROM prod_traffic.identity_resolution_df im
    WHERE im.status = 'valid'
),

-- 线下触点：门店扫码、电话和会展回补到多触点旅程; 注释分号;
traffic_offline_touch_clean AS (
    SELECT
        cast(o.offline_touch_id AS string) AS offline_touch_id,
        cast(o.visitor_id AS string) AS offline_visitor_id,
        cast(o.touch_time AS timestamp) AS offline_touch_at,
        to_date(o.touch_time) AS offline_touch_date,
        coalesce(o.offline_channel, 'store') AS offline_channel_code,
        cast(o.campaign_id AS string) AS offline_campaign_id,
        coalesce(o.store_code, 'unknown') AS offline_store_code,
        regexp_replace(coalesce(o.staff_note, ''), '[\\r\\n\\t]+', ' ') AS offline_staff_note_clean,
        cast(coalesce(o.estimated_value, 0) AS decimal(20, 4)) AS offline_estimated_value
    FROM prod_traffic.offline_touch_di o
    WHERE o.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 数字触点集合：每个来源显式映射为统一字段，不使用通用源模板
traffic_digital_touch_union AS (
    SELECT
        page_touch_id AS unified_touch_id,
        page_visitor_id AS supplied_visitor_id,
        page_anonymous_id AS source_identity_id,
        'anonymous' AS source_identity_type,
        page_touch_at AS unified_touch_at,
        page_touch_date AS unified_touch_date,
        coalesce(nullif(page_utm_source, ''), 'website') AS unified_channel_code,
        page_campaign_id AS unified_campaign_id,
        'page_view' AS unified_touch_type,
        cast(1 AS decimal(20, 8)) AS unified_touch_strength,
        page_host_name AS unified_touch_detail
    FROM traffic_page_view_clean
    UNION ALL
    SELECT
        ad_touch_id AS unified_touch_id,
        ad_visitor_id AS supplied_visitor_id,
        ad_anonymous_id AS source_identity_id,
        'anonymous' AS source_identity_type,
        ad_touch_at AS unified_touch_at,
        ad_touch_date AS unified_touch_date,
        ad_channel_code AS unified_channel_code,
        ad_campaign_id AS unified_campaign_id,
        'ad_click' AS unified_touch_type,
        cast(3 AS decimal(20, 8)) AS unified_touch_strength,
        ad_gclid_token AS unified_touch_detail
    FROM traffic_ad_click_clean
    WHERE ad_valid_click_flag = 1
    UNION ALL
    SELECT
        app_touch_id AS unified_touch_id,
        app_visitor_id AS supplied_visitor_id,
        app_device_id AS source_identity_id,
        'device' AS source_identity_type,
        app_touch_at AS unified_touch_at,
        app_touch_date AS unified_touch_date,
        app_install_source AS unified_channel_code,
        app_push_campaign_id AS unified_campaign_id,
        app_open_type AS unified_touch_type,
        cast(2 AS decimal(20, 8)) AS unified_touch_strength,
        app_version_name AS unified_touch_detail
    FROM traffic_app_open_clean
    UNION ALL
    SELECT
        deep_link_touch_id AS unified_touch_id,
        deep_link_visitor_id AS supplied_visitor_id,
        deep_link_device_id AS source_identity_id,
        'device' AS source_identity_type,
        deep_link_touch_at AS unified_touch_at,
        deep_link_touch_date AS unified_touch_date,
        deep_link_source AS unified_channel_code,
        deep_link_campaign_id AS unified_campaign_id,
        'deep_link' AS unified_touch_type,
        cast(2.5 AS decimal(20, 8)) AS unified_touch_strength,
        deep_link_scheme AS unified_touch_detail
    FROM traffic_deep_link_clean
    WHERE deep_link_success_flag = 1
    UNION ALL
    SELECT
        utm_touch_id AS unified_touch_id,
        utm_visitor_id AS supplied_visitor_id,
        cast(NULL AS string) AS source_identity_id,
        'known' AS source_identity_type,
        utm_touch_at AS unified_touch_at,
        utm_touch_date AS unified_touch_date,
        utm_source_code AS unified_channel_code,
        utm_campaign_code AS unified_campaign_id,
        'server_utm' AS unified_touch_type,
        cast(1.5 AS decimal(20, 8)) AS unified_touch_strength,
        utm_medium_code AS unified_touch_detail
    FROM traffic_utm_touch_clean
    WHERE utm_parameter_present_flag = 1
    UNION ALL
    SELECT
        referrer_touch_id AS unified_touch_id,
        referrer_visitor_id AS supplied_visitor_id,
        cast(NULL AS string) AS source_identity_id,
        'known' AS source_identity_type,
        referrer_touch_at AS unified_touch_at,
        referrer_touch_date AS unified_touch_date,
        referrer_channel_group AS unified_channel_code,
        cast(NULL AS string) AS unified_campaign_id,
        'referrer' AS unified_touch_type,
        cast(1 AS decimal(20, 8)) AS unified_touch_strength,
        referrer_host_name AS unified_touch_detail
    FROM traffic_referrer_clean
    UNION ALL
    SELECT
        search_touch_id AS unified_touch_id,
        search_visitor_id AS supplied_visitor_id,
        cast(NULL AS string) AS source_identity_id,
        'known' AS source_identity_type,
        search_touch_at AS unified_touch_at,
        search_touch_date AS unified_touch_date,
        concat('search_', search_engine_name) AS unified_channel_code,
        cast(NULL AS string) AS unified_campaign_id,
        'search' AS unified_touch_type,
        cast(CASE WHEN search_top_rank_click_flag = 1 THEN 2 ELSE 1 END AS decimal(20, 8)) AS unified_touch_strength,
        search_query_normalized AS unified_touch_detail
    FROM traffic_search_clean
    UNION ALL
    SELECT
        social_touch_id AS unified_touch_id,
        social_visitor_id AS supplied_visitor_id,
        cast(NULL AS string) AS source_identity_id,
        'known' AS source_identity_type,
        social_touch_at AS unified_touch_at,
        social_touch_date AS unified_touch_date,
        concat('social_', social_platform_code) AS unified_channel_code,
        cast(NULL AS string) AS unified_campaign_id,
        'social' AS unified_touch_type,
        social_engagement_score AS unified_touch_strength,
        social_content_id AS unified_touch_detail
    FROM traffic_social_clean
),

-- 身份解析：supplied visitor 优先，否则映射匿名或设备 ID
traffic_resolved_touch AS (
    SELECT
        touch.unified_touch_id AS resolved_touch_id,
        coalesce(touch.supplied_visitor_id, identity.mapped_visitor_id, touch.source_identity_id) AS resolved_visitor_id,
        touch.unified_touch_at AS resolved_touch_at,
        touch.unified_touch_date AS resolved_touch_date,
        coalesce(nullif(touch.unified_channel_code, ''), 'direct') AS resolved_channel_code,
        touch.unified_campaign_id AS resolved_campaign_id,
        touch.unified_touch_type AS resolved_touch_type,
        touch.unified_touch_strength AS resolved_touch_strength,
        touch.unified_touch_detail AS resolved_touch_detail,
        CASE
            WHEN touch.supplied_visitor_id IS NOT NULL THEN 'supplied'
            WHEN identity.mapped_visitor_id IS NOT NULL THEN 'mapped'
            ELSE 'unresolved'
        END AS visitor_resolution_method
    FROM traffic_digital_touch_union touch
    LEFT JOIN traffic_identity_map identity
        ON touch.source_identity_id = identity.identity_source_key
       AND touch.source_identity_type = identity.identity_source_type
       AND identity.mapping_recency_rank = 1
),

-- 会话边界：同一 visitor 相邻触点超过 30 分钟则开启新会话
traffic_session_boundary AS (
    SELECT
        resolved.resolved_touch_id AS boundary_touch_id,
        resolved.resolved_visitor_id AS boundary_visitor_id,
        resolved.resolved_touch_at AS boundary_touch_at,
        resolved.resolved_touch_date AS boundary_touch_date,
        resolved.resolved_channel_code AS boundary_channel_code,
        resolved.resolved_campaign_id AS boundary_campaign_id,
        resolved.resolved_touch_type AS boundary_touch_type,
        resolved.resolved_touch_strength AS boundary_touch_strength,
        resolved.resolved_touch_detail AS boundary_touch_detail,
        lag(resolved.resolved_touch_at, 1) OVER (
            PARTITION BY resolved.resolved_visitor_id
            ORDER BY resolved.resolved_touch_at, resolved.resolved_touch_id
        ) AS previous_visitor_touch_at,
        CASE
            WHEN lag(resolved.resolved_touch_at, 1) OVER (
                PARTITION BY resolved.resolved_visitor_id
                ORDER BY resolved.resolved_touch_at, resolved.resolved_touch_id
            ) IS NULL THEN 1
            WHEN unix_timestamp(resolved.resolved_touch_at)
               - unix_timestamp(
                    lag(resolved.resolved_touch_at, 1) OVER (
                        PARTITION BY resolved.resolved_visitor_id
                        ORDER BY resolved.resolved_touch_at, resolved.resolved_touch_id
                    )
                 ) > 1800 THEN 1
            ELSE 0
        END AS new_session_boundary_flag
    FROM traffic_resolved_touch resolved
    WHERE resolved.resolved_visitor_id IS NOT NULL
),

-- 会话化：累计边界数形成 visitor 内稳定 session 编号
traffic_sessionized_touch AS (
    SELECT
        boundary.boundary_touch_id AS session_touch_id,
        boundary.boundary_visitor_id AS session_visitor_id,
        boundary.boundary_touch_at AS session_touch_at,
        boundary.boundary_touch_date AS session_touch_date,
        boundary.boundary_channel_code AS session_channel_code,
        boundary.boundary_campaign_id AS session_campaign_id,
        boundary.boundary_touch_type AS session_touch_type,
        boundary.boundary_touch_strength AS session_touch_strength,
        boundary.boundary_touch_detail AS session_touch_detail,
        sum(boundary.new_session_boundary_flag) OVER (
            PARTITION BY boundary.boundary_visitor_id
            ORDER BY boundary.boundary_touch_at, boundary.boundary_touch_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS visitor_session_number,
        concat(
            boundary.boundary_visitor_id,
            '-',
            cast(
                sum(boundary.new_session_boundary_flag) OVER (
                    PARTITION BY boundary.boundary_visitor_id
                    ORDER BY boundary.boundary_touch_at, boundary.boundary_touch_id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )
                AS string
            )
        ) AS derived_session_id
    FROM traffic_session_boundary boundary
),

-- 旅程触点排序：跨会话保留 visitor 全旅程首末次序
traffic_journey_touch AS (
    SELECT
        sessionized.session_touch_id AS journey_touch_id,
        sessionized.session_visitor_id AS journey_visitor_id,
        sessionized.derived_session_id AS journey_session_id,
        sessionized.session_touch_at AS journey_touch_at,
        sessionized.session_touch_date AS journey_touch_date,
        sessionized.session_channel_code AS journey_channel_code,
        sessionized.session_campaign_id AS journey_campaign_id,
        sessionized.session_touch_type AS journey_touch_type,
        sessionized.session_touch_strength AS journey_touch_strength,
        row_number() OVER (
            PARTITION BY sessionized.session_visitor_id
            ORDER BY sessionized.session_touch_at, sessionized.session_touch_id
        ) AS visitor_journey_sequence,
        count(1) OVER (
            PARTITION BY sessionized.session_visitor_id, sessionized.derived_session_id
        ) AS session_touch_count
    FROM traffic_sessionized_touch sessionized
),

-- 有效转化锚点：内联视图排除无价值测试转化
traffic_conversion_anchor AS (
    SELECT
        valid_conversion.conversion_event_id AS anchor_conversion_id,
        valid_conversion.conversion_visitor_id AS anchor_visitor_id,
        valid_conversion.conversion_occurred_at AS anchor_conversion_at,
        valid_conversion.conversion_date AS anchor_conversion_date,
        valid_conversion.conversion_type_code AS anchor_conversion_type,
        valid_conversion.conversion_value AS anchor_conversion_value,
        valid_conversion.converted_order_id AS anchor_order_id
    FROM (
        SELECT
            conversion_event_id,
            conversion_visitor_id,
            conversion_occurred_at,
            conversion_date,
            conversion_type_code,
            conversion_value,
            converted_order_id
        FROM traffic_conversion_clean
        WHERE valid_conversion_flag = 1
          AND conversion_value >= 0
    ) valid_conversion
),

-- 回溯候选：转化前 14 天所有触点构成模型输入
traffic_attribution_candidate AS (
    SELECT
        conversion.anchor_conversion_id AS candidate_conversion_id,
        conversion.anchor_visitor_id AS candidate_visitor_id,
        conversion.anchor_conversion_at AS candidate_conversion_at,
        conversion.anchor_conversion_type AS candidate_conversion_type,
        conversion.anchor_conversion_value AS candidate_conversion_value,
        touch.journey_touch_id AS candidate_touch_id,
        touch.journey_session_id AS candidate_session_id,
        touch.journey_touch_at AS candidate_touch_at,
        touch.journey_channel_code AS candidate_channel_code,
        touch.journey_campaign_id AS candidate_campaign_id,
        touch.journey_touch_type AS candidate_touch_type,
        touch.journey_touch_strength AS candidate_touch_strength,
        unix_timestamp(conversion.anchor_conversion_at) - unix_timestamp(touch.journey_touch_at) AS candidate_seconds_before_conversion,
        row_number() OVER (
            PARTITION BY conversion.anchor_conversion_id
            ORDER BY touch.journey_touch_at, touch.journey_touch_id
        ) AS candidate_first_touch_rank,
        row_number() OVER (
            PARTITION BY conversion.anchor_conversion_id
            ORDER BY touch.journey_touch_at DESC, touch.journey_touch_id DESC
        ) AS candidate_last_touch_rank,
        count(1) OVER (
            PARTITION BY conversion.anchor_conversion_id
        ) AS candidate_touch_count
    FROM traffic_conversion_anchor conversion
    INNER JOIN traffic_journey_touch touch
        ON conversion.anchor_visitor_id = touch.journey_visitor_id
       AND touch.journey_touch_at <= conversion.anchor_conversion_at
       AND touch.journey_touch_at >= conversion.anchor_conversion_at - INTERVAL 14 DAYS
),

-- 首触模型：最早候选触点获得全部价值
traffic_first_touch_model AS (
    SELECT
        candidate_conversion_id AS model_conversion_id,
        candidate_touch_id AS model_touch_id,
        candidate_channel_code AS model_channel_code,
        candidate_campaign_id AS model_campaign_id,
        candidate_conversion_at AS model_conversion_at,
        candidate_conversion_value AS model_conversion_value,
        cast(1.0 AS decimal(12, 8)) AS model_attribution_weight,
        candidate_conversion_value AS model_attributed_value,
        'first_touch' AS attribution_model_name
    FROM traffic_attribution_candidate
    WHERE candidate_first_touch_rank = 1
),

-- 末触模型：最接近转化的触点获得全部价值
traffic_last_touch_model AS (
    SELECT
        candidate_conversion_id AS model_conversion_id,
        candidate_touch_id AS model_touch_id,
        candidate_channel_code AS model_channel_code,
        candidate_campaign_id AS model_campaign_id,
        candidate_conversion_at AS model_conversion_at,
        candidate_conversion_value AS model_conversion_value,
        cast(1.0 AS decimal(12, 8)) AS model_attribution_weight,
        candidate_conversion_value AS model_attributed_value,
        'last_touch' AS attribution_model_name
    FROM traffic_attribution_candidate
    WHERE candidate_last_touch_rank = 1
),

-- 线性模型：候选触点均分转化价值
traffic_linear_touch_model AS (
    SELECT
        candidate_conversion_id AS model_conversion_id,
        candidate_touch_id AS model_touch_id,
        candidate_channel_code AS model_channel_code,
        candidate_campaign_id AS model_campaign_id,
        candidate_conversion_at AS model_conversion_at,
        candidate_conversion_value AS model_conversion_value,
        cast(1.0 / greatest(candidate_touch_count, 1) AS decimal(12, 8)) AS model_attribution_weight,
        cast(
            candidate_conversion_value / greatest(candidate_touch_count, 1)
            AS decimal(20, 8)
        ) AS model_attributed_value,
        'linear' AS attribution_model_name
    FROM traffic_attribution_candidate
),

-- 位置模型：首末触各 40%，中间触点分配 20%
traffic_position_touch_model AS (
    SELECT
        candidate_conversion_id AS model_conversion_id,
        candidate_touch_id AS model_touch_id,
        candidate_channel_code AS model_channel_code,
        candidate_campaign_id AS model_campaign_id,
        candidate_conversion_at AS model_conversion_at,
        candidate_conversion_value AS model_conversion_value,
        CASE
            WHEN candidate_touch_count = 1 THEN cast(1.0 AS decimal(12, 8))
            WHEN candidate_first_touch_rank = 1 THEN cast(0.4 AS decimal(12, 8))
            WHEN candidate_last_touch_rank = 1 THEN cast(0.4 AS decimal(12, 8))
            ELSE cast(0.2 / greatest(candidate_touch_count - 2, 1) AS decimal(12, 8))
        END AS model_attribution_weight,
        candidate_conversion_value * CASE
            WHEN candidate_touch_count = 1 THEN cast(1.0 AS decimal(12, 8))
            WHEN candidate_first_touch_rank = 1 THEN cast(0.4 AS decimal(12, 8))
            WHEN candidate_last_touch_rank = 1 THEN cast(0.4 AS decimal(12, 8))
            ELSE cast(0.2 / greatest(candidate_touch_count - 2, 1) AS decimal(12, 8))
        END AS model_attributed_value,
        'position' AS attribution_model_name
    FROM traffic_attribution_candidate
),

-- 四模型集合：同一列契约保留 model_name，方便可视化分支血缘
traffic_model_union AS (
    SELECT
        model_conversion_id,
        model_touch_id,
        model_channel_code,
        model_campaign_id,
        model_conversion_at,
        model_conversion_value,
        model_attribution_weight,
        model_attributed_value,
        attribution_model_name
    FROM traffic_first_touch_model
    UNION ALL
    SELECT
        model_conversion_id,
        model_touch_id,
        model_channel_code,
        model_campaign_id,
        model_conversion_at,
        model_conversion_value,
        model_attribution_weight,
        model_attributed_value,
        attribution_model_name
    FROM traffic_last_touch_model
    UNION ALL
    SELECT
        model_conversion_id,
        model_touch_id,
        model_channel_code,
        model_campaign_id,
        model_conversion_at,
        model_conversion_value,
        model_attribution_weight,
        model_attributed_value,
        attribution_model_name
    FROM traffic_linear_touch_model
    UNION ALL
    SELECT
        model_conversion_id,
        model_touch_id,
        model_channel_code,
        model_campaign_id,
        model_conversion_at,
        model_conversion_value,
        model_attribution_weight,
        model_attributed_value,
        attribution_model_name
    FROM traffic_position_touch_model
),

-- 渠道模型聚合：按模型、渠道、日期计算归因转化和价值
traffic_channel_attribution AS (
    SELECT
        models.attribution_model_name AS attribution_model_name,
        coalesce(models.model_channel_code, 'direct') AS attributed_channel_code,
        coalesce(models.model_campaign_id, 'UNKNOWN') AS attributed_campaign_id,
        to_date(models.model_conversion_at) AS attributed_conversion_date,
        count(DISTINCT models.model_conversion_id) AS attributed_conversion_count,
        count(DISTINCT models.model_touch_id) AS contributing_touch_count,
        sum(models.model_attribution_weight) AS attributed_weight_sum,
        sum(models.model_attributed_value) AS attributed_conversion_value,
        avg(models.model_conversion_value) AS average_conversion_value,
        max(models.model_conversion_value) AS maximum_conversion_value
    FROM traffic_model_union models
    GROUP BY
        models.attribution_model_name,
        coalesce(models.model_channel_code, 'direct'),
        coalesce(models.model_campaign_id, 'UNKNOWN'),
        to_date(models.model_conversion_at)
),

-- 成本绩效：归因结果连接渠道维表和媒体成本
traffic_channel_performance AS (
    SELECT
        attribution.attribution_model_name AS performance_model_name,
        attribution.attributed_channel_code AS performance_channel_code,
        channel.channel_name AS performance_channel_name,
        channel.channel_group_name AS performance_channel_group,
        channel.paid_channel_flag AS performance_paid_channel_flag,
        attribution.attributed_campaign_id AS performance_campaign_id,
        attribution.attributed_conversion_date AS performance_date,
        attribution.attributed_conversion_count AS performance_conversion_count,
        attribution.contributing_touch_count AS performance_touch_count,
        attribution.attributed_conversion_value AS performance_attributed_value,
        coalesce(cost.total_daily_media_cost, 0) AS performance_media_cost,
        cast(
            attribution.attributed_conversion_value
            / greatest(coalesce(cost.total_daily_media_cost, 0), 0.0001)
            AS decimal(20, 8)
        ) AS performance_roas
    FROM traffic_channel_attribution attribution
    LEFT JOIN traffic_channel_dimension channel
        ON attribution.attributed_channel_code = channel.channel_key
    LEFT JOIN (
        SELECT
            media_cost_channel_code AS daily_cost_channel_code,
            media_cost_campaign_id AS daily_cost_campaign_id,
            media_cost_date AS daily_cost_date,
            sum(media_total_cost) AS total_daily_media_cost
        FROM traffic_media_cost_clean
        GROUP BY
            media_cost_channel_code,
            media_cost_campaign_id,
            media_cost_date
    ) cost
        ON attribution.attributed_channel_code = cost.daily_cost_channel_code
       AND attribution.attributed_campaign_id = cost.daily_cost_campaign_id
       AND attribution.attributed_conversion_date = cost.daily_cost_date
),

-- 线下触点回补：与数字模型输出形成另一条 UNION 分支
traffic_online_offline_performance AS (
    SELECT
        performance_model_name AS unified_model_name,
        performance_channel_code AS unified_channel_code,
        performance_channel_name AS unified_channel_name,
        performance_channel_group AS unified_channel_group,
        performance_campaign_id AS unified_campaign_id,
        performance_date AS unified_metric_date,
        performance_conversion_count AS unified_conversion_count,
        performance_touch_count AS unified_touch_count,
        performance_attributed_value AS unified_attributed_value,
        performance_media_cost AS unified_media_cost,
        'digital' AS unified_source_type
    FROM traffic_channel_performance
    UNION ALL
    SELECT
        'offline_assist' AS unified_model_name,
        offline_channel_code AS unified_channel_code,
        offline_channel_code AS unified_channel_name,
        'offline' AS unified_channel_group,
        coalesce(offline_campaign_id, 'UNKNOWN') AS unified_campaign_id,
        offline_touch_date AS unified_metric_date,
        cast(0 AS bigint) AS unified_conversion_count,
        cast(1 AS bigint) AS unified_touch_count,
        offline_estimated_value AS unified_attributed_value,
        cast(0 AS decimal(20, 4)) AS unified_media_cost,
        'offline' AS unified_source_type
    FROM traffic_offline_touch_clean
    WHERE offline_visitor_id IS NOT NULL
),

-- 最终渠道指标：线上模型与线下回补按统一粒度汇总
traffic_final_channel_metrics AS (
    SELECT
        unified.unified_model_name AS final_attribution_model,
        unified.unified_channel_code AS final_channel_code,
        max(unified.unified_channel_name) AS final_channel_name,
        max(unified.unified_channel_group) AS final_channel_group,
        unified.unified_campaign_id AS final_campaign_id,
        unified.unified_metric_date AS final_metric_date,
        sum(unified.unified_conversion_count) AS final_conversion_count,
        sum(unified.unified_touch_count) AS final_touch_count,
        sum(unified.unified_attributed_value) AS final_attributed_value,
        sum(unified.unified_media_cost) AS final_media_cost,
        cast(
            sum(unified.unified_attributed_value)
            / greatest(sum(unified.unified_media_cost), 0.0001)
            AS decimal(20, 8)
        ) AS final_blended_roas,
        collect_set(unified.unified_source_type) AS final_source_types
    FROM traffic_online_offline_performance unified
    GROUP BY
        unified.unified_model_name,
        unified.unified_channel_code,
        unified.unified_campaign_id,
        unified.unified_metric_date
)

SELECT
    'traffic_multi_touch' AS lineage_case_name,
    final.final_attribution_model AS attribution_model,
    final.final_channel_code AS channel_code,
    final.final_channel_name AS channel_name,
    final.final_channel_group AS channel_group,
    final.final_campaign_id AS campaign_id,
    final.final_metric_date AS metric_date,
    final.final_conversion_count AS attributed_conversion_count,
    final.final_touch_count AS contributing_touch_count,
    final.final_attributed_value AS attributed_conversion_value,
    final.final_media_cost AS media_cost,
    final.final_blended_roas AS blended_roas,
    final.final_source_types AS attribution_source_types,
    CASE
        WHEN final.final_blended_roas >= 3 THEN 'efficient'
        WHEN final.final_blended_roas >= 1 THEN 'balanced'
        ELSE 'inefficient'
    END AS channel_efficiency_band,
    current_timestamp() AS corpus_evaluated_at
FROM traffic_final_channel_metrics final
WHERE final.final_channel_code IS NOT NULL
  AND EXISTS (
      SELECT
          1
      FROM traffic_channel_dimension active_channel
      WHERE active_channel.channel_key = final.final_channel_code
         OR final.final_channel_group = 'offline'
  );
