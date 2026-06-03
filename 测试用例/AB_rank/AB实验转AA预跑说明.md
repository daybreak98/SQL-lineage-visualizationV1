# AB_rank 从 AB 实验到 AA 预跑的实现说明

本文基于以下两个脚本整理：

- [AB实验.sql](/D:/Users/yingjie.hu/DataGripProjects/hive/AB_rank/AB实验.sql)
- [AA预跑.sql](/D:/Users/yingjie.hu/DataGripProjects/hive/AB_rank/AA预跑.sql)

目标是说明 `AB_rank` 这条链路里，原来的 AB 实验查询是如何改造成 AA 预跑查询的。

## 1. 链路摘要

### 上游来源

- AB 实验脚本直接读取 `ihotel_default.dw_ihotel_abtest_index_searchlist_di`
- AA 预跑脚本读取两部分来源
  - `f_abt.ab_division_hive_result`：提供实验分桶结果
  - `ihotel_default.dw_ihotel_aa_index_searchlist_di`：提供 AA 搜索和订单事实

### 下游目标

- 两个脚本的下游目标都不是写表，而是产出实验结果报表查询
- 最终都输出实验组维度下的核心指标，例如 `revenue_per_uv`、`s2d`、`s2o`

### 输入粒度

- AB 搜索输入：搜索曝光明细粒度
- AB 订单输入：订单明细粒度
- AA 搜索输入：AA 搜索曝光明细粒度
- AA 订单输入：AA 订单明细粒度
- 分桶输入：`clientcode + dt` 粒度

### 输出粒度

- AB 实验输出：`datee + ab_version + ab_rule_version`
- AA 预跑输出：`ab_dt + ab_group`

### 主键

- AB 实验结果主键可视作：`datee + ab_version + ab_rule_version`
- AA 预跑结果主键可视作：`ab_dt + ab_group`

## 2. 转换核心思路

AB 到 AA 的改造不是简单替表，而是把“实验信息的获取方式”从事实表内嵌字段，改成“分桶表 + AA 事实表”的两段式关联。

核心变化有 5 点：

1. 实验标识来源变化
2. 分组维度变化
3. 事实表来源变化
4. 用户关联键变化
5. 业务筛选条件迁移

## 3. 具体改造点

### 3.1 实验标识来源变化

AB 实验脚本里，实验信息直接来自事实表本身：

- `ab_exp_id`
- `ab_version`
- `ab_rule_version`

这意味着 AB 查询只需要过滤：

```sql
and ab_exp_id = '260402_ho_gj_comment_limit'
```

AA 预跑脚本里，AA 事实表本身不承担实验分桶信息，因此先从：

```sql
f_abt.ab_division_hive_result
```

取出：

- `dt`
- `ab_group`
- `clientcode`

再把 `clientcode` 映射回 AA 事实表中的用户字段。

对应实现是：

```sql
select dt, ab_group, clientcode
from f_abt.ab_division_hive_result
where testcode = '260413_ho_gj_upstaost'
```

这一步本质上完成了：

- AB 的“表内实验标识过滤”
- 变成 AA 的“先拿实验分桶用户，再回表取数”

### 3.2 分组维度变化

AB 的结果按以下维度聚合：

- `datee`
- `ab_exp_id`
- `ab_version`
- `ab_rule_version`

AA 的结果按以下维度聚合：

- `ab_dt`
- `ab_group`

这说明改造后的分组单位从“实验版本/规则版本”切换成了“AA 分桶组”。

也就是说：

- AB 看的是版本差异
- AA 看的是预分流组差异

### 3.3 事实表来源变化

AB 脚本搜索和订单都来自同一张 AB 事实表：

```sql
ihotel_default.dw_ihotel_abtest_index_searchlist_di
```

通过 `type` 区分：

- `type = 'searchlist'`
- `type = 'order'`

AA 预跑脚本则切换成：

```sql
ihotel_default.dw_ihotel_aa_index_searchlist_di
```

同样通过 `type` 区分：

- `type = 'searchlist'`
- `type = 'order'`

所以迁移时，指标计算逻辑大体不变，但底层事实源已经切到 AA 口径。

### 3.4 用户关联键变化

这是整个转换里最关键的变化。

AB 实验脚本里，不需要额外关联分桶表，因为实验版本已经写在事实表里。

AA 预跑脚本里，需要把分桶结果回连到事实表：

- 搜索侧：`ab.clientcode = a.user_id`
- 订单侧：`ab.clientcode = a.order_user_id`

对应 SQL 结构如下：

```sql
from (
    select dt, ab_group, clientcode
    from f_abt.ab_division_hive_result
    ...
) ab
left join (
    select *
    from ihotel_default.dw_ihotel_aa_index_searchlist_di
    where type = 'searchlist'
) a
    on ab.clientcode = a.user_id
   and ab.dt = a.dt
```

订单侧则把 `user_id` 换成 `order_user_id`。

这一步的意义是：

- 先确定“哪些用户属于 AA 某个组”
- 再把这些用户在 AA 事实表中的搜索/订单行为拿出来汇总

### 3.5 业务筛选条件迁移

AB 脚本中的筛选条件示例是：

- `user_id_type = 'uid'`
- `is_big_order_user = '正常用户'`
- `country_name = '韩国'`
- `city_name = '首尔'`

AA 预跑脚本中的筛选条件示例变成了：

- `newolduser = '新客'`
- `highlowstar = 'low_star'`

这说明 AB 转 AA 时，业务筛选不是机械复制，而是要根据 AA 底表实际可用字段重新选择。

结论是：

- 实验字段必须替换
- 用户关联键必须替换
- 聚合维度必须替换
- 业务筛选条件要按 AA 底表字段重新映射，不能直接照搬

## 4. 哪些内容保持不变

虽然数据来源和分组方式变了，但下面这些核心计算逻辑基本保持不变：

- `search_times`
- `search_uv`
- `show_item`
- `show_pv`
- `click_uv`
- `order_uv`
- `order_num`
- `order_pv`
- `show_adr`
- `order_adr`
- `revenue_per_uv`
- `s2d`
- `s2o`

也就是说，这次转换的重点不是重写指标，而是重写“如何圈定实验用户”和“如何按组取数”。

## 5. 可以抽象成一个通用迁移模板

从 `AB_rank` 这组脚本里，可以抽象出一个稳定模板：

### 第一步：从分桶表拿实验用户

```sql
select dt, ab_group, clientcode
from f_abt.ab_division_hive_result
where testcode = 'xxx'
```

### 第二步：关联 AA 搜索事实

```sql
ab.clientcode = aa_search.user_id
and ab.dt = aa_search.dt
```

### 第三步：关联 AA 订单事实

```sql
ab.clientcode = aa_order.order_user_id
and ab.dt = aa_order.dt
```

### 第四步：分别聚合搜索指标和订单指标

- 搜索侧单独聚合
- 订单侧单独聚合

### 第五步：在组粒度上合并结果

```sql
on a.ab_dt = b.ab_dt
and a.ab_group = b.ab_group
```

这个模板后续也可以复用到别的 AB 转 AA 预跑场景。

## 6. 风险点

### join explosion risk

风险来源：

- 如果分桶表中的 `clientcode` 在同一天出现重复，或者 AA 明细表连接键不唯一，可能造成放大

当前脚本的控制方式：

- 分桶表先 `group by dt, ab_group, clientcode`
- 搜索和订单各自独立聚合
- 最终只在组粒度 join

### duplicate-count risk

风险来源：

- 如果直接把搜索明细和订单明细混在一层 join，会导致订单指标放大

当前脚本的控制方式：

- `search_result` 和 `order_result` 分开聚合
- 最后只在聚合结果层 join

### filter-scope drift

风险来源：

- AB 筛选条件直接照搬到 AA，可能因为字段语义不同造成口径漂移

当前脚本的处理方式：

- AA 脚本重新选择 AA 表里的可用字段做筛选
- 不再依赖 AB 表独有的实验字段

## 7. 校验 SQL

### 7.1 校验分桶用户是否正常匹配到 AA 搜索数据

```sql
with ab_user as (
    select dt, ab_group, clientcode
    from f_abt.ab_division_hive_result
    where testcode = '260413_ho_gj_upstaost'
      and dt between '2026-04-12' and '2026-04-12'
    group by 1,2,3
)
select
    ab.dt,
    ab.ab_group,
    count(distinct ab.clientcode) as ab_user_cnt,
    count(distinct a.user_id) as matched_search_user_cnt
from ab_user ab
left join ihotel_default.dw_ihotel_aa_index_searchlist_di a
    on ab.clientcode = a.user_id
   and ab.dt = a.dt
   and a.type = 'searchlist'
group by 1,2
order by 1,2;
```

### 7.2 校验分桶用户是否正常匹配到 AA 订单数据

```sql
with ab_user as (
    select dt, ab_group, clientcode
    from f_abt.ab_division_hive_result
    where testcode = '260413_ho_gj_upstaost'
      and dt between '2026-04-12' and '2026-04-12'
    group by 1,2,3
)
select
    ab.dt,
    ab.ab_group,
    count(distinct ab.clientcode) as ab_user_cnt,
    count(distinct a.order_user_id) as matched_order_user_cnt,
    count(distinct a.order_info_order_no) as matched_order_cnt
from ab_user ab
left join ihotel_default.dw_ihotel_aa_index_searchlist_di a
    on ab.clientcode = a.order_user_id
   and ab.dt = a.dt
   and a.type = 'order'
group by 1,2
order by 1,2;
```

### 7.3 校验最终输出粒度

```sql
select
    ab_dt,
    ab_group,
    count(*) as row_cnt
from (
    -- 粘贴 AA预跑.sql 的最终查询
) t
group by 1,2
having count(*) > 1;
```

预期结果应为空。

## 8. 回归检查

- AA 输出是否仍然是一行一个 `ab_dt + ab_group`
- `search_result` 与 `order_result` 的 join 后行数是否稳定
- `revenue_per_uv`、`s2d`、`s2o` 是否能正常产出非空值
- 搜索 UV 是否大于等于下单 UV
- 订单数是否大于等于下单用户数

## 9. 建议测试

- 抽一个 `ab_group`，手工核对分桶人数和匹配到的搜索 UV
- 抽一个 `ab_group`，手工核对匹配到的订单用户数和订单数
- 分别去掉和加上 `newolduser`、`highlowstar` 过滤，观察结果是否符合预期
- 对比 AB 与 AA 的核心指标趋势，确认迁移后只是分组方式改变，不是指标逻辑失真

## 10. 文档更新建议

- 记录 `AB_rank` 的 AA 预跑依赖 `f_abt.ab_division_hive_result`
- 记录 AA 版本的实验分组维度由 `ab_version + ab_rule_version` 改为 `ab_group`
- 记录搜索和订单的关联键分别是 `user_id` 和 `order_user_id`
- 记录业务筛选条件需要按 AA 底表字段重映射，不能直接照搬 AB 事实表字段

## 11. 一句话总结

`AB_rank` 从 AB 实验切到 AA 预跑，本质上是把“直接按 AB 事实表中的实验字段聚合”，改成“先从分桶表拿到 AA 组用户，再去 AA 事实表回表取搜索和订单数据，最后按 `ab_group` 汇总输出”。
