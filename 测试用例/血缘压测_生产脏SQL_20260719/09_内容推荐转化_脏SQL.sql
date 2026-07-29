/*
 * 案例：content_recommendation
 * 模拟生产环境脏 SQL：中文注释、注释分号; 正则 \\d \\s \\w \\u4e00-\\u9fa5。
 * 语句为单一 WITH ... SELECT，包含 28 个独立物理数据源。
 */
WITH

-- 生产源 01：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_01 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        coalesce(tag_name, '') AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_01_di s
    LATERAL VIEW OUTER explode(
        split(coalesce(s.tag_text, ''), ',')
    ) tag_lv AS tag_name
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 02：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_02 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_02_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 03：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_03 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_03_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 04：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_04 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_04_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 05：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_05 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_05_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 06：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_06 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_06_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 07：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_07 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_07_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 08：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_08 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_08_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 09：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_09 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_09_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 10：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_10 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_10_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 11：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_11 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_11_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 12：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_12 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_12_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 13：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_13 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_13_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 14：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_14 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_14_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 15：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_15 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_15_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 16：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_16 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_16_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 17：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_17 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_17_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 18：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_18 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_18_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 19：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_19 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_19_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 20：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_20 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_20_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 21：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_21 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_21_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 22：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_22 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_22_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 23：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_23 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_23_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 24：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_24 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_24_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 25：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_25 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_25_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 26：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_26 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_26_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 27：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_27 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_27_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 生产源 28：中文注释、空值、脏字符与反斜杠正则同时存在
content_recommendation_source_28 AS (
    SELECT
        cast(s.event_id AS string) AS event_id,
        cast(s.entity_id AS string) AS entity_id,
        cast(s.related_id AS string) AS related_id,
        cast(coalesce(s.amount, 0) AS decimal(20, 4)) AS amount,
        coalesce(s.channel_code, 'unknown') AS channel_code,
        to_date(s.event_time) AS event_date,
        cast(s.event_time AS timestamp) AS event_time,
        regexp_replace(coalesce(s.raw_text, ''), '\\s+', ' ') AS clean_text,
        regexp_extract(coalesce(s.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS text_year,
        regexp_extract(coalesce(s.raw_text, ''), '([\\u4e00-\\u9fa5]+)', 1) AS chinese_fragment,
        get_json_object(s.payload, '$.context.scene') AS scene_code,
        get_json_object(s.payload, '$.context.trace_id') AS trace_id,
        'fixed_branch_tag' AS tag_name,
        CASE             WHEN s.status_code rlike '^(ok|success|done)$' THEN 'normal'
            WHEN coalesce(s.raw_text, '') rlike '\\w+@\\w+\\.com' THEN 'dirty_contact'
            ELSE 'other'
        END AS normalized_status,
        row_number() OVER (
            PARTITION BY s.entity_id
            ORDER BY s.event_time DESC, s.event_id DESC
        ) AS latest_rank
    FROM prod_content.event_28_di s
    WHERE s.dt >= date_format(date_sub(current_date(), 120), 'yyyyMMdd')
      AND coalesce(s.is_deleted, 0) = 0
),

-- 二十八路异构事件统一，集合运算用于验证多分支字段对齐
content_recommendation_unioned_events AS (
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_01
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_02
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_03
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_04
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_05
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_06
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_07
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_08
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_09
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_10
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_11
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_12
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_13
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_14
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_15
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_16
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_17
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_18
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_19
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_20
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_21
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_22
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_23
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_24
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_25
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_26
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_27
    UNION ALL
    SELECT event_id, entity_id, related_id, amount, channel_code, event_date, event_time, clean_text, text_year, chinese_fragment, scene_code, trace_id, tag_name, normalized_status, latest_rank
    FROM content_recommendation_source_28
),

-- 指标汇总：聚合、去重、窗口派生字段与数组集合混合
content_recommendation_metric_rollup AS (
    SELECT
        entity_id,
        channel_code,
        event_date,
        sum(amount) AS total_amount,
        count(DISTINCT event_id) AS event_count,
        count(DISTINCT related_id) AS related_count,
        avg(amount) AS average_amount,
        max(amount) AS maximum_amount,
        min(amount) AS minimum_amount,
        max(latest_rank) AS maximum_rank,
        collect_set(scene_code) AS scene_codes,
        collect_set(tag_name) AS tag_names,
        CASE             WHEN sum(amount) >= 100000 THEN 'high'
            WHEN sum(amount) >= 10000 THEN 'medium'
            ELSE 'low'
        END AS amount_band
    FROM content_recommendation_unioned_events
    GROUP BY
        entity_id,
        channel_code,
        event_date
),

-- 内联子查询与维表同时出现，模拟参数表存在重复版本
content_recommendation_enriched_metrics AS (
    SELECT
        m.entity_id,
        m.channel_code,
        m.event_date,
        m.total_amount,
        m.event_count,
        m.related_count,
        m.average_amount,
        m.maximum_amount,
        m.minimum_amount,
        m.maximum_rank,
        m.scene_codes,
        m.tag_names,
        m.amount_band,
        d.dimension_name,
        d.dimension_group,
        cfg.threshold_value,
        cfg.config_version
    FROM content_recommendation_metric_rollup m
    LEFT JOIN prod_content.entity_dimension_df d
        ON m.entity_id = d.entity_id
    LEFT JOIN (
        SELECT
            config_key,
            max(cast(config_value AS decimal(20, 4))) AS threshold_value,
            max(config_version) AS config_version
        FROM prod_content.runtime_config_df
        WHERE enabled_flag = 1
        GROUP BY config_key
    ) cfg
        ON m.channel_code = cfg.config_key
)

-- 最终查询：保留标量子查询、复杂函数和生产过滤噪声
SELECT
    'content_recommendation' AS lineage_case_name,
    e.entity_id,
    e.channel_code,
    e.event_date,
    e.total_amount,
    e.event_count,
    e.related_count,
    e.average_amount,
    e.maximum_amount,
    e.minimum_amount,
    e.maximum_rank,
    e.scene_codes,
    e.tag_names,
    e.amount_band,
    e.dimension_name,
    e.dimension_group,
    coalesce(e.threshold_value, 0) AS threshold_value,
    e.config_version,
    cast(e.total_amount / greatest(e.event_count, 1) AS decimal(20, 6)) AS amount_per_event,
    current_timestamp() AS corpus_evaluated_at
FROM content_recommendation_enriched_metrics e
WHERE e.entity_id IS NOT NULL
  AND EXISTS (
      SELECT
          1
      FROM prod_content.audit_event_df a
      WHERE a.entity_id = e.entity_id
        AND (
            a.audit_status IN ('pass', 'approved')
            OR regexp_replace(coalesce(a.audit_note, ''), '\\s+', ' ') rlike 'manual\\w*'
        )
  );
