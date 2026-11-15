# 上传 SQL 的列级血缘解析重点拆解

## 1. SQL 结构概览

该 SQL 的主链路可以抽象为：

```text
物理表
  ↓
order_90 / user_type / hotel_info / ab_rule / product
  ↓
no_user / search_list / order_detail
  ↓
search_result / order_result
  ↓
final select
```

## 2. 关键 CTE 依赖关系

```text
order_90
  ← default.mdw_order_v3_international

no_user
  ← order_90

user_type
  ← pub.dim_user_profile_nd

hotel_info
  ← ihotel_default.ods_qhotel_intl_hotel_info_publish

ab_rule
  ← default.ods_abtest_rule_info
  ← default.ods_abtest_sdk_log_endtime_hotel

product
  ← default.dwd_hotel_cq_compare_price_result_intl_hi

search_list
  ← default.dwd_ihotel_flow_app_searchlist_di
  ← temp.temp_yiquny_zhang_ihotel_area_region_forever
  ← user_type
  ← hotel_info
  ← product
  ← no_user

order_detail
  ← mdw_order_v3_international
  ← search_list
  ← no_user

search_result
  ← ab_rule
  ← search_list

order_result
  ← ab_rule
  ← order_detail

final select
  ← search_result
  ← order_result
```

## 3. 最终输出字段样例血缘

### 3.1 `单UV收益`

表达式：

```sql
cast(b.total_order_commission / a.show_uv as decimal(20,2)) as `单UV收益`
```

一跳血缘：

```text
order_result.total_order_commission → 单UV收益
search_result.show_uv              → 单UV收益
```

根字段血缘：

```text
mdw_order_v3_international.init_commission_after → order_detail.order_commission → order_result.total_order_commission → 单UV收益
mdw_order_v3_international.coupon_info           → order_detail.order_commission → order_result.total_order_commission → 单UV收益
mdw_order_v3_international.ext_plat_certificate  → order_detail.order_commission → order_result.total_order_commission → 单UV收益
mdw_order_v3_international.batch_series          → order_detail.order_commission → order_result.total_order_commission → 单UV收益

default.dwd_ihotel_flow_app_searchlist_di.orig_device_id → search_result.show_uv → 单UV收益
default.dwd_ihotel_flow_app_searchlist_di.is_display     → search_result.show_uv → 单UV收益
default.dwd_ihotel_flow_app_searchlist_di.hotel_seq       → search_result.show_uv → 单UV收益
```

### 3.2 `S2D`

表达式：

```sql
concat(round(a.click_uv/a.show_uv*100,2),'%') as `S2D`
```

一跳血缘：

```text
search_result.click_uv → S2D
search_result.show_uv  → S2D
```

根字段血缘主要来自：

```text
default.dwd_ihotel_flow_app_searchlist_di.orig_device_id
default.dwd_ihotel_flow_app_searchlist_di.is_display
default.dwd_ihotel_flow_app_searchlist_di.hotel_seq
default.dwd_ihotel_flow_app_searchlist_di.detail_log_id
```

### 3.3 `搜索预定率_pv`

表达式：

```sql
concat(round(a.order_pv/a.show_pv*100,2),'%') as `搜索预定率_pv`
```

根字段血缘主要来自：

```text
default.dwd_ihotel_flow_app_searchlist_di.order_info_order_no
default.dwd_ihotel_flow_app_searchlist_di.search_request_uid
default.dwd_ihotel_flow_app_searchlist_di.is_display
```

### 3.4 `订单ADR`

表达式：

```sql
cast(b.order_adr as decimal(20,2)) as `订单ADR`
```

递归链路：

```text
mdw_order_v3_international.init_gmv    → order_detail.init_gmv    → order_result.order_adr → 订单ADR
mdw_order_v3_international.room_night   → order_detail.room_night   → order_result.order_adr → 订单ADR
```

### 3.5 `曝光与订单adr_gap`

表达式：

```sql
concat(round((a.show_adr/b.order_adr-1)*100,2),'%') as `曝光与订单adr_gap`
```

根字段血缘来自两个指标分支：

```text
show_adr 分支：
  default.dwd_ihotel_flow_app_searchlist_di.qpayprice
  default.dwd_ihotel_flow_app_searchlist_di.is_display
  default.dwd_ihotel_flow_app_searchlist_di.hotel_seq

order_adr 分支：
  mdw_order_v3_international.init_gmv
  mdw_order_v3_international.room_night
```

## 4. 对解析器能力的要求

该 SQL 至少要求解析器支持：

| 能力 | 重要性 | 说明 |
|---|---:|---|
| 多层 CTE schema | 高 | `search_result/order_result` 必须继续穿透 |
| 表达式多输入依赖 | 高 | 比率类指标普遍依赖多个字段 |
| 聚合函数依赖 | 高 | `count distinct`、`sum`、`avg` 是核心指标来源 |
| `case when` 依赖 | 高 | 订单佣金、产品力分类、搜索意图分类都依赖 case |
| `select *` 展开 | 高 | 多处子查询使用 `select *` |
| join alias 消歧 | 高 | 最终 select 中 a/b 别名非常关键 |
| map/array/function 字段识别 | 中 | `user_info['orig_device_id']`、`coupon_info[...]` |
| SourceLocation 精准定位 | 中 | 可后置，不阻塞字段血缘 P0 |

## 5. 最小验收

第一版不要求解析完整 100% 字段，但至少应该稳定识别：

```text
单UV收益
S2D
S2O
搜索点击率_pv
搜索预定率_pv
订单ADR
曝光ADR
曝光与订单adr_gap
```

这几个字段覆盖了：

```text
CTE 穿透 + 聚合 + 表达式 + join alias + 多输入依赖
```
