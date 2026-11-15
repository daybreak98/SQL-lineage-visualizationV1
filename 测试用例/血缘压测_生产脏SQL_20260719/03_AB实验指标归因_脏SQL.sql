/*
 * 案例 03：AB 实验指标归因生产脏 SQL
 * 拓扑：实验曝光与分桶 -> cohort/资格人群 -> 分析总体；
 *       行为指标集合 -> 前置基线 / 实验期结果 -> CUPED 校正 -> variant 与护栏统计。
 * 噪声标记：中文注释、分号;、\\d、\\s、\\w、\\u4e00-\\u9fa5。
 */
WITH

-- 实验定义：生命周期和主指标口径; 注释里的 ALTER; 不执行
exp_definition_clean AS (
    SELECT
        cast(e.experiment_id AS string) AS experiment_key,
        coalesce(e.experiment_name, '未命名实验') AS experiment_name,
        cast(e.start_time AS timestamp) AS experiment_started_at,
        cast(e.end_time AS timestamp) AS experiment_ended_at,
        coalesce(e.primary_metric_code, 'conversion') AS primary_metric_code,
        cast(coalesce(e.preperiod_days, 14) AS int) AS preperiod_days,
        cast(coalesce(e.minimum_sample_size, 100) AS bigint) AS minimum_sample_size,
        get_json_object(e.config_json, '$.allocation.unit') AS randomization_unit,
        get_json_object(e.config_json, '$.guardrail.metric') AS configured_guardrail_metric,
        CASE WHEN e.status IN ('running', 'completed') THEN 1 ELSE 0 END AS analyzable_experiment_flag
    FROM prod_exp.experiment_definition_df e
    WHERE e.is_deleted = 0
),

-- variant 定义：流量比例需要标准化; 注释中有分号;
exp_variant_dimension AS (
    SELECT
        cast(v.variant_id AS string) AS variant_key,
        cast(v.experiment_id AS string) AS variant_experiment_key,
        coalesce(v.variant_name, 'unnamed') AS variant_name,
        coalesce(v.variant_role, 'treatment') AS variant_role,
        cast(coalesce(v.traffic_ratio, 0) AS decimal(12, 8)) AS configured_traffic_ratio,
        regexp_extract(coalesce(v.variant_code, ''), '([A-Za-z]+)[_-](\\d+)', 1) AS variant_code_family,
        CASE WHEN v.is_enabled = 1 THEN 1 ELSE 0 END AS variant_enabled_flag
    FROM prod_exp.experiment_variant_df v
    WHERE v.snapshot_date = date_format(date_sub(current_date(), 1), 'yyyyMMdd')
),

-- 曝光事件：JSON、文本正则与标签展开集中在真实曝光源
exp_exposure_clean AS (
    SELECT
        cast(x.exposure_id AS string) AS exposure_event_id,
        cast(x.experiment_id AS string) AS exposure_experiment_id,
        cast(x.variant_id AS string) AS exposure_variant_id,
        cast(x.subject_id AS string) AS exposure_subject_id,
        cast(x.exposure_time AS timestamp) AS exposure_occurred_at,
        to_date(x.exposure_time) AS exposure_date,
        regexp_replace(coalesce(x.raw_text, ''), '\\s+', ' ') AS exposure_text_normalized,
        regexp_extract(coalesce(x.raw_text, ''), 'bucket[=:](\\d+)', 1) AS exposure_bucket_text,
        get_json_object(x.event_payload, '$.campaign.id') AS exposure_campaign_id,
        get_json_object(x.event_payload, '$.device.os') AS exposure_device_os,
        exposure_tag_lv.tag_name AS exposure_tag_name,
        CASE
            WHEN coalesce(x.raw_text, '') rlike '[\\u4e00-\\u9fa5]+' THEN 'cn'
            WHEN coalesce(x.raw_text, '') rlike '\\w+' THEN 'token'
            ELSE 'empty'
        END AS exposure_text_language
    FROM prod_exp.experiment_exposure_di x
    LATERAL VIEW OUTER explode(
        split(coalesce(x.tag_text, ''), ',')
    ) exposure_tag_lv AS tag_name
    WHERE x.dt >= date_format(date_sub(current_date(), 60), 'yyyyMMdd')
),

-- 分桶日志：同一主体重分桶时取最新有效记录; 不与曝光直接混写
exp_assignment_clean AS (
    SELECT
        cast(a.assignment_id AS string) AS assignment_event_id,
        cast(a.experiment_id AS string) AS assignment_experiment_id,
        cast(a.variant_id AS string) AS assigned_variant_id,
        cast(a.subject_id AS string) AS assigned_subject_id,
        cast(a.assignment_time AS timestamp) AS assigned_at,
        cast(coalesce(a.bucket_number, -1) AS int) AS assigned_bucket_number,
        coalesce(a.hash_version, 'unknown') AS assignment_hash_version,
        regexp_replace(coalesce(a.hash_input, ''), '[\\r\\n\\t\\s]+', '') AS assignment_hash_input_clean,
        CASE WHEN a.assignment_status = 'valid' THEN 1 ELSE 0 END AS assignment_valid_flag
    FROM prod_exp.subject_assignment_di a
    WHERE a.dt >= date_format(date_sub(current_date(), 60), 'yyyyMMdd')
),

-- cohort 成员：人群进入和退出时间控制分析资格; 注释内 SELECT;
exp_cohort_membership AS (
    SELECT
        cast(c.cohort_id AS string) AS cohort_key,
        cast(c.subject_id AS string) AS cohort_subject_id,
        cast(c.enter_time AS timestamp) AS cohort_entered_at,
        cast(c.exit_time AS timestamp) AS cohort_exited_at,
        coalesce(c.cohort_type, 'default') AS cohort_type_code,
        cast(coalesce(c.membership_weight, 1) AS decimal(12, 8)) AS cohort_membership_weight,
        CASE
            WHEN c.exit_time IS NULL OR c.exit_time >= current_timestamp() THEN 1
            ELSE 0
        END AS current_cohort_member_flag
    FROM prod_exp.cohort_membership_df c
    WHERE c.snapshot_date >= date_format(date_sub(current_date(), 60), 'yyyyMMdd')
),

-- 主体画像：用于分层分析，不向下游机械透传原始 JSON
exp_subject_profile AS (
    SELECT
        cast(p.subject_id AS string) AS profile_subject_id,
        coalesce(p.country_code, 'UNKNOWN') AS profile_country_code,
        coalesce(p.device_type, 'unknown') AS profile_device_type,
        coalesce(p.member_level, 'none') AS profile_member_level,
        to_date(p.register_time) AS profile_register_date,
        datediff(current_date(), to_date(p.register_time)) AS profile_tenure_days,
        get_json_object(p.preference_json, '$.segment') AS profile_preference_segment,
        CASE WHEN p.is_employee = 1 THEN 1 ELSE 0 END AS employee_subject_flag
    FROM prod_exp.subject_profile_df p
    WHERE p.is_deleted = 0
),

-- 通用指标事件：主指标、次指标通过 metric_code 区分; 注释中分号;
exp_metric_event_clean AS (
    SELECT
        cast(m.metric_event_id AS string) AS metric_event_key,
        cast(m.subject_id AS string) AS metric_subject_id,
        cast(m.metric_time AS timestamp) AS metric_occurred_at,
        to_date(m.metric_time) AS metric_date,
        coalesce(m.metric_code, 'unknown') AS metric_code,
        cast(coalesce(m.metric_value, 0) AS decimal(20, 8)) AS metric_value,
        coalesce(m.dimension_value, 'all') AS metric_dimension_value,
        regexp_extract(coalesce(m.source_trace, ''), 'trace[-_:](\\w+)', 1) AS metric_trace_token
    FROM prod_exp.metric_event_di m
    WHERE m.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- 转化事件：二元结果进入 metric 集合; 同一主体可多次转化
exp_conversion_clean AS (
    SELECT
        cast(c.conversion_id AS string) AS conversion_event_key,
        cast(c.subject_id AS string) AS conversion_subject_id,
        cast(c.conversion_time AS timestamp) AS conversion_occurred_at,
        to_date(c.conversion_time) AS conversion_date,
        coalesce(c.conversion_type, 'default') AS conversion_type_code,
        cast(coalesce(c.conversion_value, 0) AS decimal(20, 8)) AS conversion_value,
        CASE WHEN c.conversion_status = 'valid' THEN 1 ELSE 0 END AS valid_conversion_flag
    FROM prod_exp.conversion_event_di c
    WHERE c.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- 收入事实：连续指标单独进入实验期结果; 退款后收入已在源侧净额化
exp_revenue_clean AS (
    SELECT
        cast(r.revenue_event_id AS string) AS revenue_event_key,
        cast(r.subject_id AS string) AS revenue_subject_id,
        cast(r.revenue_time AS timestamp) AS revenue_occurred_at,
        to_date(r.revenue_time) AS revenue_date,
        cast(coalesce(r.net_revenue_amount, 0) AS decimal(20, 8)) AS net_revenue_value,
        upper(coalesce(r.currency_code, 'CNY')) AS revenue_currency_code,
        CASE WHEN r.is_recognized = 1 THEN 1 ELSE 0 END AS recognized_revenue_flag
    FROM prod_exp.subject_revenue_di r
    WHERE r.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- 护栏事件：性能与投诉等反向指标; 单独聚合避免污染主指标
exp_guardrail_clean AS (
    SELECT
        cast(g.guardrail_event_id AS string) AS guardrail_event_key,
        cast(g.subject_id AS string) AS guardrail_subject_id,
        cast(g.event_time AS timestamp) AS guardrail_occurred_at,
        to_date(g.event_time) AS guardrail_date,
        coalesce(g.guardrail_code, 'unknown') AS guardrail_metric_code,
        cast(coalesce(g.guardrail_value, 0) AS decimal(20, 8)) AS guardrail_metric_value,
        CASE WHEN g.severity IN ('high', 'critical') THEN 1 ELSE 0 END AS severe_guardrail_flag
    FROM prod_exp.guardrail_event_di g
    WHERE g.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- 排除样本：机器人、员工、跨组污染等原因; 相关子查询后续使用
exp_exclusion_clean AS (
    SELECT
        cast(ex.exclusion_id AS string) AS exclusion_event_key,
        cast(ex.experiment_id AS string) AS excluded_experiment_id,
        cast(ex.subject_id AS string) AS excluded_subject_id,
        coalesce(ex.reason_code, 'unknown') AS exclusion_reason_code,
        cast(ex.effective_time AS timestamp) AS exclusion_effective_at,
        CASE WHEN ex.is_active = 1 THEN 1 ELSE 0 END AS active_exclusion_flag
    FROM prod_exp.subject_exclusion_df ex
    WHERE ex.snapshot_date = date_format(date_sub(current_date(), 1), 'yyyyMMdd')
),

-- 分流成本：按 variant 记录实验资源成本; 注释有分号;
exp_allocation_cost_clean AS (
    SELECT
        cast(ac.experiment_id AS string) AS cost_experiment_id,
        cast(ac.variant_id AS string) AS cost_variant_id,
        to_date(ac.cost_date) AS allocation_cost_date,
        cast(coalesce(ac.compute_cost, 0) AS decimal(20, 8)) AS compute_cost_amount,
        cast(coalesce(ac.media_cost, 0) AS decimal(20, 8)) AS media_cost_amount,
        cast(coalesce(ac.incentive_cost, 0) AS decimal(20, 8)) AS incentive_cost_amount,
        cast(
            coalesce(ac.compute_cost, 0)
            + coalesce(ac.media_cost, 0)
            + coalesce(ac.incentive_cost, 0)
            AS decimal(20, 8)
        ) AS total_allocation_cost
    FROM prod_exp.variant_allocation_cost_di ac
    WHERE ac.dt >= date_format(date_sub(current_date(), 90), 'yyyyMMdd')
),

-- 最新分桶：窗口只在 assignment 分支内执行
exp_latest_assignment AS (
    SELECT
        ranked.assignment_event_id AS latest_assignment_id,
        ranked.assignment_experiment_id AS latest_assignment_experiment_id,
        ranked.assigned_variant_id AS latest_assigned_variant_id,
        ranked.assigned_subject_id AS latest_assigned_subject_id,
        ranked.assigned_at AS latest_assigned_at,
        ranked.assigned_bucket_number AS latest_bucket_number,
        ranked.assignment_hash_version AS latest_hash_version
    FROM (
        SELECT
            assignment_event_id,
            assignment_experiment_id,
            assigned_variant_id,
            assigned_subject_id,
            assigned_at,
            assigned_bucket_number,
            assignment_hash_version,
            row_number() OVER (
                PARTITION BY assignment_experiment_id, assigned_subject_id
                ORDER BY assigned_at DESC, assignment_event_id DESC
            ) AS assignment_recency_rank
        FROM exp_assignment_clean
        WHERE assignment_valid_flag = 1
    ) ranked
    WHERE ranked.assignment_recency_rank = 1
),

-- 有效曝光：实验、variant、曝光三表汇合并验证时间窗
exp_valid_exposure AS (
    SELECT
        exposure.exposure_event_id AS valid_exposure_id,
        exposure.exposure_experiment_id AS valid_experiment_id,
        exposure.exposure_variant_id AS valid_variant_id,
        exposure.exposure_subject_id AS valid_subject_id,
        exposure.exposure_occurred_at AS valid_exposure_at,
        definition.experiment_name AS valid_experiment_name,
        definition.primary_metric_code AS valid_primary_metric_code,
        definition.preperiod_days AS valid_preperiod_days,
        variant.variant_name AS valid_variant_name,
        variant.variant_role AS valid_variant_role,
        variant.configured_traffic_ratio AS valid_configured_traffic_ratio,
        exposure.exposure_campaign_id AS valid_campaign_id,
        exposure.exposure_device_os AS valid_device_os
    FROM exp_exposure_clean exposure
    INNER JOIN exp_definition_clean definition
        ON exposure.exposure_experiment_id = definition.experiment_key
       AND exposure.exposure_occurred_at BETWEEN definition.experiment_started_at AND definition.experiment_ended_at
    INNER JOIN exp_variant_dimension variant
        ON exposure.exposure_experiment_id = variant.variant_experiment_key
       AND exposure.exposure_variant_id = variant.variant_key
    WHERE definition.analyzable_experiment_flag = 1
      AND variant.variant_enabled_flag = 1
),

-- cohort 分层：成员关系连接画像，形成可读分层键
exp_cohort_profile AS (
    SELECT
        membership.cohort_key AS profiled_cohort_id,
        membership.cohort_subject_id AS profiled_subject_id,
        membership.cohort_type_code AS profiled_cohort_type,
        membership.cohort_membership_weight AS profiled_membership_weight,
        profile.profile_country_code AS profiled_country_code,
        profile.profile_device_type AS profiled_device_type,
        profile.profile_member_level AS profiled_member_level,
        profile.profile_tenure_days AS profiled_tenure_days,
        concat_ws(
            ':',
            membership.cohort_type_code,
            profile.profile_country_code,
            profile.profile_device_type
        ) AS analysis_stratum_key
    FROM exp_cohort_membership membership
    LEFT JOIN exp_subject_profile profile
        ON membership.cohort_subject_id = profile.profile_subject_id
    WHERE membership.current_cohort_member_flag = 1
      AND coalesce(profile.employee_subject_flag, 0) = 0
),

-- 合格主体：内联画像与排除表反连接
exp_eligible_subject AS (
    SELECT
        candidates.eligible_subject_id,
        candidates.eligible_country_code,
        candidates.eligible_device_type,
        candidates.eligible_member_level,
        candidates.eligible_tenure_days
    FROM (
        SELECT
            profile_subject_id AS eligible_subject_id,
            profile_country_code AS eligible_country_code,
            profile_device_type AS eligible_device_type,
            profile_member_level AS eligible_member_level,
            profile_tenure_days AS eligible_tenure_days
        FROM exp_subject_profile
        WHERE employee_subject_flag = 0
          AND profile_tenure_days >= 0
    ) candidates
    WHERE NOT EXISTS (
        SELECT
            1
        FROM exp_exclusion_clean exclusion
        WHERE exclusion.excluded_subject_id = candidates.eligible_subject_id
          AND exclusion.active_exclusion_flag = 1
    )
),

-- 分析总体：有效曝光、最新分桶、cohort 与资格四分支汇合
exp_analysis_population AS (
    SELECT
        exposure.valid_experiment_id AS population_experiment_id,
        exposure.valid_variant_id AS population_variant_id,
        exposure.valid_subject_id AS population_subject_id,
        exposure.valid_exposure_at AS population_exposure_at,
        exposure.valid_experiment_name AS population_experiment_name,
        exposure.valid_primary_metric_code AS population_primary_metric_code,
        exposure.valid_preperiod_days AS population_preperiod_days,
        exposure.valid_variant_name AS population_variant_name,
        exposure.valid_variant_role AS population_variant_role,
        cohort.analysis_stratum_key AS population_stratum_key,
        cohort.profiled_membership_weight AS population_weight,
        eligible.eligible_tenure_days AS population_tenure_days,
        CASE
            WHEN assignment.latest_assigned_variant_id = exposure.valid_variant_id THEN 0
            ELSE 1
        END AS assignment_mismatch_flag
    FROM exp_valid_exposure exposure
    INNER JOIN exp_latest_assignment assignment
        ON exposure.valid_experiment_id = assignment.latest_assignment_experiment_id
       AND exposure.valid_subject_id = assignment.latest_assigned_subject_id
    INNER JOIN exp_eligible_subject eligible
        ON exposure.valid_subject_id = eligible.eligible_subject_id
    LEFT JOIN exp_cohort_profile cohort
        ON exposure.valid_subject_id = cohort.profiled_subject_id
    WHERE assignment.latest_assigned_variant_id = exposure.valid_variant_id
),

-- 指标事件集合：不同业务源显式映射为统一 metric 语义
exp_metric_union AS (
    SELECT
        metric_event_key AS unified_metric_event_id,
        metric_subject_id AS unified_metric_subject_id,
        metric_occurred_at AS unified_metric_at,
        metric_date AS unified_metric_date,
        metric_code AS unified_metric_code,
        metric_value AS unified_metric_value,
        'behavior' AS unified_metric_family
    FROM exp_metric_event_clean
    UNION ALL
    SELECT
        conversion_event_key AS unified_metric_event_id,
        conversion_subject_id AS unified_metric_subject_id,
        conversion_occurred_at AS unified_metric_at,
        conversion_date AS unified_metric_date,
        concat('conversion_', conversion_type_code) AS unified_metric_code,
        CASE WHEN valid_conversion_flag = 1 THEN conversion_value ELSE 0 END AS unified_metric_value,
        'conversion' AS unified_metric_family
    FROM exp_conversion_clean
    UNION ALL
    SELECT
        revenue_event_key AS unified_metric_event_id,
        revenue_subject_id AS unified_metric_subject_id,
        revenue_occurred_at AS unified_metric_at,
        revenue_date AS unified_metric_date,
        'net_revenue' AS unified_metric_code,
        CASE WHEN recognized_revenue_flag = 1 THEN net_revenue_value ELSE 0 END AS unified_metric_value,
        'revenue' AS unified_metric_family
    FROM exp_revenue_clean
    UNION ALL
    SELECT
        guardrail_event_key AS unified_metric_event_id,
        guardrail_subject_id AS unified_metric_subject_id,
        guardrail_occurred_at AS unified_metric_at,
        guardrail_date AS unified_metric_date,
        guardrail_metric_code AS unified_metric_code,
        guardrail_metric_value AS unified_metric_value,
        'guardrail' AS unified_metric_family
    FROM exp_guardrail_clean
),

-- 主体日指标：统一事件先在主体、日期、指标粒度聚合
exp_subject_daily_metric AS (
    SELECT
        unioned.unified_metric_subject_id AS daily_subject_id,
        unioned.unified_metric_date AS daily_metric_date,
        unioned.unified_metric_code AS daily_metric_code,
        unioned.unified_metric_family AS daily_metric_family,
        sum(unioned.unified_metric_value) AS daily_metric_value,
        count(DISTINCT unioned.unified_metric_event_id) AS daily_metric_event_count,
        max(unioned.unified_metric_at) AS latest_daily_metric_at
    FROM exp_metric_union unioned
    GROUP BY
        unioned.unified_metric_subject_id,
        unioned.unified_metric_date,
        unioned.unified_metric_code,
        unioned.unified_metric_family
),

-- 前置基线：曝光前 N 天主指标均值作为 CUPED 协变量
exp_preperiod_baseline AS (
    SELECT
        population.population_experiment_id AS baseline_experiment_id,
        population.population_variant_id AS baseline_variant_id,
        population.population_subject_id AS baseline_subject_id,
        avg(coalesce(metric.daily_metric_value, 0)) AS preperiod_metric_mean,
        sum(coalesce(metric.daily_metric_event_count, 0)) AS preperiod_metric_event_count,
        count(DISTINCT metric.daily_metric_date) AS observed_preperiod_days
    FROM exp_analysis_population population
    LEFT JOIN exp_subject_daily_metric metric
        ON population.population_subject_id = metric.daily_subject_id
       AND metric.daily_metric_code = population.population_primary_metric_code
       AND metric.daily_metric_date >= date_sub(
            to_date(population.population_exposure_at),
            population.population_preperiod_days
       )
       AND metric.daily_metric_date < to_date(population.population_exposure_at)
    GROUP BY
        population.population_experiment_id,
        population.population_variant_id,
        population.population_subject_id
),

-- 实验期结果：曝光后主指标、转化、收入与护栏分别计量
exp_postperiod_outcome AS (
    SELECT
        population.population_experiment_id AS outcome_experiment_id,
        population.population_variant_id AS outcome_variant_id,
        population.population_subject_id AS outcome_subject_id,
        population.population_stratum_key AS outcome_stratum_key,
        population.population_weight AS outcome_population_weight,
        sum(
            CASE
                WHEN metric.daily_metric_code = population.population_primary_metric_code
                THEN coalesce(metric.daily_metric_value, 0)
                ELSE 0
            END
        ) AS primary_metric_outcome,
        sum(
            CASE
                WHEN metric.daily_metric_family = 'conversion'
                THEN coalesce(metric.daily_metric_value, 0)
                ELSE 0
            END
        ) AS conversion_metric_outcome,
        sum(
            CASE
                WHEN metric.daily_metric_family = 'revenue'
                THEN coalesce(metric.daily_metric_value, 0)
                ELSE 0
            END
        ) AS revenue_metric_outcome,
        sum(
            CASE
                WHEN metric.daily_metric_family = 'guardrail'
                THEN coalesce(metric.daily_metric_value, 0)
                ELSE 0
            END
        ) AS guardrail_metric_outcome
    FROM exp_analysis_population population
    LEFT JOIN exp_subject_daily_metric metric
        ON population.population_subject_id = metric.daily_subject_id
       AND metric.daily_metric_date >= to_date(population.population_exposure_at)
       AND metric.daily_metric_date <= date_add(to_date(population.population_exposure_at), 14)
    GROUP BY
        population.population_experiment_id,
        population.population_variant_id,
        population.population_subject_id,
        population.population_stratum_key,
        population.population_weight
),

-- CUPED 主体结果：使用固定 theta 演示协变量校正血缘
exp_cuped_subject_metric AS (
    SELECT
        outcome.outcome_experiment_id AS cuped_experiment_id,
        outcome.outcome_variant_id AS cuped_variant_id,
        outcome.outcome_subject_id AS cuped_subject_id,
        outcome.outcome_stratum_key AS cuped_stratum_key,
        outcome.outcome_population_weight AS cuped_population_weight,
        baseline.preperiod_metric_mean AS cuped_preperiod_mean,
        outcome.primary_metric_outcome AS cuped_raw_primary_metric,
        cast(
            outcome.primary_metric_outcome
            - 0.35 * (coalesce(baseline.preperiod_metric_mean, 0) - baseline_center.experiment_preperiod_mean)
            AS decimal(20, 8)
        ) AS cuped_adjusted_primary_metric,
        outcome.conversion_metric_outcome AS cuped_conversion_metric,
        outcome.revenue_metric_outcome AS cuped_revenue_metric,
        outcome.guardrail_metric_outcome AS cuped_guardrail_metric
    FROM exp_postperiod_outcome outcome
    LEFT JOIN exp_preperiod_baseline baseline
        ON outcome.outcome_experiment_id = baseline.baseline_experiment_id
       AND outcome.outcome_subject_id = baseline.baseline_subject_id
    LEFT JOIN (
        SELECT
            baseline_experiment_id AS centered_experiment_id,
            avg(preperiod_metric_mean) AS experiment_preperiod_mean
        FROM exp_preperiod_baseline
        GROUP BY baseline_experiment_id
    ) baseline_center
        ON outcome.outcome_experiment_id = baseline_center.centered_experiment_id
),

-- variant 统计：主体 CUPED 结果在实验组粒度汇总
exp_variant_statistics AS (
    SELECT
        cuped.cuped_experiment_id AS statistics_experiment_id,
        cuped.cuped_variant_id AS statistics_variant_id,
        count(DISTINCT cuped.cuped_subject_id) AS statistics_subject_count,
        avg(cuped.cuped_raw_primary_metric) AS raw_primary_metric_mean,
        avg(cuped.cuped_adjusted_primary_metric) AS cuped_primary_metric_mean,
        avg(cuped.cuped_conversion_metric) AS conversion_metric_mean,
        avg(cuped.cuped_revenue_metric) AS revenue_metric_mean,
        avg(cuped.cuped_guardrail_metric) AS guardrail_metric_mean,
        max(cuped.cuped_adjusted_primary_metric) AS maximum_adjusted_metric,
        min(cuped.cuped_adjusted_primary_metric) AS minimum_adjusted_metric,
        count(DISTINCT cuped.cuped_stratum_key) AS represented_stratum_count
    FROM exp_cuped_subject_metric cuped
    GROUP BY
        cuped.cuped_experiment_id,
        cuped.cuped_variant_id
),

-- 成本统计：资源成本独立聚合后再进入实验结论
exp_variant_cost_summary AS (
    SELECT
        cost_experiment_id AS summarized_cost_experiment_id,
        cost_variant_id AS summarized_cost_variant_id,
        sum(total_allocation_cost) AS summarized_total_allocation_cost,
        avg(total_allocation_cost) AS summarized_daily_allocation_cost,
        count(DISTINCT allocation_cost_date) AS summarized_cost_day_count
    FROM exp_allocation_cost_clean
    GROUP BY cost_experiment_id, cost_variant_id
),

-- 实验结果：variant 统计、角色和成本汇合，control 均值通过内联子查询提供
exp_final_experiment_result AS (
    SELECT
        stats.statistics_experiment_id AS final_experiment_id,
        stats.statistics_variant_id AS final_variant_id,
        variant.variant_name AS final_variant_name,
        variant.variant_role AS final_variant_role,
        stats.statistics_subject_count AS final_subject_count,
        stats.raw_primary_metric_mean AS final_raw_metric_mean,
        stats.cuped_primary_metric_mean AS final_cuped_metric_mean,
        control.control_cuped_metric_mean AS final_control_metric_mean,
        stats.cuped_primary_metric_mean - control.control_cuped_metric_mean AS final_absolute_lift,
        cast(
            (stats.cuped_primary_metric_mean - control.control_cuped_metric_mean)
            / greatest(abs(control.control_cuped_metric_mean), 0.000001)
            AS decimal(20, 8)
        ) AS final_relative_lift,
        stats.conversion_metric_mean AS final_conversion_mean,
        stats.revenue_metric_mean AS final_revenue_mean,
        stats.guardrail_metric_mean AS final_guardrail_mean,
        coalesce(cost.summarized_total_allocation_cost, 0) AS final_allocation_cost,
        stats.represented_stratum_count AS final_stratum_count
    FROM exp_variant_statistics stats
    INNER JOIN exp_variant_dimension variant
        ON stats.statistics_variant_id = variant.variant_key
       AND stats.statistics_experiment_id = variant.variant_experiment_key
    LEFT JOIN (
        SELECT
            control_stats.statistics_experiment_id AS control_experiment_id,
            avg(control_stats.cuped_primary_metric_mean) AS control_cuped_metric_mean
        FROM exp_variant_statistics control_stats
        INNER JOIN exp_variant_dimension control_variant
            ON control_stats.statistics_variant_id = control_variant.variant_key
        WHERE control_variant.variant_role = 'control'
        GROUP BY control_stats.statistics_experiment_id
    ) control
        ON stats.statistics_experiment_id = control.control_experiment_id
    LEFT JOIN exp_variant_cost_summary cost
        ON stats.statistics_experiment_id = cost.summarized_cost_experiment_id
       AND stats.statistics_variant_id = cost.summarized_cost_variant_id
)

SELECT
    'ab_experiment_metrics' AS lineage_case_name,
    result.final_experiment_id AS experiment_id,
    result.final_variant_id AS variant_id,
    result.final_variant_name AS variant_name,
    result.final_variant_role AS variant_role,
    result.final_subject_count AS analyzed_subject_count,
    result.final_raw_metric_mean AS raw_primary_metric_mean,
    result.final_cuped_metric_mean AS cuped_primary_metric_mean,
    result.final_control_metric_mean AS control_primary_metric_mean,
    result.final_absolute_lift AS absolute_metric_lift,
    result.final_relative_lift AS relative_metric_lift,
    result.final_conversion_mean AS conversion_metric_mean,
    result.final_revenue_mean AS revenue_metric_mean,
    result.final_guardrail_mean AS guardrail_metric_mean,
    result.final_allocation_cost AS experiment_allocation_cost,
    result.final_stratum_count AS represented_stratum_count,
    CASE
        WHEN result.final_subject_count < 100 THEN 'insufficient_sample'
        WHEN result.final_guardrail_mean > 0 THEN 'guardrail_review'
        WHEN result.final_relative_lift > 0 THEN 'positive'
        ELSE 'non_positive'
    END AS experiment_decision_state,
    current_timestamp() AS corpus_evaluated_at
FROM exp_final_experiment_result result
WHERE result.final_experiment_id IS NOT NULL;
