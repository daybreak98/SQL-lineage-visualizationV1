/*
 * 流量渠道归因生产脏 SQL 血缘压测
 * 说明：注释中的 SELECT、FROM、JOIN 以及分号; 都不是可执行语句。
 * 正则场景：\\d、\\s、\\w、\\u4e00-\\u9fa5，验证反斜杠保真。
 * 输出主题：traffic_channel_attribution
 */
WITH
-- 流量渠道归因 / page_view：历史任务备注 1; 分号仅存在于注释，不能拆分 SQL
traffic_src_page_view AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'page_view' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '\\s+', ' ') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        tag_lv.tag_name AS expanded_tag,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_page_view_di base
    LATERAL VIEW OUTER explode(
        split(coalesce(base.tag_text, ''), ',')
    ) tag_lv AS tag_name
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / ad_click：历史任务备注 2; 分号仅存在于注释，不能拆分 SQL
traffic_src_ad_click AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'ad_click' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        base.raw_text AS raw_text,
        base.event_payload AS event_payload,
        base.tag_text AS tag_text,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_ad_click_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / app_open：历史任务备注 3; 分号仅存在于注释，不能拆分 SQL
traffic_src_app_open AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'app_open' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_app_open_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / deep_link：历史任务备注 4; 分号仅存在于注释，不能拆分 SQL
traffic_src_deep_link AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'deep_link' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_deep_link_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / utm_touch：历史任务备注 5; 分号仅存在于注释，不能拆分 SQL
traffic_src_utm_touch AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'utm_touch' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_utm_touch_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / referrer_touch：历史任务备注 6; 分号仅存在于注释，不能拆分 SQL
traffic_src_referrer_touch AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'referrer_touch' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_referrer_touch_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / search_touch：历史任务备注 7; 分号仅存在于注释，不能拆分 SQL
traffic_src_search_touch AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'search_touch' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_search_touch_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / social_touch：历史任务备注 8; 分号仅存在于注释，不能拆分 SQL
traffic_src_social_touch AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'social_touch' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_social_touch_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / conversion_event：历史任务备注 9; 分号仅存在于注释，不能拆分 SQL
traffic_src_conversion_event AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'conversion_event' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_conversion_event_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / channel_dim：历史任务备注 10; 分号仅存在于注释，不能拆分 SQL
traffic_src_channel_dim AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'channel_dim' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_channel_dim_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / landing_dim：历史任务备注 11; 分号仅存在于注释，不能拆分 SQL
traffic_src_landing_dim AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'landing_dim' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_landing_dim_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / visitor_segment：历史任务备注 12; 分号仅存在于注释，不能拆分 SQL
traffic_src_visitor_segment AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'visitor_segment' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_visitor_segment_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / media_cost：历史任务备注 13; 分号仅存在于注释，不能拆分 SQL
traffic_src_media_cost AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'media_cost' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_media_cost_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / offline_touch：历史任务备注 14; 分号仅存在于注释，不能拆分 SQL
traffic_src_offline_touch AS (
    SELECT
        cast(base.journey_id AS string) AS entity_id,
        cast(base.visitor_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'offline_touch' AS relation_stage,
        regexp_replace(coalesce(raw_text, ''), '[\\u4e00-\\u9fa5]+', '中文') AS normalized_text,
        regexp_extract(coalesce(raw_text, ''), '(\\w+)', 1) AS extracted_year,
        get_json_object(event_payload, '$.campaign.id') AS campaign_id,
        get_json_object(event_payload, '$.device.os') AS device_os,
        coalesce(tag_text, '') AS expanded_tag,
        CASE
            WHEN coalesce(base.raw_text, '') rlike '\\d{3,}' THEN 'has_number'
            WHEN coalesce(base.raw_text, '') rlike '\\s+' THEN 'has_space'
            ELSE 'plain'
        END AS text_quality_flag,
        from_unixtime(unix_timestamp(base.event_time), 'yyyy-MM-dd HH:mm:ss') AS event_time_text
    FROM prod_traffic.traffic_offline_touch_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 流量渠道归因 / 多触点集合运算：历史任务备注 15; 分号仅存在于注释，不能拆分 SQL
traffic_all_touchpoints AS (
    SELECT
        entity_id,
        user_id,
        event_time,
        event_date,
        metric_amount,
        relation_stage,
        normalized_text,
        campaign_id,
        expanded_tag,
        text_quality_flag
    FROM traffic_src_page_view
    UNION ALL
    SELECT
        entity_id,
        user_id,
        event_time,
        event_date,
        metric_amount,
        relation_stage,
        normalized_text,
        campaign_id,
        expanded_tag,
        text_quality_flag
    FROM traffic_src_ad_click
    UNION ALL
    SELECT
        entity_id,
        user_id,
        event_time,
        event_date,
        metric_amount,
        relation_stage,
        normalized_text,
        campaign_id,
        expanded_tag,
        text_quality_flag
    FROM traffic_src_app_open
    UNION ALL
    SELECT
        entity_id,
        user_id,
        event_time,
        event_date,
        metric_amount,
        relation_stage,
        normalized_text,
        campaign_id,
        expanded_tag,
        text_quality_flag
    FROM traffic_src_deep_link
),

-- 流量渠道归因 / 维度交叉补全：历史任务备注 16; 分号仅存在于注释，不能拆分 SQL
traffic_entity_dimensions AS (
    SELECT
        a.entity_id,
        a.user_id,
        coalesce(b.campaign_id, a.campaign_id, 'UNKNOWN') AS resolved_campaign_id,
        coalesce(c.expanded_tag, a.expanded_tag, 'untagged') AS resolved_tag,
        greatest(a.event_date, b.event_date, c.event_date) AS latest_dimension_date,
        concat_ws('|', a.relation_stage, b.relation_stage, c.relation_stage) AS dimension_sources
    FROM traffic_src_channel_dim a
    LEFT JOIN traffic_src_landing_dim b
        ON a.entity_id = b.entity_id
    LEFT JOIN traffic_src_visitor_segment c
        ON a.user_id = c.user_id
    WHERE a.event_date >= date_sub(current_date(), 90)
),

-- 流量渠道归因 / 内联子查询归一：历史任务备注 17; 分号仅存在于注释，不能拆分 SQL
traffic_inline_activity AS (
    SELECT
        inline_base.entity_id,
        inline_base.user_id,
        inline_base.event_time,
        inline_base.event_date,
        inline_base.metric_amount,
        inline_base.relation_stage,
        inline_base.normalized_text,
        inline_base.campaign_id,
        inline_base.expanded_tag,
        coalesce(cost.metric_amount, 0) AS auxiliary_amount
    FROM (
        SELECT
            entity_id,
            user_id,
            event_time,
            event_date,
            metric_amount,
            relation_stage,
            normalized_text,
            campaign_id,
            expanded_tag
        FROM traffic_src_utm_touch
        WHERE text_quality_flag <> 'invalid'
    ) inline_base
    LEFT JOIN traffic_src_media_cost cost
        ON inline_base.campaign_id = cost.campaign_id
       AND inline_base.event_date = cost.event_date
),

-- 流量渠道归因 / 标量子查询过滤：历史任务备注 18; 分号仅存在于注释，不能拆分 SQL
traffic_eligible_entities AS (
    SELECT
        current_rows.entity_id,
        current_rows.user_id,
        current_rows.event_time,
        current_rows.event_date,
        current_rows.metric_amount,
        current_rows.relation_stage,
        current_rows.normalized_text,
        current_rows.campaign_id,
        current_rows.expanded_tag
    FROM traffic_src_referrer_touch current_rows
    WHERE current_rows.entity_id IN (
        SELECT
            eligible.entity_id
        FROM traffic_src_search_touch eligible
        WHERE eligible.event_date >= date_sub(current_date(), 30)
          AND eligible.metric_amount >= 0
    )
),

-- 流量渠道归因 / 行为链合并：历史任务备注 19; 分号仅存在于注释，不能拆分 SQL
traffic_combined_activity AS (
    SELECT
        entity_id,
        user_id,
        event_time,
        event_date,
        metric_amount,
        relation_stage,
        normalized_text,
        campaign_id,
        expanded_tag
    FROM traffic_all_touchpoints
    UNION ALL
    SELECT
        entity_id,
        user_id,
        event_time,
        event_date,
        metric_amount + auxiliary_amount AS metric_amount,
        relation_stage,
        normalized_text,
        campaign_id,
        expanded_tag
    FROM traffic_inline_activity
    UNION ALL
    SELECT
        entity_id,
        user_id,
        event_time,
        event_date,
        metric_amount,
        relation_stage,
        normalized_text,
        campaign_id,
        expanded_tag
    FROM traffic_eligible_entities
),

-- 流量渠道归因 / 窗口序列计算：历史任务备注 20; 分号仅存在于注释，不能拆分 SQL
traffic_sequenced_activity AS (
    SELECT
        combined.entity_id,
        combined.user_id,
        combined.event_time,
        combined.event_date,
        combined.metric_amount,
        combined.relation_stage,
        combined.normalized_text,
        combined.campaign_id,
        combined.expanded_tag,
        row_number() OVER (
            PARTITION BY combined.entity_id
            ORDER BY combined.event_time, combined.relation_stage
        ) AS event_sequence_number,
        lag(combined.event_time, 1) OVER (
            PARTITION BY combined.entity_id
            ORDER BY combined.event_time, combined.relation_stage
        ) AS previous_event_time,
        sum(combined.metric_amount) OVER (
            PARTITION BY combined.entity_id
            ORDER BY combined.event_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_amount
    FROM traffic_combined_activity combined
),

-- 流量渠道归因 / 实体聚合指标：历史任务备注 21; 分号仅存在于注释，不能拆分 SQL
traffic_entity_rollup AS (
    SELECT
        seq.entity_id,
        max(seq.user_id) AS user_id,
        min(seq.event_time) AS first_event_time,
        max(seq.event_time) AS last_event_time,
        count(1) AS touchpoint_count,
        count(DISTINCT seq.relation_stage) AS stage_count,
        sum(seq.metric_amount) AS total_amount,
        avg(seq.metric_amount) AS average_amount,
        max(seq.running_amount) AS maximum_running_amount,
        collect_set(seq.campaign_id) AS campaign_ids,
        collect_set(seq.expanded_tag) AS tag_names,
        CASE
            WHEN count(DISTINCT seq.relation_stage) >= 4 THEN 'deep'
            WHEN count(DISTINCT seq.relation_stage) >= 2 THEN 'medium'
            ELSE 'shallow'
        END AS journey_depth
    FROM traffic_sequenced_activity seq
    GROUP BY seq.entity_id
),

-- 流量渠道归因 / JSON 画像补全：历史任务备注 22; 分号仅存在于注释，不能拆分 SQL
traffic_json_profile AS (
    SELECT
        profile.entity_id,
        profile.user_id,
        get_json_object(profile.event_payload, '$.campaign.id') AS json_campaign_id,
        get_json_object(profile.event_payload, '$.geo.city') AS json_city,
        regexp_replace(coalesce(profile.raw_text, ''), '\\s+', ' ') AS profile_text,
        regexp_extract(coalesce(profile.raw_text, ''), '([A-Za-z]+)_(\\d+)', 2) AS profile_code,
        CASE
            WHEN get_json_object(profile.event_payload, '$.risk.level') = 'high' THEN 1
            ELSE 0
        END AS high_risk_flag,
        profile.event_date AS profile_event_date
    FROM traffic_src_offline_touch profile
    WHERE coalesce(profile.normalized_text, '') <> ''
),

-- 流量渠道归因 / 业务结果拼接：历史任务备注 23; 分号仅存在于注释，不能拆分 SQL
traffic_metric_enriched AS (
    SELECT
        rollup.entity_id,
        rollup.user_id,
        dims.resolved_campaign_id,
        dims.resolved_tag,
        rollup.first_event_time,
        rollup.last_event_time,
        rollup.touchpoint_count,
        rollup.stage_count,
        rollup.total_amount,
        rollup.average_amount,
        rollup.maximum_running_amount,
        rollup.journey_depth,
        json_profile.json_city,
        json_profile.profile_code,
        json_profile.high_risk_flag,
        datediff(to_date(rollup.last_event_time), to_date(rollup.first_event_time)) AS journey_days,
        if(rollup.total_amount > 0, 'valuable', 'non_value') AS value_flag
    FROM traffic_entity_rollup rollup
    LEFT JOIN traffic_entity_dimensions dims
        ON rollup.entity_id = dims.entity_id
    LEFT JOIN traffic_json_profile json_profile
        ON rollup.entity_id = json_profile.entity_id
),

-- 流量渠道归因 / 最终口径及第二个内联查询：历史任务备注 24; 分号仅存在于注释，不能拆分 SQL
traffic_final_metrics AS (
    SELECT
        enriched.entity_id,
        enriched.user_id,
        enriched.resolved_campaign_id,
        enriched.resolved_tag,
        enriched.first_event_time,
        enriched.last_event_time,
        enriched.touchpoint_count,
        enriched.stage_count,
        enriched.total_amount,
        enriched.average_amount,
        enriched.maximum_running_amount,
        enriched.journey_depth,
        enriched.json_city,
        enriched.profile_code,
        enriched.high_risk_flag,
        enriched.journey_days,
        enriched.value_flag,
        quality.last_quality_event,
        quality.quality_record_count
    FROM traffic_metric_enriched enriched
    LEFT JOIN (
        SELECT
            entity_id,
            max(event_time) AS last_quality_event,
            count(1) AS quality_record_count
        FROM traffic_src_social_touch
        GROUP BY entity_id
    ) quality
        ON enriched.entity_id = quality.entity_id
    WHERE EXISTS (
        SELECT
            1
        FROM traffic_src_conversion_event closure
        WHERE closure.entity_id = enriched.entity_id
    )
)

-- 流量渠道归因 / 最终输出：历史任务备注 25; 分号仅存在于注释，不能拆分 SQL
SELECT
    'traffic_channel_attribution' AS output_subject,
    final_rows.entity_id,
    final_rows.user_id,
    final_rows.resolved_campaign_id,
    final_rows.resolved_tag,
    final_rows.first_event_time,
    final_rows.last_event_time,
    final_rows.touchpoint_count,
    final_rows.stage_count,
    final_rows.total_amount AS attributed_conversion_value,
    final_rows.average_amount,
    final_rows.maximum_running_amount,
    final_rows.journey_depth,
    final_rows.json_city,
    final_rows.profile_code,
    final_rows.high_risk_flag,
    final_rows.journey_days,
    final_rows.value_flag,
    final_rows.last_quality_event,
    final_rows.quality_record_count AS converting_journey_count,
    CASE
        WHEN final_rows.high_risk_flag = 1 THEN 'review'
        WHEN final_rows.touchpoint_count >= 5 THEN 'priority'
        ELSE 'normal'
    END AS attribution_status,
    current_timestamp() AS lineage_test_generated_at
FROM traffic_final_metrics final_rows
WHERE final_rows.entity_id IS NOT NULL;
