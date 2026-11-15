/*
 * 案例 01：营销漏斗归因生产脏 SQL
 * 真实噪声：中文备注、注释内分号; 以及 \\d、\\s、\\w、\\u4e00-\\u9fa5。
 * 拓扑：五类触点汇聚 -> 身份解析 -> 时序排列 -> 转化候选 -> 归因权重 -> 成本与线下回补。
 * 本文件只包含一条 WITH ... SELECT 查询。
 */
WITH

-- 曝光事件：历史口径 v3; 注释分号不代表语句结束
mkt_impression_clean AS (
    SELECT
        cast(i.impression_id AS string) AS impression_event_id,
        cast(i.session_id AS string) AS impression_session_id,
        cast(i.anonymous_id AS string) AS impression_anonymous_id,
        cast(i.event_time AS timestamp) AS impression_time,
        to_date(i.event_time) AS impression_date,
        regexp_replace(coalesce(i.raw_text, ''), '\\s+', ' ') AS impression_text_normalized,
        regexp_extract(coalesce(i.raw_text, ''), '(\\d{4})[-/](\\d{2})', 1) AS impression_text_year,
        get_json_object(i.event_payload, '$.campaign.id') AS impression_campaign_id,
        get_json_object(i.event_payload, '$.creative.id') AS impression_creative_id,
        tag_lv.tag_name AS impression_tag_name,
        CASE
            WHEN coalesce(i.raw_text, '') rlike '[\\u4e00-\\u9fa5]+' THEN 'contains_chinese'
            WHEN coalesce(i.raw_text, '') rlike '\\w+@\\w+' THEN 'contains_email'
            ELSE 'ordinary'
        END AS impression_text_class
    FROM prod_mkt.ad_impression_event_di i
    LATERAL VIEW OUTER explode(
        split(coalesce(i.tag_text, ''), ',')
    ) tag_lv AS tag_name
    WHERE i.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(i.is_robot, 0) = 0
),

-- 点击事件：URL 参数经常脏乱; 保留反斜杠正则用于解析器回归
mkt_click_clean AS (
    SELECT
        cast(c.click_id AS string) AS click_event_id,
        cast(c.session_id AS string) AS click_session_id,
        cast(c.anonymous_id AS string) AS click_anonymous_id,
        cast(c.click_time AS timestamp) AS click_time,
        to_date(c.click_time) AS click_date,
        regexp_replace(coalesce(c.target_url, ''), '[\\r\\n\\t]+', '') AS click_url_compacted,
        regexp_extract(coalesce(c.target_url, ''), '[?&]utm_source=([^&\\s]+)', 1) AS click_utm_source,
        regexp_extract(coalesce(c.target_url, ''), '[?&]utm_campaign=([^&\\s]+)', 1) AS click_utm_campaign,
        get_json_object(c.event_payload, '$.ad.slot') AS click_ad_slot,
        CASE WHEN c.is_valid = 1 THEN 1 ELSE 0 END AS click_valid_flag
    FROM prod_mkt.ad_click_event_di c
    WHERE c.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
      AND coalesce(c.target_url, '') <> ''
),

-- 落地页访问：页面路径可能包含中文; 不在这里复用原始 payload 字段
mkt_landing_clean AS (
    SELECT
        cast(l.page_view_id AS string) AS landing_view_id,
        cast(l.session_id AS string) AS landing_session_id,
        cast(l.anonymous_id AS string) AS landing_anonymous_id,
        cast(l.view_time AS timestamp) AS landing_time,
        to_date(l.view_time) AS landing_date,
        regexp_replace(coalesce(l.page_path, ''), '/+', '/') AS landing_path_normalized,
        regexp_extract(coalesce(l.page_path, ''), '/product/(\\d+)', 1) AS landing_product_id,
        get_json_object(l.context_json, '$.geo.city') AS landing_city,
        cast(coalesce(l.stay_seconds, 0) AS bigint) AS landing_stay_seconds,
        if(coalesce(l.stay_seconds, 0) >= 10, 1, 0) AS landing_engaged_flag
    FROM prod_mkt.landing_page_view_di l
    WHERE l.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
),

/* 线索提交：CRM 历史备注中常有 SELECT、JOIN 和分号;
   这些内容都只属于注释，不应形成第二条 SQL。 */
mkt_lead_clean AS (
    SELECT
        cast(le.lead_id AS string) AS lead_event_id,
        cast(le.session_id AS string) AS lead_session_id,
        cast(le.customer_id AS string) AS lead_customer_id,
        cast(le.submit_time AS timestamp) AS lead_submit_time,
        to_date(le.submit_time) AS lead_submit_date,
        regexp_replace(coalesce(le.phone_text, ''), '[^0-9]+', '') AS lead_phone_digits,
        regexp_extract(coalesce(le.email_text, ''), '([\\w.+-]+)@([\\w.-]+)', 2) AS lead_email_domain,
        get_json_object(le.form_json, '$.intent.product') AS lead_intent_product,
        CASE WHEN le.lead_status IN ('valid', 'converted') THEN 1 ELSE 0 END AS lead_valid_flag,
        cast(coalesce(le.lead_score, 0) AS decimal(12, 4)) AS lead_quality_score
    FROM prod_mkt.lead_submit_event_di le
    WHERE le.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
),

-- 加购行为：同一会话可能重复加购; 数量需保留而不是机械透传
mkt_cart_clean AS (
    SELECT
        cast(a.cart_event_id AS string) AS cart_event_id,
        cast(a.session_id AS string) AS cart_session_id,
        cast(a.customer_id AS string) AS cart_customer_id,
        cast(a.add_time AS timestamp) AS cart_add_time,
        to_date(a.add_time) AS cart_add_date,
        cast(a.sku_id AS string) AS cart_sku_id,
        cast(greatest(coalesce(a.quantity, 0), 0) AS bigint) AS cart_quantity,
        cast(coalesce(a.unit_price, 0) AS decimal(20, 4)) AS cart_unit_price,
        cast(greatest(coalesce(a.quantity, 0), 0) * coalesce(a.unit_price, 0) AS decimal(20, 4)) AS cart_value,
        CASE WHEN a.source_code rlike '^(ad|seo|social)_\\w+$' THEN a.source_code ELSE 'unknown' END AS cart_source_code
    FROM prod_mkt.cart_add_event_di a
    WHERE a.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
),

-- 订单事实：支付成功才是线上转化; 退款在独立分支冲减
mkt_order_clean AS (
    SELECT
        cast(o.order_id AS string) AS conversion_order_id,
        cast(o.session_id AS string) AS conversion_session_id,
        cast(o.customer_id AS string) AS conversion_customer_id,
        cast(o.pay_time AS timestamp) AS conversion_time,
        to_date(o.pay_time) AS conversion_date,
        cast(coalesce(o.paid_amount, 0) AS decimal(20, 4)) AS conversion_paid_amount,
        cast(coalesce(o.discount_amount, 0) AS decimal(20, 4)) AS conversion_discount_amount,
        get_json_object(o.order_ext_json, '$.first_order') AS conversion_first_order_text,
        CASE WHEN o.order_status IN ('paid', 'fulfilled') THEN 1 ELSE 0 END AS conversion_success_flag,
        from_unixtime(unix_timestamp(o.pay_time), 'yyyy-MM-dd HH:mm:ss') AS conversion_time_text
    FROM prod_mkt.order_payment_fact_di o
    WHERE o.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
),

-- 退款事实：部分退款和全额退款都必须进入净收入; 不与订单源混写
mkt_refund_clean AS (
    SELECT
        cast(r.refund_id AS string) AS refund_event_id,
        cast(r.order_id AS string) AS refund_order_id,
        cast(r.customer_id AS string) AS refund_customer_id,
        cast(r.refund_time AS timestamp) AS refund_time,
        to_date(r.refund_time) AS refund_date,
        cast(coalesce(r.refund_amount, 0) AS decimal(20, 4)) AS refund_amount,
        regexp_replace(coalesce(r.reason_text, ''), '\\s+', ' ') AS refund_reason_normalized,
        regexp_extract(coalesce(r.reason_text, ''), '(质量|物流|价格|其他)', 1) AS refund_reason_group,
        CASE WHEN r.refund_status = 'success' THEN 1 ELSE 0 END AS refund_success_flag
    FROM prod_mkt.order_refund_fact_di r
    WHERE r.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
),

-- 活动维表：活动有效期决定触点是否可归因; 注释里有分号;
mkt_campaign_dimension AS (
    SELECT
        cast(cd.campaign_id AS string) AS campaign_key,
        coalesce(cd.campaign_name, '未命名活动') AS campaign_name,
        cast(cd.start_time AS timestamp) AS campaign_start_time,
        cast(cd.end_time AS timestamp) AS campaign_end_time,
        coalesce(cd.channel_code, 'unknown') AS campaign_channel_code,
        coalesce(cd.attribution_model, 'position') AS configured_attribution_model,
        cast(coalesce(cd.lookback_days, 7) AS int) AS configured_lookback_days,
        CASE WHEN cd.status = 'active' THEN 1 ELSE 0 END AS campaign_active_flag
    FROM prod_mkt.campaign_dimension_df cd
    WHERE cd.snapshot_date = date_format(date_sub(current_date(), 1), 'yyyyMMdd')
),

-- 创意维表：仅输出创意业务属性; 不复制事件原始文本字段
mkt_creative_dimension AS (
    SELECT
        cast(cr.creative_id AS string) AS creative_key,
        coalesce(cr.creative_name, '未命名创意') AS creative_name,
        coalesce(cr.creative_type, 'unknown') AS creative_type,
        coalesce(cr.material_format, 'unknown') AS material_format,
        regexp_extract(coalesce(cr.material_url, ''), '\\.([A-Za-z0-9]+)(?:\\?|$)', 1) AS material_extension,
        get_json_object(cr.audit_json, '$.status') AS creative_audit_status,
        to_date(cr.updated_at) AS creative_updated_date
    FROM prod_mkt.creative_dimension_df cr
    WHERE cr.is_deleted = 0
),

-- 渠道成本：按活动、日期聚合前先规范币种; 成本链与触点链后置汇合
mkt_channel_cost_clean AS (
    SELECT
        cast(cc.campaign_id AS string) AS cost_campaign_id,
        to_date(cc.cost_date) AS cost_business_date,
        coalesce(cc.channel_code, 'unknown') AS cost_channel_code,
        cast(coalesce(cc.impression_cost, 0) AS decimal(20, 4)) AS impression_cost_amount,
        cast(coalesce(cc.click_cost, 0) AS decimal(20, 4)) AS click_cost_amount,
        cast(coalesce(cc.service_fee, 0) AS decimal(20, 4)) AS service_fee_amount,
        cast(coalesce(cc.impression_cost, 0) + coalesce(cc.click_cost, 0) + coalesce(cc.service_fee, 0) AS decimal(20, 4)) AS total_media_cost,
        upper(coalesce(cc.currency_code, 'CNY')) AS cost_currency_code
    FROM prod_mkt.channel_cost_fact_di cc
    WHERE cc.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
),

-- 身份映射：匿名 ID 到客户 ID; 只选择可用映射
mkt_identity_map AS (
    SELECT
        cast(im.anonymous_id AS string) AS identity_anonymous_id,
        cast(im.customer_id AS string) AS identity_customer_id,
        cast(im.first_seen_time AS timestamp) AS identity_first_seen_time,
        cast(im.last_seen_time AS timestamp) AS identity_last_seen_time,
        coalesce(im.mapping_source, 'unknown') AS identity_mapping_source,
        row_number() OVER (
            PARTITION BY im.anonymous_id
            ORDER BY im.confidence_score DESC, im.last_seen_time DESC
        ) AS identity_confidence_rank
    FROM prod_mkt.anonymous_customer_map_df im
    WHERE coalesce(im.confidence_score, 0) > 0
),

-- 线下转化：用于回补门店签约; 注释中的 INSERT; 不执行
mkt_offline_conversion_clean AS (
    SELECT
        cast(oc.contract_id AS string) AS offline_contract_id,
        cast(oc.customer_id AS string) AS offline_customer_id,
        cast(oc.campaign_id AS string) AS offline_campaign_id,
        cast(oc.sign_time AS timestamp) AS offline_sign_time,
        to_date(oc.sign_time) AS offline_sign_date,
        cast(coalesce(oc.contract_amount, 0) AS decimal(20, 4)) AS offline_contract_amount,
        coalesce(oc.store_code, 'unknown') AS offline_store_code,
        regexp_replace(coalesce(oc.sales_note, ''), '[\\r\\n\\t]+', ' ') AS offline_sales_note_clean,
        CASE WHEN oc.contract_status = 'effective' THEN 1 ELSE 0 END AS offline_effective_flag
    FROM prod_mkt.offline_contract_fact_di oc
    WHERE oc.dt >= date_format(date_sub(current_date(), 35), 'yyyyMMdd')
),

-- 五类线上触点集合：字段语义在每个分支显式映射; 不使用 SELECT *
mkt_session_touchpoints AS (
    SELECT
        impression_event_id AS touch_id,
        impression_session_id AS session_id,
        impression_anonymous_id AS anonymous_id,
        cast(NULL AS string) AS known_customer_id,
        impression_time AS touch_time,
        impression_date AS touch_date,
        'impression' AS touch_type,
        impression_campaign_id AS campaign_id,
        impression_creative_id AS creative_id,
        cast(0 AS decimal(20, 4)) AS touch_value,
        impression_tag_name AS touch_detail
    FROM mkt_impression_clean
    UNION ALL
    SELECT
        click_event_id AS touch_id,
        click_session_id AS session_id,
        click_anonymous_id AS anonymous_id,
        cast(NULL AS string) AS known_customer_id,
        click_time AS touch_time,
        click_date AS touch_date,
        'click' AS touch_type,
        nullif(click_utm_campaign, '') AS campaign_id,
        cast(NULL AS string) AS creative_id,
        cast(0 AS decimal(20, 4)) AS touch_value,
        click_utm_source AS touch_detail
    FROM mkt_click_clean
    WHERE click_valid_flag = 1
    UNION ALL
    SELECT
        landing_view_id AS touch_id,
        landing_session_id AS session_id,
        landing_anonymous_id AS anonymous_id,
        cast(NULL AS string) AS known_customer_id,
        landing_time AS touch_time,
        landing_date AS touch_date,
        'landing' AS touch_type,
        cast(NULL AS string) AS campaign_id,
        cast(NULL AS string) AS creative_id,
        cast(landing_stay_seconds AS decimal(20, 4)) AS touch_value,
        landing_path_normalized AS touch_detail
    FROM mkt_landing_clean
    WHERE landing_engaged_flag = 1
    UNION ALL
    SELECT
        lead_event_id AS touch_id,
        lead_session_id AS session_id,
        cast(NULL AS string) AS anonymous_id,
        lead_customer_id AS known_customer_id,
        lead_submit_time AS touch_time,
        lead_submit_date AS touch_date,
        'lead' AS touch_type,
        cast(NULL AS string) AS campaign_id,
        cast(NULL AS string) AS creative_id,
        cast(lead_quality_score AS decimal(20, 4)) AS touch_value,
        lead_intent_product AS touch_detail
    FROM mkt_lead_clean
    WHERE lead_valid_flag = 1
    UNION ALL
    SELECT
        cart_event_id AS touch_id,
        cart_session_id AS session_id,
        cast(NULL AS string) AS anonymous_id,
        cart_customer_id AS known_customer_id,
        cart_add_time AS touch_time,
        cart_add_date AS touch_date,
        'cart' AS touch_type,
        cast(NULL AS string) AS campaign_id,
        cast(NULL AS string) AS creative_id,
        cart_value AS touch_value,
        cart_sku_id AS touch_detail
    FROM mkt_cart_clean
),

-- 身份解析分支：匿名触点通过最高置信映射补全客户
mkt_resolved_touchpoints AS (
    SELECT
        t.touch_id AS resolved_touch_id,
        t.session_id AS resolved_session_id,
        coalesce(t.known_customer_id, im.identity_customer_id, t.anonymous_id) AS resolved_customer_id,
        t.touch_time AS resolved_touch_time,
        t.touch_date AS resolved_touch_date,
        t.touch_type AS resolved_touch_type,
        t.campaign_id AS resolved_campaign_id,
        t.creative_id AS resolved_creative_id,
        t.touch_value AS resolved_touch_value,
        t.touch_detail AS resolved_touch_detail,
        CASE
            WHEN t.known_customer_id IS NOT NULL THEN 'known'
            WHEN im.identity_customer_id IS NOT NULL THEN 'mapped'
            ELSE 'anonymous'
        END AS identity_resolution_type
    FROM mkt_session_touchpoints t
    LEFT JOIN mkt_identity_map im
        ON t.anonymous_id = im.identity_anonymous_id
       AND im.identity_confidence_rank = 1
),

-- 触点时序：保留首触、末触、前序时间和累计触点价值
mkt_ordered_touchpoints AS (
    SELECT
        rt.resolved_touch_id AS ordered_touch_id,
        rt.resolved_session_id AS ordered_session_id,
        rt.resolved_customer_id AS ordered_customer_id,
        rt.resolved_touch_time AS ordered_touch_time,
        rt.resolved_touch_date AS ordered_touch_date,
        rt.resolved_touch_type AS ordered_touch_type,
        rt.resolved_campaign_id AS ordered_campaign_id,
        rt.resolved_creative_id AS ordered_creative_id,
        rt.resolved_touch_value AS ordered_touch_value,
        rt.resolved_touch_detail AS ordered_touch_detail,
        row_number() OVER (
            PARTITION BY rt.resolved_customer_id
            ORDER BY rt.resolved_touch_time, rt.resolved_touch_id
        ) AS customer_touch_sequence,
        lag(rt.resolved_touch_time, 1) OVER (
            PARTITION BY rt.resolved_customer_id
            ORDER BY rt.resolved_touch_time, rt.resolved_touch_id
        ) AS previous_customer_touch_time,
        sum(rt.resolved_touch_value) OVER (
            PARTITION BY rt.resolved_customer_id
            ORDER BY rt.resolved_touch_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_touch_value
    FROM mkt_resolved_touchpoints rt
),

-- 订单净转化：退款先按订单汇总再冲减，形成可归因价值
mkt_net_conversions AS (
    SELECT
        o.conversion_order_id AS attributed_order_id,
        o.conversion_session_id AS attributed_session_id,
        o.conversion_customer_id AS attributed_customer_id,
        o.conversion_time AS attributed_conversion_time,
        o.conversion_date AS attributed_conversion_date,
        o.conversion_paid_amount AS gross_conversion_amount,
        coalesce(r.successful_refund_amount, 0) AS successful_refund_amount,
        cast(o.conversion_paid_amount - coalesce(r.successful_refund_amount, 0) AS decimal(20, 4)) AS net_conversion_amount,
        o.conversion_first_order_text AS first_order_indicator,
        datediff(current_date(), o.conversion_date) AS conversion_age_days
    FROM mkt_order_clean o
    LEFT JOIN (
        SELECT
            refund_order_id AS grouped_refund_order_id,
            sum(CASE WHEN refund_success_flag = 1 THEN refund_amount ELSE 0 END) AS successful_refund_amount,
            max(refund_time) AS latest_refund_time,
            count(1) AS refund_record_count
        FROM mkt_refund_clean
        GROUP BY refund_order_id
    ) r
        ON o.conversion_order_id = r.grouped_refund_order_id
    WHERE o.conversion_success_flag = 1
),

-- 候选归因：内联转化范围与触点按客户、会话及回溯窗口关联
mkt_attribution_candidates AS (
    SELECT
        scope.attributed_order_id AS candidate_order_id,
        scope.attributed_customer_id AS candidate_customer_id,
        scope.attributed_conversion_time AS candidate_conversion_time,
        scope.net_conversion_amount AS candidate_conversion_amount,
        ot.ordered_touch_id AS candidate_touch_id,
        ot.ordered_touch_time AS candidate_touch_time,
        ot.ordered_touch_type AS candidate_touch_type,
        ot.ordered_campaign_id AS candidate_campaign_id,
        ot.ordered_creative_id AS candidate_creative_id,
        ot.ordered_touch_detail AS candidate_touch_detail,
        unix_timestamp(scope.attributed_conversion_time) - unix_timestamp(ot.ordered_touch_time) AS seconds_before_conversion
    FROM (
        SELECT
            attributed_order_id,
            attributed_session_id,
            attributed_customer_id,
            attributed_conversion_time,
            attributed_conversion_date,
            net_conversion_amount
        FROM mkt_net_conversions
        WHERE net_conversion_amount > 0
    ) scope
    INNER JOIN mkt_ordered_touchpoints ot
        ON scope.attributed_customer_id = ot.ordered_customer_id
       AND ot.ordered_touch_time <= scope.attributed_conversion_time
       AND ot.ordered_touch_time >= scope.attributed_conversion_time - INTERVAL 7 DAYS
    WHERE scope.attributed_session_id = ot.ordered_session_id
       OR ot.ordered_touch_type IN ('impression', 'click')
),

-- 权重计算：位置模型首末触各 40%，中间触点均分 20%
mkt_weighted_attribution AS (
    SELECT
        c.candidate_order_id AS weighted_order_id,
        c.candidate_customer_id AS weighted_customer_id,
        c.candidate_touch_id AS weighted_touch_id,
        c.candidate_touch_time AS weighted_touch_time,
        c.candidate_touch_type AS weighted_touch_type,
        c.candidate_campaign_id AS weighted_campaign_id,
        c.candidate_creative_id AS weighted_creative_id,
        c.candidate_conversion_amount AS weighted_conversion_amount,
        count(1) OVER (
            PARTITION BY c.candidate_order_id
        ) AS order_candidate_count,
        row_number() OVER (
            PARTITION BY c.candidate_order_id
            ORDER BY c.candidate_touch_time, c.candidate_touch_id
        ) AS first_touch_rank,
        row_number() OVER (
            PARTITION BY c.candidate_order_id
            ORDER BY c.candidate_touch_time DESC, c.candidate_touch_id DESC
        ) AS last_touch_rank,
        CASE
            WHEN count(1) OVER (PARTITION BY c.candidate_order_id) = 1 THEN cast(1.0 AS decimal(12, 8))
            WHEN row_number() OVER (
                PARTITION BY c.candidate_order_id
                ORDER BY c.candidate_touch_time, c.candidate_touch_id
            ) = 1 THEN cast(0.4 AS decimal(12, 8))
            WHEN row_number() OVER (
                PARTITION BY c.candidate_order_id
                ORDER BY c.candidate_touch_time DESC, c.candidate_touch_id DESC
            ) = 1 THEN cast(0.4 AS decimal(12, 8))
            ELSE cast(0.2 / greatest(count(1) OVER (PARTITION BY c.candidate_order_id) - 2, 1) AS decimal(12, 8))
        END AS position_attribution_weight
    FROM mkt_attribution_candidates c
),

-- 活动归因汇总：订单价值乘以权重，形成线上归因收入
mkt_campaign_attribution_rollup AS (
    SELECT
        coalesce(wa.weighted_campaign_id, 'UNKNOWN') AS rollup_campaign_id,
        to_date(wa.weighted_touch_time) AS rollup_touch_date,
        count(DISTINCT wa.weighted_order_id) AS attributed_order_count,
        count(DISTINCT wa.weighted_customer_id) AS attributed_customer_count,
        count(DISTINCT wa.weighted_touch_id) AS attributed_touch_count,
        sum(wa.position_attribution_weight) AS attribution_weight_sum,
        sum(wa.weighted_conversion_amount * wa.position_attribution_weight) AS online_attributed_revenue,
        avg(wa.order_candidate_count) AS average_candidate_touch_count,
        max(wa.weighted_conversion_amount) AS maximum_conversion_amount,
        collect_set(wa.weighted_touch_type) AS contributing_touch_types
    FROM mkt_weighted_attribution wa
    GROUP BY
        coalesce(wa.weighted_campaign_id, 'UNKNOWN'),
        to_date(wa.weighted_touch_time)
),

-- 成本汇总后连接活动：成本分支与归因分支在此首次汇合
mkt_campaign_cost_performance AS (
    SELECT
        roll.rollup_campaign_id AS performance_campaign_id,
        roll.rollup_touch_date AS performance_date,
        roll.attributed_order_count AS performance_order_count,
        roll.attributed_customer_count AS performance_customer_count,
        roll.attributed_touch_count AS performance_touch_count,
        roll.online_attributed_revenue AS performance_online_revenue,
        coalesce(cost.daily_media_cost, 0) AS performance_media_cost,
        cast(
            roll.online_attributed_revenue / greatest(coalesce(cost.daily_media_cost, 0), 0.0001)
            AS decimal(20, 8)
        ) AS performance_roas,
        roll.contributing_touch_types AS performance_touch_types
    FROM mkt_campaign_attribution_rollup roll
    LEFT JOIN (
        SELECT
            cost_campaign_id AS daily_cost_campaign_id,
            cost_business_date AS daily_cost_date,
            sum(total_media_cost) AS daily_media_cost,
            collect_set(cost_channel_code) AS daily_cost_channels
        FROM mkt_channel_cost_clean
        GROUP BY cost_campaign_id, cost_business_date
    ) cost
        ON roll.rollup_campaign_id = cost.daily_cost_campaign_id
       AND roll.rollup_touch_date = cost.daily_cost_date
),

-- 线上与线下价值采用集合运算汇总，但保留来源类型
mkt_online_offline_value AS (
    SELECT
        performance_campaign_id AS unified_campaign_id,
        performance_date AS unified_value_date,
        performance_online_revenue AS unified_attributed_value,
        performance_media_cost AS unified_media_cost,
        performance_order_count AS unified_conversion_count,
        'online' AS unified_conversion_source
    FROM mkt_campaign_cost_performance
    UNION ALL
    SELECT
        offline_campaign_id AS unified_campaign_id,
        offline_sign_date AS unified_value_date,
        offline_contract_amount AS unified_attributed_value,
        cast(0 AS decimal(20, 4)) AS unified_media_cost,
        cast(1 AS bigint) AS unified_conversion_count,
        'offline' AS unified_conversion_source
    FROM mkt_offline_conversion_clean
    WHERE offline_effective_flag = 1
),

-- 最终业务宽表：维度、线上成本和线下价值形成可审查血缘
mkt_final_campaign_metrics AS (
    SELECT
        uv.unified_campaign_id AS final_campaign_id,
        cd.campaign_name AS final_campaign_name,
        cd.campaign_channel_code AS final_channel_code,
        uv.unified_value_date AS final_metric_date,
        sum(uv.unified_attributed_value) AS final_attributed_revenue,
        sum(uv.unified_media_cost) AS final_media_cost,
        sum(uv.unified_conversion_count) AS final_conversion_count,
        count(DISTINCT uv.unified_conversion_source) AS final_source_type_count,
        cast(
            sum(uv.unified_attributed_value) / greatest(sum(uv.unified_media_cost), 0.0001)
            AS decimal(20, 8)
        ) AS final_blended_roas,
        max(cd.configured_lookback_days) AS final_configured_lookback_days,
        collect_set(uv.unified_conversion_source) AS final_conversion_sources
    FROM mkt_online_offline_value uv
    LEFT JOIN mkt_campaign_dimension cd
        ON uv.unified_campaign_id = cd.campaign_key
       AND uv.unified_value_date BETWEEN to_date(cd.campaign_start_time) AND to_date(cd.campaign_end_time)
    WHERE EXISTS (
        SELECT
            1
        FROM mkt_creative_dimension cr
        WHERE cr.creative_audit_status IN ('approved', 'pass')
           OR cr.creative_updated_date >= date_sub(current_date(), 90)
    )
    GROUP BY
        uv.unified_campaign_id,
        cd.campaign_name,
        cd.campaign_channel_code,
        uv.unified_value_date
)

-- 最终 SELECT：字段均为营销归因语义，不复用通用模板投影
SELECT
    'marketing_attribution' AS lineage_case_name,
    fm.final_campaign_id AS campaign_id,
    fm.final_campaign_name AS campaign_name,
    fm.final_channel_code AS channel_code,
    fm.final_metric_date AS metric_date,
    fm.final_attributed_revenue AS attributed_revenue,
    fm.final_media_cost AS media_cost,
    fm.final_conversion_count AS conversion_count,
    fm.final_source_type_count AS conversion_source_type_count,
    fm.final_blended_roas AS blended_roas,
    fm.final_configured_lookback_days AS lookback_days,
    fm.final_conversion_sources AS conversion_sources,
    CASE
        WHEN fm.final_blended_roas >= 3 THEN 'high_return'
        WHEN fm.final_blended_roas >= 1 THEN 'break_even'
        ELSE 'low_return'
    END AS campaign_return_band,
    current_timestamp() AS corpus_evaluated_at
FROM mkt_final_campaign_metrics fm
WHERE fm.final_campaign_id IS NOT NULL;
