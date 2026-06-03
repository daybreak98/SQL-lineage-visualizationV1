insert overwrite table ihotel_default.dw_ihotel_abtest_index_searchlist_di partition (dt='${zdt.addDay(-1).format("yyyy-MM-dd")}', type = 'order',user_id_type='user_id')

select
    ab_exp_id,
    ab_version,
    ab_rule_version,
    ab_exp_value,
    null as datee,
    null as search_request_uid,
    null as hotel_seq,
    null as user_id,
    null as detail_log_id,
    null as detail_device_id,
    null as device_id,
    null as orig_device_id,
    null as rank,
    null as sort_price,
    null as order_info_device_id,
    null as is_display,
    null as render_price,
    null as qpayprice,
    null as cpayprice,
    null as is_query,
    null as is_same_city,
    null as is_filter,
    null as intention,
    null as suggest_type,
    null as country_name,
    null as province_name,
    null as checkin_date,
    null as checkout_date,
    null as log_datetime,
    null as total_hotels,
    null as intention1,
    null as country,
    null as product_range,
    null as new_render_price,
    null as new_sort_price,
    null as order_info_order_no,
    null as click_rank,
    null as order_rank,
    null as medal_type,
    null as show_commission,
    null as sort_v2_price,
    null as rn,
    null as newolduser,
    null as highlowstar,
    order_datee,
    order_orig_device_id,
    order_user_id,
    order_order_no,
    order_hotel_seq,
    order_room_night,
    order_checkin_date,
    order_checkout_date,
    order_init_gmv,
    order_order_commission
from
    (
        select
            ab_exp_id
             ,ab_version
             ,ab_rule_version
             ,device_id as ab_exp_value
        from
            (
                select
                    ab_exp_id,
                    ab_version,
                    ab_rule_version
                from ods_abtest_rule_info
                where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
                  and source = 'hotel'
                  and ab_shuntbase='USERID'
            ) rule
                join
            (
                select  expid, version, ruleversion, clientcode as device_id, dt,logdate
                from ods_abtest_sdk_log_endtime_hotel
                where dt='${zdt.addDay(-1).format("yyyyMMdd")}'
                  and clientcode is not NULL
                  and expid is not NULL
                  and version is not NULL
                  and ruleversion is not NULL
                  and expid !=''
                  and version !=''
                  and clientcode not in ('0','00000000','00000000000000','000000000000000','0000000000000000','0000000000000000000000000000000000000000','','ctrip','elong','352284040670808')
                  and (clientcode not like 'tc%' and clientcode not like 'wx%' and clientcode not like 'pd%')
            )ab
            on ab.expid=rule.ab_exp_id and ab.version=rule.ab_version and ab.ruleversion=rule.ab_rule_version
        group by 1,2,3,4
    ) a
        left join (
        select
            cast(a.order_date as string) as order_datee,
            cast(a.user_info['orig_device_id'] as string) as order_orig_device_id,
            cast(a.user_id as string) as order_user_id,
            cast(a.order_no as string) as order_order_no,
            cast(a.hotel_seq as string) as order_hotel_seq,
            cast(a.room_night as string) as order_room_night,
            cast(a.checkin_date as string) as order_checkin_date,
            cast(a.checkout_date as string) as order_checkout_date,
            cast(a.init_gmv as string) as order_init_gmv,
            cast(
                    case
                        when batch_series like '%23base_ZK_728810%'
                            or batch_series like '%23extra_ZK_ce6f99%'
                            then init_commission_after
                            + nvl(split(coupon_info['23base_ZK_728810'], '_')[1], 0)
                            + nvl(split(coupon_info['23extra_ZK_ce6f99'], '_')[1], 0)
                            + nvl(ext_plat_certificate, 0)
                        else init_commission_after + nvl(ext_plat_certificate, 0)
                        end as string
            ) as order_order_commission
        from default.mdw_order_v3_international a
                 inner join (
            select order_info_order_no
            from ihotel_default.dw_ihotel_abtest_detail_searchlist_baseinfo
            where dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
              and order_info_order_no is not null
            group by 1
        ) b
                            on a.order_no = b.order_info_order_no
        where a.dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
          and (a.province_name in ('台湾', '澳门', '香港') or a.country_name != '中国')
          and a.terminal_channel_type = 'app'
          and a.order_status not in ('CANCELLED', 'REJECTED')
          and a.is_valid = '1'
          and substr(cast(a.order_date as string), 1, 10) = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
        group by 1,2,3,4,5,6,7,8,9,10
    ) order
on a.ab_exp_value = order.order_user_id
