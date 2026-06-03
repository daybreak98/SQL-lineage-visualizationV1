with ab_user as (select dt,
                        ab_group,
                        clientcode
                 from f_abt.ab_division_hive_result
                 WHERE testcode = '${code}'
                   AND dt between '${fromDt}' and '${toDt}'
                 group by 1, 2, 3)
   , q_uv_info as (select ab.dt,
                          ab.ab_group,
                          count(distinct t1.flow_user_id) as uv
                   from ab_user ab
                            left join (select *
                                       from ihotel_default.dw_ihotel_aa_index_order_di
                                       where dt between '${fromDt}' and '${toDt}'
                                         and flow_is_big_order_user = '正常用户'
                                         and type = 'flow'
                                           -- 新老客和星级可选
                                           <#if flow_user_type?exists>
                                            and flow_user_type in (
                                                <#list flow_user_type as item>
                                                '${item}'<#if item_has_next>,</#if> -- 新客,老客
                                                </#list>
                                            )</#if>

                                            <#if highlowstar?exists>
                                            and highlowstar in (
                                                <#list highlowstar as item>
                                                '${item}'<#if item_has_next>,</#if> -- high_star,middle_star,low_star
                                                </#list>
                                            )</#if>
                                         ) t1
                                      on ab.clientcode = t1.flow_user_id
                                          and ab.dt = t1.dt
                   where t1.flow_user_id is not null
                   group by 1, 2)
   , order_info_app as (select ab.dt
                             , ab.ab_group
                             , sum(init_commission_after)                                                 as q_commission_app       -- Q_佣金_app
                             , sum(init_gmv)                                                              as q_gmv_app              -- Q_GMV_app
                             , sum(coupon_subsidy_amount)                                                 as q_coupon_amount_app    -- Q_券额_app
                             , count(distinct order_no)                                                   as q_order_cnt_app        -- Q_订单量_app
                             , count(distinct t1.user_id)                                                 as q_order_user_cnt_app   -- Q_下单用户_app
                             , sum(room_night)                                                            as q_room_night_app       -- Q_间夜量_app
                             , count(distinct case when is_user_coupon = 'Y' then order_no else null end) as q_coupon_order_cnt_app -- Q_用券订单量_app
                             , sum(pricing_subsidy_amount) + sum(coupon_subsidy_amount) + sum(point_subsidy_amount) -
                               sum(multi_point_subsidy_amount) + sum(follow_price_subsidy_amount)         as `平台补贴额`
                             , (sum(pricing_subsidy_amount) + sum(coupon_subsidy_amount) + sum(point_subsidy_amount) -
                                sum(multi_point_subsidy_amount) + sum(follow_price_subsidy_amount)) /
                               sum(init_gmv)                                                              as `平台补贴率`
                             , sum(init_commission_after) / sum(init_gmv) +
                               (sum(pricing_subsidy_amount) + sum(coupon_subsidy_amount) + sum(point_subsidy_amount) -
                                sum(multi_point_subsidy_amount) + sum(follow_price_subsidy_amount) -
                                sum(bp_adv_amount_realized)) /
                               sum(init_gmv)                                                              as `补贴前佣金率`
                             , sum(init_commission_after) + sum(pricing_subsidy_amount) + sum(coupon_subsidy_amount) +
                               sum(point_subsidy_amount) - sum(multi_point_subsidy_amount) +
                               sum(follow_price_subsidy_amount) - sum(bp_adv_amount_realized)             as `补贴前佣金额`
                        from ab_user ab
                                 left join (select *
                                            from ihotel_default.dw_ihotel_aa_index_order_di
                                            where dt between '${fromDt}' and '${toDt}'
                                              and type = 'order'
                                              and is_big_order_user = '正常用户'
                                                -- 新老客和星级可选
                                                <#if user_type?exists>
                                            and user_type in (
                                                <#list user_type as item>
                                                '${item}'<#if item_has_next>,</#if> -- 新客,老客
                                                </#list>
                                            )</#if>

                                            <#if highlowstar?exists>
                                            and highlowstar in (
                                                <#list highlowstar as item>
                                                '${item}'<#if item_has_next>,</#if> -- high_star,middle_star,low_star
                                                </#list>
                                            )</#if>) t1
                                           on ab.clientcode = t1.user_id
                                               and ab.dt = t1.dt
                        where t1.user_id is not null
                        group by 1, 2)
   , q_data_info as (select t1.dt
                          , t1.ab_group
                          , coalesce(t1.uv, 0)                                                 as uv
                          , coalesce(t4.q_room_night_app, 0)                                   as q_room_night_app               -- Q_间夜量_app
                          , coalesce(t4.q_order_cnt_app, 0)                                    as q_order_cnt_app                -- Q_订单量_app
                          , coalesce(t4.q_order_user_cnt_app, 0)                               as q_order_user_cnt_app           -- Q_下单用户_app
                          , coalesce(t4.q_gmv_app, 0)                                          as q_gmv_app                      -- Q_GMV_app
                          , coalesce(t4.q_commission_app, 0)                                   as q_commission_app               -- Q_佣金_app
                          , coalesce(t4.q_coupon_amount_app, 0)                                as q_coupon_amount_app            -- Q_券额_app
                          , coalesce(t4.q_order_cnt_app / t1.uv, 0)                            as q_cr_app                       -- Q_CR_app
                          , coalesce(t4.q_room_night_app, 0) / coalesce(t4.q_order_cnt_app, 0) as q_avg_rn_per_order_app         -- Q_单间夜_app
                          , coalesce(t4.q_commission_app, 0) / coalesce(t4.q_gmv_app, 0)       as q_take_rate_app                -- Q_收益率_app
                          , coalesce(t4.q_coupon_amount_app, 0) / coalesce(t4.q_gmv_app, 0)    as q_subsidy_rate_app             -- Q_券补贴率_app
                          , coalesce(t4.q_gmv_app, 0) / coalesce(t4.q_room_night_app, 0)       as q_adr_app                      -- Q_ADR_app
                          , coalesce(t4.q_coupon_order_cnt_app, 0) /
                            coalesce(t4.q_order_cnt_app, 0)                                    as q_coupon_order_rate_app        -- Q_用券订单占比_app
                          , coalesce(t4.`平台补贴额`, 0)                                       as platform_subsidy_amount        -- 平台补贴额
                          , coalesce(t4.`平台补贴率`, 0)                                       as platform_subsidy_rate          -- 平台补贴率
                          , coalesce(t4.`补贴前佣金率`, 0)                                     as commission_rate_before_subsidy -- 补贴前佣金率
                          , coalesce(t4.`补贴前佣金额`, 0)                                     as commission_after_subsidy       -- 补贴前佣金额
                     from q_uv_info t1
                              left join order_info_app t4
                                        on t1.dt = t4.dt
                                            and t1.ab_group = t4.ab_group)

select dt
     , ab_group
     , uv
     , q_order_user_cnt_app                            -- Q_下单用户_app
     , q_order_cnt_app                                 -- Q_订单量_app
     , q_order_user_cnt_app / uv as U2O
     , q_cr_app                                        -- Q_CR_app
     , q_room_night_app                                -- Q_间夜量_app
     , q_avg_rn_per_order_app                          -- Q_单间夜_app
     , q_gmv_app                                       -- Q_GMV_app
     , q_adr_app                                       -- Q_ADR_app
     , q_commission_app                                -- Q_佣金_app
     , q_take_rate_app                                 -- Q_收益率_app(佣金率)

     , platform_subsidy_amount                         -- 平台补贴额
     , platform_subsidy_rate                           -- 平台补贴率
     , commission_rate_before_subsidy                  -- 补贴前佣金率
     , commission_after_subsidy                        -- 补贴前佣金额

     , q_room_night_app / uv     as room_nights_per_uv -- 单UV间夜
     , q_gmv_app / uv            as gmv_per_uv         -- 单UVGMV
     , q_commission_app / uv     as revenue_per_uv     -- 单UV收益
     , platform_subsidy_amount / uv                    --单UV补贴
     , q_commission_app / q_room_night_app             --单间夜收益
     , platform_subsidy_amount / q_room_night_app      --单间夜补贴

from q_data_info