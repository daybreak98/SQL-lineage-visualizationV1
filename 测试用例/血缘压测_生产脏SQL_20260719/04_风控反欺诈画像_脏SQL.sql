/*
 * 风控反欺诈画像生产脏 SQL 血缘压测
 * 说明：注释中的 SELECT、FROM、JOIN 以及分号; 都不是可执行语句。
 * 正则场景：\\d、\\s、\\w、\\u4e00-\\u9fa5，验证反斜杠保真。
 * 输出主题：fraud_risk_portrait
 */
WITH
-- 风控反欺诈画像 / risk_application：历史任务备注 1; 分号仅存在于注释，不能拆分 SQL
risk_src_risk_application AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'risk_application' AS relation_stage,
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
    FROM prod_risk.risk_risk_application_di base
    LATERAL VIEW OUTER explode(
        split(coalesce(base.tag_text, ''), ',')
    ) tag_lv AS tag_name
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / login_event：历史任务备注 2; 分号仅存在于注释，不能拆分 SQL
risk_src_login_event AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'login_event' AS relation_stage,
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
    FROM prod_risk.risk_login_event_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / device_fingerprint：历史任务备注 3; 分号仅存在于注释，不能拆分 SQL
risk_src_device_fingerprint AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'device_fingerprint' AS relation_stage,
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
    FROM prod_risk.risk_device_fingerprint_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / ip_reputation：历史任务备注 4; 分号仅存在于注释，不能拆分 SQL
risk_src_ip_reputation AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'ip_reputation' AS relation_stage,
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
    FROM prod_risk.risk_ip_reputation_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / payment_attempt：历史任务备注 5; 分号仅存在于注释，不能拆分 SQL
risk_src_payment_attempt AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'payment_attempt' AS relation_stage,
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
    FROM prod_risk.risk_payment_attempt_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / rule_hit：历史任务备注 6; 分号仅存在于注释，不能拆分 SQL
risk_src_rule_hit AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'rule_hit' AS relation_stage,
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
    FROM prod_risk.risk_rule_hit_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / case_review：历史任务备注 7; 分号仅存在于注释，不能拆分 SQL
risk_src_case_review AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'case_review' AS relation_stage,
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
    FROM prod_risk.risk_case_review_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / chargeback：历史任务备注 8; 分号仅存在于注释，不能拆分 SQL
risk_src_chargeback AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'chargeback' AS relation_stage,
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
    FROM prod_risk.risk_chargeback_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / account_freeze：历史任务备注 9; 分号仅存在于注释，不能拆分 SQL
risk_src_account_freeze AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'account_freeze' AS relation_stage,
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
    FROM prod_risk.risk_account_freeze_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / risk_rule_dim：历史任务备注 10; 分号仅存在于注释，不能拆分 SQL
risk_src_risk_rule_dim AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'risk_rule_dim' AS relation_stage,
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
    FROM prod_risk.risk_risk_rule_dim_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / device_graph：历史任务备注 11; 分号仅存在于注释，不能拆分 SQL
risk_src_device_graph AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'device_graph' AS relation_stage,
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
    FROM prod_risk.risk_device_graph_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / account_profile：历史任务备注 12; 分号仅存在于注释，不能拆分 SQL
risk_src_account_profile AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'account_profile' AS relation_stage,
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
    FROM prod_risk.risk_account_profile_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / model_score：历史任务备注 13; 分号仅存在于注释，不能拆分 SQL
risk_src_model_score AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'model_score' AS relation_stage,
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
    FROM prod_risk.risk_model_score_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / whitelist_record：历史任务备注 14; 分号仅存在于注释，不能拆分 SQL
risk_src_whitelist_record AS (
    SELECT
        cast(base.case_id AS string) AS entity_id,
        cast(base.account_id AS string) AS user_id,
        cast(base.event_time AS timestamp) AS event_time,
        to_date(base.event_time) AS event_date,
        cast(coalesce(base.amount, 0) AS decimal(20, 4)) AS metric_amount,
        'whitelist_record' AS relation_stage,
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
    FROM prod_risk.risk_whitelist_record_di base
    WHERE base.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(base.is_deleted, 0) = 0
),

-- 风控反欺诈画像 / 多触点集合运算：历史任务备注 15; 分号仅存在于注释，不能拆分 SQL
risk_all_touchpoints AS (
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
    FROM risk_src_risk_application
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
    FROM risk_src_login_event
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
    FROM risk_src_device_fingerprint
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
    FROM risk_src_ip_reputation
),

-- 风控反欺诈画像 / 维度交叉补全：历史任务备注 16; 分号仅存在于注释，不能拆分 SQL
risk_entity_dimensions AS (
    SELECT
        a.entity_id,
        a.user_id,
        coalesce(b.campaign_id, a.campaign_id, 'UNKNOWN') AS resolved_campaign_id,
        coalesce(c.expanded_tag, a.expanded_tag, 'untagged') AS resolved_tag,
        greatest(a.event_date, b.event_date, c.event_date) AS latest_dimension_date,
        concat_ws('|', a.relation_stage, b.relation_stage, c.relation_stage) AS dimension_sources
    FROM risk_src_risk_rule_dim a
    LEFT JOIN risk_src_device_graph b
        ON a.entity_id = b.entity_id
    LEFT JOIN risk_src_account_profile c
        ON a.user_id = c.user_id
    WHERE a.event_date >= date_sub(current_date(), 90)
),

-- 风控反欺诈画像 / 内联子查询归一：历史任务备注 17; 分号仅存在于注释，不能拆分 SQL
risk_inline_activity AS (
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
        FROM risk_src_payment_attempt
        WHERE text_quality_flag <> 'invalid'
    ) inline_base
    LEFT JOIN risk_src_model_score cost
        ON inline_base.campaign_id = cost.campaign_id
       AND inline_base.event_date = cost.event_date
),

-- 风控反欺诈画像 / 标量子查询过滤：历史任务备注 18; 分号仅存在于注释，不能拆分 SQL
risk_eligible_entities AS (
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
    FROM risk_src_rule_hit current_rows
    WHERE current_rows.entity_id IN (
        SELECT
            eligible.entity_id
        FROM risk_src_case_review eligible
        WHERE eligible.event_date >= date_sub(current_date(), 30)
          AND eligible.metric_amount >= 0
    )
),

-- 风控反欺诈画像 / 行为链合并：历史任务备注 19; 分号仅存在于注释，不能拆分 SQL
risk_combined_activity AS (
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
    FROM risk_all_touchpoints
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
    FROM risk_inline_activity
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
    FROM risk_eligible_entities
),

-- 风控反欺诈画像 / 窗口序列计算：历史任务备注 20; 分号仅存在于注释，不能拆分 SQL
risk_sequenced_activity AS (
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
    FROM risk_combined_activity combined
),

-- 风控反欺诈画像 / 实体聚合指标：历史任务备注 21; 分号仅存在于注释，不能拆分 SQL
risk_entity_rollup AS (
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
    FROM risk_sequenced_activity seq
    GROUP BY seq.entity_id
),

-- 风控反欺诈画像 / JSON 画像补全：历史任务备注 22; 分号仅存在于注释，不能拆分 SQL
risk_json_profile AS (
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
    FROM risk_src_whitelist_record profile
    WHERE coalesce(profile.normalized_text, '') <> ''
),

-- 风控反欺诈画像 / 业务结果拼接：历史任务备注 23; 分号仅存在于注释，不能拆分 SQL
risk_metric_enriched AS (
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
    FROM risk_entity_rollup rollup
    LEFT JOIN risk_entity_dimensions dims
        ON rollup.entity_id = dims.entity_id
    LEFT JOIN risk_json_profile json_profile
        ON rollup.entity_id = json_profile.entity_id
),

-- 风控反欺诈画像 / 最终口径及第二个内联查询：历史任务备注 24; 分号仅存在于注释，不能拆分 SQL
risk_final_metrics AS (
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
    FROM risk_metric_enriched enriched
    LEFT JOIN (
        SELECT
            entity_id,
            max(event_time) AS last_quality_event,
            count(1) AS quality_record_count
        FROM risk_src_chargeback
        GROUP BY entity_id
    ) quality
        ON enriched.entity_id = quality.entity_id
    WHERE EXISTS (
        SELECT
            1
        FROM risk_src_account_freeze closure
        WHERE closure.entity_id = enriched.entity_id
    )
)

-- 风控反欺诈画像 / 最终输出：历史任务备注 25; 分号仅存在于注释，不能拆分 SQL
SELECT
    'fraud_risk_portrait' AS output_subject,
    final_rows.entity_id,
    final_rows.user_id,
    final_rows.resolved_campaign_id,
    final_rows.resolved_tag,
    final_rows.first_event_time,
    final_rows.last_event_time,
    final_rows.touchpoint_count,
    final_rows.stage_count,
    final_rows.total_amount AS risk_exposure_amount,
    final_rows.average_amount,
    final_rows.maximum_running_amount,
    final_rows.journey_depth,
    final_rows.json_city,
    final_rows.profile_code,
    final_rows.high_risk_flag,
    final_rows.journey_days,
    final_rows.value_flag,
    final_rows.last_quality_event,
    final_rows.quality_record_count AS reviewed_case_count,
    CASE
        WHEN final_rows.high_risk_flag = 1 THEN 'review'
        WHEN final_rows.touchpoint_count >= 5 THEN 'priority'
        ELSE 'normal'
    END AS attribution_status,
    current_timestamp() AS lineage_test_generated_at
FROM risk_final_metrics final_rows
WHERE final_rows.entity_id IS NOT NULL;
