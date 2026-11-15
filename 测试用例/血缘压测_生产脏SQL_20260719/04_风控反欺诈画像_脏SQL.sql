/*
 * 案例 04：风控反欺诈画像生产脏 SQL
 * 拓扑：账户/设备/IP/商户节点 -> 多类型图边 UNION -> 图度数与邻居风险；
 *       规则、模型、历史损失、黑白名单分支 -> 案件特征 -> 同账户风险排序 -> 人审结果。
 * 污染文本包含中文、分号;、\\d、\\s、\\w、\\u4e00-\\u9fa5。
 */
WITH

-- 风险申请：每次业务申请形成案件起点; 注释中的 DELETE; 不执行
risk_application_clean AS (
    SELECT
        cast(a.case_id AS string) AS application_case_id,
        cast(a.account_id AS string) AS application_account_id,
        cast(a.merchant_id AS string) AS application_merchant_id,
        cast(a.apply_time AS timestamp) AS application_occurred_at,
        to_date(a.apply_time) AS application_date,
        coalesce(a.application_type, 'unknown') AS application_type_code,
        cast(coalesce(a.request_amount, 0) AS decimal(20, 4)) AS application_request_amount,
        regexp_extract(coalesce(a.request_no, ''), '([A-Z]+)-(\\d+)', 2) AS application_request_sequence,
        get_json_object(a.application_json, '$.channel.code') AS application_channel_code,
        CASE WHEN a.status <> 'cancelled' THEN 1 ELSE 0 END AS active_application_flag
    FROM prod_risk.risk_application_di a
    WHERE a.dt >= date_format(date_sub(current_date(), 60), 'yyyyMMdd')
),

-- 账户画像：账户节点只保留身份与历史属性; 不复制申请字段
risk_account_profile AS (
    SELECT
        cast(ac.account_id AS string) AS account_node_id,
        to_date(ac.register_time) AS account_register_date,
        datediff(current_date(), to_date(ac.register_time)) AS account_age_days,
        coalesce(ac.country_code, 'UNKNOWN') AS account_country_code,
        coalesce(ac.member_level, 'none') AS account_member_level,
        cast(coalesce(ac.verified_level, 0) AS int) AS account_verified_level,
        CASE WHEN ac.is_employee = 1 THEN 1 ELSE 0 END AS account_employee_flag,
        get_json_object(ac.profile_json, '$.kyc.status') AS account_kyc_status
    FROM prod_risk.account_profile_df ac
    WHERE ac.is_deleted = 0
),

-- 设备指纹：JSON、中文文本清洗与标签展开集中在设备源; 注释有分号;
risk_device_fingerprint AS (
    SELECT
        cast(d.device_id AS string) AS device_node_id,
        cast(d.account_id AS string) AS device_owner_account_id,
        cast(d.first_seen_time AS timestamp) AS device_first_seen_at,
        cast(d.last_seen_time AS timestamp) AS device_last_seen_at,
        regexp_replace(coalesce(d.raw_text, ''), '\\s+', ' ') AS device_text_normalized,
        regexp_extract(coalesce(d.raw_text, ''), 'sdk[=:](\\w+)', 1) AS device_sdk_token,
        get_json_object(d.event_payload, '$.campaign.id') AS device_campaign_id,
        get_json_object(d.event_payload, '$.device.os') AS device_os_name,
        get_json_object(d.event_payload, '$.rooted') AS device_rooted_text,
        device_tag_lv.tag_name AS device_risk_tag,
        CASE
            WHEN coalesce(d.raw_text, '') rlike '[\\u4e00-\\u9fa5]+' THEN 'cn_note'
            WHEN coalesce(d.raw_text, '') rlike '\\d{6,}' THEN 'long_number'
            ELSE 'ordinary'
        END AS device_text_pattern
    FROM prod_risk.device_fingerprint_di d
    LATERAL VIEW OUTER explode(
        split(coalesce(d.tag_text, ''), ',')
    ) device_tag_lv AS tag_name
    WHERE d.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- 登录事件：账户、设备和 IP 的三元关系是图边来源; 分号;
risk_login_event AS (
    SELECT
        cast(l.login_id AS string) AS login_event_id,
        cast(l.account_id AS string) AS login_account_id,
        cast(l.device_id AS string) AS login_device_id,
        coalesce(l.ip_address, '0.0.0.0') AS login_ip_address,
        cast(l.login_time AS timestamp) AS login_occurred_at,
        to_date(l.login_time) AS login_date,
        coalesce(l.login_result, 'unknown') AS login_result_code,
        regexp_replace(coalesce(l.user_agent, ''), '[\\r\\n\\t]+', ' ') AS login_user_agent_clean,
        CASE WHEN l.login_result = 'success' THEN 1 ELSE 0 END AS login_success_flag
    FROM prod_risk.account_login_event_di l
    WHERE l.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- IP 信誉：IP 节点风险来自外部情报; CIDR 文本用正则分组
risk_ip_reputation AS (
    SELECT
        coalesce(ip.ip_address, '0.0.0.0') AS ip_node_id,
        coalesce(ip.country_code, 'UNKNOWN') AS ip_country_code,
        coalesce(ip.network_type, 'unknown') AS ip_network_type,
        cast(coalesce(ip.reputation_score, 0) AS decimal(12, 4)) AS ip_reputation_score,
        cast(coalesce(ip.proxy_probability, 0) AS decimal(12, 8)) AS ip_proxy_probability,
        regexp_extract(coalesce(ip.cidr_block, ''), '^(\\d+\\.\\d+)', 1) AS ip_cidr_prefix,
        CASE WHEN ip.blacklisted = 1 THEN 1 ELSE 0 END AS ip_blacklist_flag,
        to_date(ip.updated_at) AS ip_reputation_date
    FROM prod_risk.ip_reputation_df ip
    WHERE ip.snapshot_date = date_format(date_sub(current_date(), 1), 'yyyyMMdd')
),

-- 支付尝试：账户、设备、商户和金额构成交易图边; 失败也要计数
risk_payment_attempt AS (
    SELECT
        cast(p.attempt_id AS string) AS payment_attempt_id,
        cast(p.account_id AS string) AS payment_account_id,
        cast(p.device_id AS string) AS payment_device_id,
        cast(p.merchant_id AS string) AS payment_merchant_id,
        cast(p.attempt_time AS timestamp) AS payment_attempted_at,
        to_date(p.attempt_time) AS payment_attempt_date,
        cast(coalesce(p.attempt_amount, 0) AS decimal(20, 4)) AS payment_attempt_amount,
        coalesce(p.result_code, 'unknown') AS payment_result_code,
        CASE WHEN p.result_code = 'approved' THEN 1 ELSE 0 END AS payment_approved_flag
    FROM prod_risk.payment_attempt_di p
    WHERE p.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- 商户维表：商户节点提供行业和历史等级; 注释中的 UPDATE;
risk_merchant_dimension AS (
    SELECT
        cast(m.merchant_id AS string) AS merchant_node_id,
        coalesce(m.merchant_name, '未知商户') AS merchant_name,
        coalesce(m.industry_code, 'unknown') AS merchant_industry_code,
        coalesce(m.risk_tier, 'unrated') AS merchant_risk_tier,
        to_date(m.onboard_time) AS merchant_onboard_date,
        cast(coalesce(m.historical_chargeback_rate, 0) AS decimal(12, 8)) AS merchant_chargeback_rate,
        CASE WHEN m.status = 'active' THEN 1 ELSE 0 END AS merchant_active_flag
    FROM prod_risk.merchant_dimension_df m
    WHERE m.is_deleted = 0
),

-- 规则命中：一案多规则，严重度和权重后续聚合
risk_rule_hit AS (
    SELECT
        cast(rh.rule_hit_id AS string) AS rule_hit_event_id,
        cast(rh.case_id AS string) AS rule_hit_case_id,
        cast(rh.rule_id AS string) AS triggered_rule_id,
        cast(rh.hit_time AS timestamp) AS rule_hit_at,
        coalesce(rh.rule_category, 'unknown') AS triggered_rule_category,
        cast(coalesce(rh.rule_weight, 0) AS decimal(12, 8)) AS triggered_rule_weight,
        coalesce(rh.severity, 'low') AS triggered_rule_severity,
        regexp_replace(coalesce(rh.evidence_text, ''), '\\s+', ' ') AS rule_evidence_normalized
    FROM prod_risk.rule_hit_event_di rh
    WHERE rh.dt >= date_format(date_sub(current_date(), 60), 'yyyyMMdd')
),

-- 模型评分：多模型版本取最新分数; 不覆盖规则信号
risk_model_score AS (
    SELECT
        cast(ms.score_id AS string) AS model_score_event_id,
        cast(ms.case_id AS string) AS model_score_case_id,
        coalesce(ms.model_name, 'unknown') AS scoring_model_name,
        coalesce(ms.model_version, 'unknown') AS scoring_model_version,
        cast(ms.score_time AS timestamp) AS model_scored_at,
        cast(coalesce(ms.risk_probability, 0) AS decimal(12, 8)) AS model_risk_probability,
        cast(coalesce(ms.raw_score, 0) AS decimal(20, 8)) AS model_raw_score,
        get_json_object(ms.explanation_json, '$.top_feature') AS model_top_feature
    FROM prod_risk.model_score_di ms
    WHERE ms.dt >= date_format(date_sub(current_date(), 60), 'yyyyMMdd')
),

-- 历史拒付：账户和商户两侧的损失信号; 注释包含分号;
risk_chargeback_history AS (
    SELECT
        cast(cb.chargeback_id AS string) AS chargeback_event_id,
        cast(cb.account_id AS string) AS chargeback_account_id,
        cast(cb.merchant_id AS string) AS chargeback_merchant_id,
        cast(cb.chargeback_time AS timestamp) AS chargeback_occurred_at,
        to_date(cb.chargeback_time) AS chargeback_date,
        cast(coalesce(cb.loss_amount, 0) AS decimal(20, 4)) AS chargeback_loss_amount,
        coalesce(cb.reason_code, 'unknown') AS chargeback_reason_code,
        CASE WHEN cb.status = 'confirmed' THEN 1 ELSE 0 END AS confirmed_chargeback_flag
    FROM prod_risk.chargeback_fact_di cb
    WHERE cb.dt >= date_format(date_sub(current_date(), 365), 'yyyyMMdd')
),

-- 黑名单：不同实体类型统一在 membership 分支映射
risk_blacklist AS (
    SELECT
        cast(bl.list_record_id AS string) AS blacklist_record_id,
        coalesce(bl.entity_type, 'unknown') AS blacklist_entity_type,
        cast(bl.entity_id AS string) AS blacklist_entity_id,
        coalesce(bl.reason_code, 'unknown') AS blacklist_reason_code,
        cast(bl.effective_time AS timestamp) AS blacklist_effective_at,
        CASE WHEN bl.status = 'active' THEN 1 ELSE 0 END AS active_blacklist_flag
    FROM prod_risk.blacklist_snapshot_df bl
    WHERE bl.snapshot_date = date_format(date_sub(current_date(), 1), 'yyyyMMdd')
),

-- 白名单：白名单不直接删除风险，只改变最终处置建议; 分号;
risk_whitelist AS (
    SELECT
        cast(wl.list_record_id AS string) AS whitelist_record_id,
        coalesce(wl.entity_type, 'unknown') AS whitelist_entity_type,
        cast(wl.entity_id AS string) AS whitelist_entity_id,
        coalesce(wl.approval_scope, 'unknown') AS whitelist_approval_scope,
        cast(wl.expire_time AS timestamp) AS whitelist_expired_at,
        CASE WHEN wl.status = 'active' AND wl.expire_time > current_timestamp() THEN 1 ELSE 0 END AS active_whitelist_flag
    FROM prod_risk.whitelist_snapshot_df wl
    WHERE wl.snapshot_date = date_format(date_sub(current_date(), 1), 'yyyyMMdd')
),

-- 人审结果：模型与规则之后的标签，用于结果层评估
risk_case_review AS (
    SELECT
        cast(rv.review_id AS string) AS review_event_id,
        cast(rv.case_id AS string) AS reviewed_case_id,
        cast(rv.reviewer_id AS string) AS reviewer_id,
        cast(rv.review_time AS timestamp) AS reviewed_at,
        coalesce(rv.review_decision, 'pending') AS review_decision_code,
        regexp_extract(coalesce(rv.review_note, ''), '(欺诈|正常|待核实|误报)', 1) AS review_note_category,
        cast(coalesce(rv.review_duration_seconds, 0) AS bigint) AS review_duration_seconds
    FROM prod_risk.case_review_fact_di rv
    WHERE rv.dt >= date_format(date_sub(current_date(), 60), 'yyyyMMdd')
),

-- 账户节点：画像映射为图节点属性
risk_account_node AS (
    SELECT
        concat('account:', account.account_node_id) AS graph_account_node_id,
        account.account_node_id AS graph_account_business_id,
        account.account_age_days AS graph_account_age_days,
        account.account_country_code AS graph_account_country_code,
        account.account_verified_level AS graph_account_verified_level,
        account.account_kyc_status AS graph_account_kyc_status,
        CASE
            WHEN account.account_age_days < 7 THEN 1
            ELSE 0
        END AS graph_new_account_flag
    FROM risk_account_profile account
    WHERE account.account_employee_flag = 0
),

-- 设备节点：按设备聚合多个标签与归属账户数量
risk_device_node AS (
    SELECT
        concat('device:', device.device_node_id) AS graph_device_node_id,
        device.device_node_id AS graph_device_business_id,
        min(device.device_first_seen_at) AS graph_device_first_seen_at,
        max(device.device_last_seen_at) AS graph_device_last_seen_at,
        count(DISTINCT device.device_owner_account_id) AS graph_device_owner_count,
        max(CASE WHEN device.device_rooted_text = 'true' THEN 1 ELSE 0 END) AS graph_rooted_device_flag,
        collect_set(device.device_risk_tag) AS graph_device_risk_tags,
        collect_set(device.device_os_name) AS graph_device_os_names
    FROM risk_device_fingerprint device
    GROUP BY device.device_node_id
),

-- IP 节点：信誉分转换为节点危险等级
risk_ip_node AS (
    SELECT
        concat('ip:', ip.ip_node_id) AS graph_ip_node_id,
        ip.ip_node_id AS graph_ip_business_id,
        ip.ip_country_code AS graph_ip_country_code,
        ip.ip_network_type AS graph_ip_network_type,
        ip.ip_reputation_score AS graph_ip_reputation_score,
        ip.ip_proxy_probability AS graph_ip_proxy_probability,
        CASE
            WHEN ip.ip_blacklist_flag = 1 OR ip.ip_proxy_probability >= 0.8 THEN 'high'
            WHEN ip.ip_reputation_score >= 50 THEN 'medium'
            ELSE 'low'
        END AS graph_ip_risk_level
    FROM risk_ip_reputation ip
),

-- 账户设备边：成功登录构造有向边并统计最近时间
risk_account_device_edge AS (
    SELECT
        concat('account:', login.login_account_id) AS edge_source_node_id,
        concat('device:', login.login_device_id) AS edge_target_node_id,
        'account_uses_device' AS edge_relation_type,
        count(DISTINCT login.login_event_id) AS edge_event_count,
        min(login.login_occurred_at) AS edge_first_seen_at,
        max(login.login_occurred_at) AS edge_last_seen_at,
        cast(1.0 AS decimal(12, 8)) AS edge_base_weight
    FROM risk_login_event login
    WHERE login.login_success_flag = 1
    GROUP BY login.login_account_id, login.login_device_id
),

-- 设备 IP 边：登录事件构建设备到 IP 的网络关系
risk_device_ip_edge AS (
    SELECT
        concat('device:', login.login_device_id) AS edge_source_node_id,
        concat('ip:', login.login_ip_address) AS edge_target_node_id,
        'device_uses_ip' AS edge_relation_type,
        count(DISTINCT login.login_event_id) AS edge_event_count,
        min(login.login_occurred_at) AS edge_first_seen_at,
        max(login.login_occurred_at) AS edge_last_seen_at,
        cast(0.8 AS decimal(12, 8)) AS edge_base_weight
    FROM risk_login_event login
    GROUP BY login.login_device_id, login.login_ip_address
),

-- 账户商户边：支付尝试构成交易关系，金额成为边权
risk_account_merchant_edge AS (
    SELECT
        concat('account:', payment.payment_account_id) AS edge_source_node_id,
        concat('merchant:', payment.payment_merchant_id) AS edge_target_node_id,
        'account_pays_merchant' AS edge_relation_type,
        count(DISTINCT payment.payment_attempt_id) AS edge_event_count,
        min(payment.payment_attempted_at) AS edge_first_seen_at,
        max(payment.payment_attempted_at) AS edge_last_seen_at,
        sum(payment.payment_attempt_amount) AS edge_base_weight
    FROM risk_payment_attempt payment
    GROUP BY payment.payment_account_id, payment.payment_merchant_id
),

-- 图边全集：三类边集合运算保持 relation_type
risk_graph_edge_union AS (
    SELECT
        edge_source_node_id,
        edge_target_node_id,
        edge_relation_type,
        edge_event_count,
        edge_first_seen_at,
        edge_last_seen_at,
        edge_base_weight
    FROM risk_account_device_edge
    UNION ALL
    SELECT
        edge_source_node_id,
        edge_target_node_id,
        edge_relation_type,
        edge_event_count,
        edge_first_seen_at,
        edge_last_seen_at,
        edge_base_weight
    FROM risk_device_ip_edge
    UNION ALL
    SELECT
        edge_source_node_id,
        edge_target_node_id,
        edge_relation_type,
        edge_event_count,
        edge_first_seen_at,
        edge_last_seen_at,
        edge_base_weight
    FROM risk_account_merchant_edge
),

-- 图度数：源节点和目标节点分别聚合后再 UNION
risk_graph_degree AS (
    SELECT
        degree_rows.degree_node_id AS graph_degree_node_id,
        sum(degree_rows.outgoing_edge_count) AS outgoing_edge_count,
        sum(degree_rows.incoming_edge_count) AS incoming_edge_count,
        sum(degree_rows.connected_event_count) AS connected_event_count,
        sum(degree_rows.connected_edge_weight) AS connected_edge_weight,
        count(DISTINCT degree_rows.connected_relation_type) AS connected_relation_type_count
    FROM (
        SELECT
            edge_source_node_id AS degree_node_id,
            count(DISTINCT edge_target_node_id) AS outgoing_edge_count,
            cast(0 AS bigint) AS incoming_edge_count,
            sum(edge_event_count) AS connected_event_count,
            sum(edge_base_weight) AS connected_edge_weight,
            edge_relation_type AS connected_relation_type
        FROM risk_graph_edge_union
        GROUP BY edge_source_node_id, edge_relation_type
        UNION ALL
        SELECT
            edge_target_node_id AS degree_node_id,
            cast(0 AS bigint) AS outgoing_edge_count,
            count(DISTINCT edge_source_node_id) AS incoming_edge_count,
            sum(edge_event_count) AS connected_event_count,
            sum(edge_base_weight) AS connected_edge_weight,
            edge_relation_type AS connected_relation_type
        FROM risk_graph_edge_union
        GROUP BY edge_target_node_id, edge_relation_type
    ) degree_rows
    GROUP BY degree_rows.degree_node_id
),

-- 规则信号：规则命中与最新模型评分在案件粒度汇合
risk_rule_model_signal AS (
    SELECT
        rules.rule_case_id AS signal_case_id,
        rules.triggered_rule_count AS signal_rule_count,
        rules.critical_rule_count AS signal_critical_rule_count,
        rules.weighted_rule_score AS signal_weighted_rule_score,
        model.scoring_model_name AS signal_model_name,
        model.scoring_model_version AS signal_model_version,
        model.model_risk_probability AS signal_model_probability,
        model.model_top_feature AS signal_model_top_feature,
        greatest(
            coalesce(rules.weighted_rule_score, 0),
            coalesce(model.model_risk_probability, 0)
        ) AS combined_risk_signal
    FROM (
        SELECT
            rule_hit_case_id AS rule_case_id,
            count(DISTINCT triggered_rule_id) AS triggered_rule_count,
            count(DISTINCT CASE WHEN triggered_rule_severity = 'critical' THEN triggered_rule_id END) AS critical_rule_count,
            sum(triggered_rule_weight) AS weighted_rule_score,
            max(rule_hit_at) AS latest_rule_hit_at
        FROM risk_rule_hit
        GROUP BY rule_hit_case_id
    ) rules
    LEFT JOIN (
        SELECT
            ranked_scores.model_score_case_id,
            ranked_scores.scoring_model_name,
            ranked_scores.scoring_model_version,
            ranked_scores.model_risk_probability,
            ranked_scores.model_top_feature
        FROM (
            SELECT
                model_score_case_id,
                scoring_model_name,
                scoring_model_version,
                model_risk_probability,
                model_top_feature,
                row_number() OVER (
                    PARTITION BY model_score_case_id
                    ORDER BY model_scored_at DESC, model_score_event_id DESC
                ) AS model_score_recency_rank
            FROM risk_model_score
        ) ranked_scores
        WHERE ranked_scores.model_score_recency_rank = 1
    ) model
        ON rules.rule_case_id = model.model_score_case_id
),

-- 历史损失：账户与商户损失分别计算，案件层按两侧汇入
risk_account_loss_history AS (
    SELECT
        chargeback_account_id AS loss_account_id,
        count(DISTINCT chargeback_event_id) AS historical_chargeback_count,
        sum(CASE WHEN confirmed_chargeback_flag = 1 THEN chargeback_loss_amount ELSE 0 END) AS confirmed_loss_amount,
        max(chargeback_occurred_at) AS latest_chargeback_at,
        count(DISTINCT chargeback_merchant_id) AS loss_merchant_count
    FROM risk_chargeback_history
    GROUP BY chargeback_account_id
),

-- 黑白名单统一：名单类型保留并在案件处置层解释
risk_list_membership AS (
    SELECT
        blacklist_entity_type AS listed_entity_type,
        blacklist_entity_id AS listed_entity_id,
        'black' AS list_color,
        blacklist_reason_code AS list_reason_or_scope,
        blacklist_effective_at AS list_effective_at,
        active_blacklist_flag AS active_list_flag
    FROM risk_blacklist
    UNION ALL
    SELECT
        whitelist_entity_type AS listed_entity_type,
        whitelist_entity_id AS listed_entity_id,
        'white' AS list_color,
        whitelist_approval_scope AS list_reason_or_scope,
        whitelist_expired_at AS list_effective_at,
        active_whitelist_flag AS active_list_flag
    FROM risk_whitelist
),

-- 案件特征：申请、账户节点、图度数、规则模型、损失和名单分支汇合
risk_case_feature AS (
    SELECT
        app.application_case_id AS feature_case_id,
        app.application_account_id AS feature_account_id,
        app.application_merchant_id AS feature_merchant_id,
        app.application_occurred_at AS feature_application_at,
        app.application_request_amount AS feature_request_amount,
        account.graph_account_age_days AS feature_account_age_days,
        account.graph_new_account_flag AS feature_new_account_flag,
        degree.outgoing_edge_count AS feature_graph_out_degree,
        degree.connected_event_count AS feature_graph_event_count,
        degree.connected_relation_type_count AS feature_graph_relation_types,
        signal.signal_rule_count AS feature_rule_count,
        signal.signal_critical_rule_count AS feature_critical_rule_count,
        signal.signal_model_probability AS feature_model_probability,
        signal.combined_risk_signal AS feature_combined_signal,
        loss.historical_chargeback_count AS feature_chargeback_count,
        loss.confirmed_loss_amount AS feature_confirmed_loss_amount,
        max(CASE WHEN listing.list_color = 'black' AND listing.active_list_flag = 1 THEN 1 ELSE 0 END) AS feature_blacklist_flag,
        max(CASE WHEN listing.list_color = 'white' AND listing.active_list_flag = 1 THEN 1 ELSE 0 END) AS feature_whitelist_flag,
        merchant.merchant_risk_tier AS feature_merchant_risk_tier,
        merchant.merchant_chargeback_rate AS feature_merchant_chargeback_rate
    FROM risk_application_clean app
    LEFT JOIN risk_account_node account
        ON concat('account:', app.application_account_id) = account.graph_account_node_id
    LEFT JOIN risk_graph_degree degree
        ON concat('account:', app.application_account_id) = degree.graph_degree_node_id
    LEFT JOIN risk_rule_model_signal signal
        ON app.application_case_id = signal.signal_case_id
    LEFT JOIN risk_account_loss_history loss
        ON app.application_account_id = loss.loss_account_id
    LEFT JOIN risk_list_membership listing
        ON app.application_account_id = listing.listed_entity_id
       AND listing.listed_entity_type = 'account'
    LEFT JOIN risk_merchant_dimension merchant
        ON app.application_merchant_id = merchant.merchant_node_id
    WHERE app.active_application_flag = 1
    GROUP BY
        app.application_case_id,
        app.application_account_id,
        app.application_merchant_id,
        app.application_occurred_at,
        app.application_request_amount,
        account.graph_account_age_days,
        account.graph_new_account_flag,
        degree.outgoing_edge_count,
        degree.connected_event_count,
        degree.connected_relation_type_count,
        signal.signal_rule_count,
        signal.signal_critical_rule_count,
        signal.signal_model_probability,
        signal.combined_risk_signal,
        loss.historical_chargeback_count,
        loss.confirmed_loss_amount,
        merchant.merchant_risk_tier,
        merchant.merchant_chargeback_rate
),

-- 案件排序：同账户多申请按综合信号和时间排序
risk_ranked_case AS (
    SELECT
        feature.feature_case_id AS ranked_case_id,
        feature.feature_account_id AS ranked_account_id,
        feature.feature_merchant_id AS ranked_merchant_id,
        feature.feature_application_at AS ranked_application_at,
        feature.feature_request_amount AS ranked_request_amount,
        feature.feature_graph_out_degree AS ranked_graph_out_degree,
        feature.feature_graph_event_count AS ranked_graph_event_count,
        feature.feature_rule_count AS ranked_rule_count,
        feature.feature_critical_rule_count AS ranked_critical_rule_count,
        feature.feature_model_probability AS ranked_model_probability,
        feature.feature_combined_signal AS ranked_combined_signal,
        feature.feature_chargeback_count AS ranked_chargeback_count,
        feature.feature_confirmed_loss_amount AS ranked_confirmed_loss_amount,
        feature.feature_blacklist_flag AS ranked_blacklist_flag,
        feature.feature_whitelist_flag AS ranked_whitelist_flag,
        row_number() OVER (
            PARTITION BY feature.feature_account_id
            ORDER BY
                feature.feature_blacklist_flag DESC,
                feature.feature_combined_signal DESC,
                feature.feature_application_at DESC
        ) AS account_risk_case_rank,
        avg(feature.feature_combined_signal) OVER (
            PARTITION BY feature.feature_account_id
        ) AS account_average_risk_signal,
        sum(feature.feature_request_amount) OVER (
            PARTITION BY feature.feature_account_id
            ORDER BY feature.feature_application_at
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS account_running_requested_amount
    FROM risk_case_feature feature
),

-- 人审结果：案件排序连接最新审核，形成模型与人工一致性
risk_review_outcome AS (
    SELECT
        ranked.ranked_case_id AS outcome_case_id,
        ranked.ranked_account_id AS outcome_account_id,
        ranked.ranked_merchant_id AS outcome_merchant_id,
        ranked.ranked_application_at AS outcome_application_at,
        ranked.ranked_request_amount AS outcome_request_amount,
        ranked.ranked_graph_out_degree AS outcome_graph_out_degree,
        ranked.ranked_graph_event_count AS outcome_graph_event_count,
        ranked.ranked_rule_count AS outcome_rule_count,
        ranked.ranked_critical_rule_count AS outcome_critical_rule_count,
        ranked.ranked_model_probability AS outcome_model_probability,
        ranked.ranked_combined_signal AS outcome_combined_signal,
        ranked.ranked_chargeback_count AS outcome_chargeback_count,
        ranked.ranked_confirmed_loss_amount AS outcome_confirmed_loss_amount,
        ranked.ranked_blacklist_flag AS outcome_blacklist_flag,
        ranked.ranked_whitelist_flag AS outcome_whitelist_flag,
        review.review_decision_code AS outcome_review_decision,
        review.review_note_category AS outcome_review_category,
        review.review_duration_seconds AS outcome_review_duration_seconds,
        CASE
            WHEN ranked.ranked_whitelist_flag = 1 THEN 'allow'
            WHEN ranked.ranked_blacklist_flag = 1 THEN 'block'
            WHEN ranked.ranked_combined_signal >= 0.8 THEN 'block'
            WHEN ranked.ranked_combined_signal >= 0.5 THEN 'manual_review'
            ELSE 'allow'
        END AS outcome_recommended_action
    FROM risk_ranked_case ranked
    LEFT JOIN (
        SELECT
            latest.reviewed_case_id,
            latest.review_decision_code,
            latest.review_note_category,
            latest.review_duration_seconds
        FROM (
            SELECT
                reviewed_case_id,
                review_decision_code,
                review_note_category,
                review_duration_seconds,
                row_number() OVER (
                    PARTITION BY reviewed_case_id
                    ORDER BY reviewed_at DESC, review_event_id DESC
                ) AS review_recency_rank
            FROM risk_case_review
        ) latest
        WHERE latest.review_recency_rank = 1
    ) review
        ON ranked.ranked_case_id = review.reviewed_case_id
)

SELECT
    'fraud_graph_portrait' AS lineage_case_name,
    outcome.outcome_case_id AS case_id,
    outcome.outcome_account_id AS account_id,
    outcome.outcome_merchant_id AS merchant_id,
    outcome.outcome_application_at AS application_time,
    outcome.outcome_request_amount AS requested_amount,
    outcome.outcome_graph_out_degree AS graph_out_degree,
    outcome.outcome_graph_event_count AS graph_event_count,
    outcome.outcome_rule_count AS triggered_rule_count,
    outcome.outcome_critical_rule_count AS critical_rule_count,
    outcome.outcome_model_probability AS model_risk_probability,
    outcome.outcome_combined_signal AS combined_risk_signal,
    outcome.outcome_chargeback_count AS historical_chargeback_count,
    outcome.outcome_confirmed_loss_amount AS historical_confirmed_loss,
    outcome.outcome_blacklist_flag AS blacklist_flag,
    outcome.outcome_whitelist_flag AS whitelist_flag,
    outcome.outcome_review_decision AS human_review_decision,
    outcome.outcome_recommended_action AS recommended_action,
    CASE
        WHEN outcome.outcome_review_decision = outcome.outcome_recommended_action THEN 1
        ELSE 0
    END AS model_review_agreement_flag,
    current_timestamp() AS corpus_evaluated_at
FROM risk_review_outcome outcome
WHERE outcome.outcome_case_id IS NOT NULL
  AND EXISTS (
      SELECT
          1
      FROM risk_application_clean application_probe
      WHERE application_probe.application_case_id = outcome.outcome_case_id
  );
