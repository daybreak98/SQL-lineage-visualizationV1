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

下表中的“具名关系”采用 `tools/validate_production_dirty_sql_corpus.py` 的统一口径，合计 CTE、内联/标量子查询别名和物理表引用。每个案例均包含 24 个 CTE、14 张独立物理源表、2 个显式内联子查询，并额外包含 `IN/EXISTS` 标量或相关子查询。

| 文件 | 业务场景 | 物理行 | 具名关系 | 重点压力构造 |
| --- | --- | ---: | ---: | --- |
| `01_营销漏斗归因_脏SQL.sql` | 广告曝光、点击、落地页、支付与退款闭环归因 | 733 | 78 | Campaign JSON、标签展开、多触点窗口、线下回补 |
| `02_交易履约全链路_脏SQL.sql` | 下单、支付、仓配、签收、退款与工单履约 | 733 | 78 | 履约阶段 UNION、承运成本关联、时序窗口、退款闭环 |
| `03_AB实验指标归因_脏SQL.sql` | 曝光分桶、实验转化、护栏指标与排除样本 | 733 | 78 | 实验 JSON、主体窗口、增量指标聚合、排除样本子查询 |
| `04_风控反欺诈画像_脏SQL.sql` | 账户、设备、IP、规则命中、拒付与冻结画像 | 733 | 78 | 设备标签展开、风险规则关联、案件窗口、白名单相关子查询 |
| `05_流量渠道归因_脏SQL.sql` | 页面、广告、App、UTM、搜索、社媒与线下触点 | 733 | 78 | UTM 正则、渠道 JSON、多触点路径窗口、媒体成本关联 |

## 人工血缘核验目标

每个案例建议至少观察以下三条根表到最终输出的路径；箭头中间为关键派生关系，末端为最终 CTE 输出列。

### 01 营销漏斗归因

- `prod_mkt.mkt_ad_impression_di.amount` → `mkt_src_ad_impression.metric_amount` → `mkt_all_touchpoints` → `mkt_entity_rollup.total_amount` → 最终 `attributed_revenue`；
- `prod_mkt.mkt_channel_cost_di.amount` → `mkt_src_channel_cost.metric_amount` → `mkt_inline_activity.auxiliary_amount` → `mkt_combined_activity.metric_amount` → 最终 `attributed_revenue`；
- `prod_mkt.mkt_offline_conversion_di.event_payload` → `mkt_src_offline_conversion.event_payload` → `mkt_json_profile.json_city` → `mkt_final_metrics.json_city`。

### 02 交易履约全链路

- `prod_ord.ord_order_created_di.amount` → `ord_src_order_created.metric_amount` → `ord_all_touchpoints` → `ord_entity_rollup.total_amount` → 最终 `fulfilled_gmv`；
- `prod_ord.ord_carrier_fee_di.amount` → `ord_src_carrier_fee.metric_amount` → `ord_inline_activity.auxiliary_amount` → `ord_combined_activity.metric_amount` → 最终 `fulfilled_gmv`；
- `prod_ord.ord_service_ticket_di.event_payload` → `ord_src_service_ticket.event_payload` → `ord_json_profile.high_risk_flag` → `ord_final_metrics.high_risk_flag`。

### 03 AB 实验指标归因

- `prod_exp.exp_experiment_exposure_di.amount` → `exp_src_experiment_exposure.metric_amount` → `exp_all_touchpoints` → `exp_entity_rollup.total_amount` → 最终 `incremental_revenue`；
- `prod_exp.exp_allocation_cost_di.amount` → `exp_src_allocation_cost.metric_amount` → `exp_inline_activity.auxiliary_amount` → `exp_combined_activity.metric_amount` → 最终 `incremental_revenue`；
- `prod_exp.exp_exclusion_event_di.event_payload` → `exp_src_exclusion_event.event_payload` → `exp_json_profile.profile_code` → `exp_final_metrics.profile_code`。

### 04 风控反欺诈画像

- `prod_risk.risk_risk_application_di.amount` → `risk_src_risk_application.metric_amount` → `risk_all_touchpoints` → `risk_entity_rollup.total_amount` → 最终 `risk_exposure_amount`；
- `prod_risk.risk_model_score_di.amount` → `risk_src_model_score.metric_amount` → `risk_inline_activity.auxiliary_amount` → `risk_combined_activity.metric_amount` → 最终 `risk_exposure_amount`；
- `prod_risk.risk_whitelist_record_di.event_payload` → `risk_src_whitelist_record.event_payload` → `risk_json_profile.high_risk_flag` → `risk_final_metrics.attribution_status`。

### 05 流量渠道归因

- `prod_traffic.traffic_page_view_di.amount` → `traffic_src_page_view.metric_amount` → `traffic_all_touchpoints` → `traffic_entity_rollup.total_amount` → 最终 `attributed_conversion_value`；
- `prod_traffic.traffic_media_cost_di.amount` → `traffic_src_media_cost.metric_amount` → `traffic_inline_activity.auxiliary_amount` → `traffic_combined_activity.metric_amount` → 最终 `attributed_conversion_value`；
- `prod_traffic.traffic_offline_touch_di.event_payload` → `traffic_src_offline_touch.event_payload` → `traffic_json_profile.json_city` → `traffic_final_metrics.json_city`。

案例 06—10 的业务清单与人工血缘路径由第二批语料生成任务继续补充。
