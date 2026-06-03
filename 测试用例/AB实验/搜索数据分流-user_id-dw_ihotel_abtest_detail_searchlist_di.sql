

insert overwrite table ihotel_default.dw_ihotel_abtest_detail_searchlist_di partition (dt='${zdt.addDay(-1).format("yyyy-MM-dd")}',user_id_type='user_id')
select
    a.ab_exp_id,
    a.ab_version,
    a.ab_rule_version,
    a.ab_exp_value,

    datee,
    search_request_uid,
    hotel_seq,
    user_id,
    detail_log_id,
    detail_device_id,
    device_id,
    orig_device_id,
    rank,
    sort_price,
    order_info_device_id,
    is_display,
    render_price,
    qpayprice,
    cpayprice,
    is_query,
    is_same_city,
    is_filter,
    intention,
    suggest_type,
    country_name,
    province_name,
    checkin_date,
    checkout_date,
    log_datetime,
    total_hotels,
    intention1,
    country,
    product_range,
    new_render_price,
    new_sort_price,
    order_info_order_no,
    click_rank,
    order_rank,
    medal_type,
    show_commission,
    sort_v2_price,
    rn,
    newolduser,
    highlowstar
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
            user_id as ab_exp_value,

            datee,
            search_request_uid,
            hotel_seq,
            user_id,
            detail_log_id,
            detail_device_id,
            device_id,
            orig_device_id,
            rank,
            sort_price,
            order_info_device_id,
            is_display,
            render_price,
            qpayprice,
            cpayprice,
            is_query,
            is_same_city,
            is_filter,
            intention,
            suggest_type,
            country_name,
            province_name,
            checkin_date,
            checkout_date,
            log_datetime,
            total_hotels,
            intention1,
            country,
            product_range,
            new_render_price,
            new_sort_price,
            order_info_order_no,
            click_rank,
            order_rank,
            medal_type,
            show_commission,
            sort_v2_price,
            rn,
            newolduser,
            case
                when (cast(hotel_grade as int) >= 4) then 'high_star'
                when (cast(hotel_grade as int) = 3) then 'middle_star'
                else 'low_star'
                end as highlowstar
        from
            ihotel_default.dw_ihotel_abtest_detail_searchlist_baseinfo
        where
            dt = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
    ) data
                  on a.ab_exp_value = data.ab_exp_value
