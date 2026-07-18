# 生产脏 SQL 血缘压测集

本目录承载 10 份可独立执行的 Spark SQL 血缘压测用例。每份文件是一个以 `WITH` 开始、以单条 `SELECT` 结束的查询，面向现有 SQL 血缘解析链路的回归验证。

## 静态准入契约

每份用例必须同时满足以下条件：

- 至少 300 个物理行；
- 至少 26 个具名关系（CTE、内联/标量子查询别名与物理表引用的合计）；
- 包含中文注释、含反斜杠的正则表达式；
- 包含正则、JSON、数组展开、窗口、聚合、条件和日期时间函数族；
- 包含 CTE、内联或标量子查询、JOIN 与集合运算；
- 使用 Spark SQL 语法，且只有一个最终查询。

## 使用方式

执行静态校验并生成本目录内的 `validation_report.json`：

```powershell
python tools/validate_production_dirty_sql_corpus.py
```

仅检查指定前缀的案例：

```powershell
python tools/validate_production_dirty_sql_corpus.py --cases 01 02 03 04 05
```

## 第一批案例清单（01—05）

下表中的“具名关系”采用 `tools/validate_production_dirty_sql_corpus.py` 的统一口径，合计 CTE、内联/标量子查询别名和物理表引用。五份案例故意采用不同的 CTE 数量、物理表数量、汇合顺序和终端投影，用来观察解析器面对不同依赖拓扑时的血缘稳定性。

| 文件 | 业务场景 | 物理行 | 具名关系 | 重点压力构造 |
| --- | --- | ---: | ---: | --- |
| `01_营销漏斗归因_脏SQL.sql` | 广告触点、订单净转化、位置权重、成本及线下回补 | 566 | 178 | 12 物理表、22 CTE、候选回溯、位置模型、线上/线下 UNION |
| `02_交易履约全链路_脏SQL.sql` | 下单到签收的顺序阶段链，支付/退款/工单旁路汇合 | 574 | 179 | 12 物理表、26 CTE、阶段事件流、相邻耗时窗口、SLA 汇总 |
| `03_AB实验指标归因_脏SQL.sql` | 曝光分桶、cohort 资格、前置基线、CUPED 与护栏 | 606 | 156 | 12 物理表、25 CTE、排除样本、前后周期分支、control 对照 |
| `04_风控反欺诈画像_脏SQL.sql` | 账户/设备/IP/商户图、规则模型、名单与人审 | 631 | 178 | 13 物理表、27 CTE、多类型图边、节点度数、案件风险排序 |
| `05_流量渠道归因_脏SQL.sql` | 八类数字触点、会话化、四种归因模型及成本回补 | 795 | 189 | 13 物理表、29 CTE、30 分钟会话、四模型分支、多触点旅程 |

## 人工血缘核验目标

每个案例建议至少观察以下三条根表到最终输出的路径；箭头中间为关键派生关系，末端为最终 CTE 输出列。

### 01 营销漏斗归因

- `prod_mkt.ad_impression_event_di.event_payload` → `mkt_impression_clean.impression_campaign_id` → `mkt_session_touchpoints.campaign_id` → `mkt_attribution_candidates.candidate_campaign_id` → `mkt_campaign_attribution_rollup.rollup_campaign_id` → 最终 `campaign_id`；
- `prod_mkt.order_payment_fact_di.paid_amount` → `mkt_order_clean.conversion_paid_amount` → `mkt_net_conversions.net_conversion_amount` → `mkt_weighted_attribution.weighted_conversion_amount` → `mkt_campaign_attribution_rollup.online_attributed_revenue` → 最终 `attributed_revenue`；
- `prod_mkt.channel_cost_fact_di.click_cost` → `mkt_channel_cost_clean.total_media_cost` → `mkt_campaign_cost_performance.performance_media_cost` → `mkt_online_offline_value.unified_media_cost` → 最终 `media_cost`。

### 02 交易履约全链路

- `prod_ord.order_header_di.create_time` → `ord_header_clean.order_created_at` → `ord_fulfillment_fact.fulfillment_created_at` → `ord_stage_event_stream.stage_event_at` → `ord_stage_timing.seconds_from_order_start` → 最终 `end_to_end_seconds`；
- `prod_ord.payment_transaction_di.paid_amount` → `ord_payment_clean.payment_amount` → `ord_payment_summary.total_successful_payment_amount` → `ord_fulfillment_fact.fulfillment_net_gmv` → 最终 `fulfilled_net_gmv`；
- `prod_ord.shipment_event_di.event_time` → `ord_shipment_event_clean.shipment_event_at` → `ord_transport_stage.first_shipment_event_at` → `ord_delivery_stage.delivered_first_shipment_at` → `ord_stage_timing` → 最终 `stage_delay_flag`。

### 03 AB 实验指标归因

- `prod_exp.experiment_exposure_di.subject_id` → `exp_exposure_clean.exposure_subject_id` → `exp_valid_exposure.valid_subject_id` → `exp_analysis_population.population_subject_id` → `exp_variant_statistics.statistics_subject_count` → 最终 `analyzed_subject_count`；
- `prod_exp.metric_event_di.metric_value` → `exp_metric_event_clean.metric_value` → `exp_metric_union.unified_metric_value` → `exp_preperiod_baseline.preperiod_metric_mean` / `exp_postperiod_outcome.primary_metric_outcome` → `exp_cuped_subject_metric.cuped_adjusted_primary_metric` → 最终 `cuped_primary_metric_mean`；
- `prod_exp.variant_allocation_cost_di.compute_cost` → `exp_allocation_cost_clean.total_allocation_cost` → `exp_variant_cost_summary.summarized_total_allocation_cost` → 最终 `experiment_allocation_cost`。

### 04 风控反欺诈画像

- `prod_risk.account_login_event_di.device_id` → `risk_account_device_edge.edge_target_node_id` → `risk_graph_edge_union` → `risk_graph_degree.connected_event_count` → `risk_case_feature.feature_graph_event_count` → 最终 `graph_event_count`；
- `prod_risk.rule_hit_event_di.rule_weight` + `prod_risk.model_score_di.risk_probability` → `risk_rule_model_signal.combined_risk_signal` → `risk_case_feature.feature_combined_signal` → `risk_ranked_case.ranked_combined_signal` → 最终 `combined_risk_signal`；
- `prod_risk.blacklist_snapshot_df.entity_id` → `risk_list_membership.listed_entity_id` → `risk_case_feature.feature_blacklist_flag` → `risk_review_outcome.outcome_recommended_action` → 最终 `recommended_action`。

### 05 流量渠道归因

- `prod_traffic.page_view_event_di.page_url` → `traffic_page_view_clean.page_utm_source` → `traffic_digital_touch_union.unified_channel_code` → `traffic_sessionized_touch.session_channel_code` → `traffic_attribution_candidate.candidate_channel_code` → 最终 `channel_code`；
- `prod_traffic.conversion_event_di.conversion_value` → `traffic_conversion_anchor.anchor_conversion_value` → 四个 `traffic_*_touch_model.model_attributed_value` 分支 → `traffic_model_union` → `traffic_channel_attribution.attributed_conversion_value` → 最终 `attributed_conversion_value`；
- `prod_traffic.media_cost_fact_di.click_cost` → `traffic_media_cost_clean.media_total_cost` → `traffic_channel_performance.performance_media_cost` → `traffic_online_offline_performance.unified_media_cost` → 最终 `media_cost` / `blended_roas`。

案例 06—10 的业务清单与人工血缘路径由第二批语料生成任务继续补充。
