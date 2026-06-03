insert overwrite table ihotel_default.dwd_abtest_rule_info_di partition (dt='${zdt.addDay(-1).format("yyyy-MM-dd")}',user_id_type)
select
    ab_exp_id
     ,ab_version
     ,ab_rule_version
     ,device_id as ab_exp_value
     ,user_id_type
from
    (
        select
            ab_exp_id,
            ab_version,
            ab_rule_version,
            case ab_shuntbase
                when 'APP_UID' then 'uid'
                when 'USERID'  then 'user_id'
                end as user_id_type
        from ods_abtest_rule_info
        where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
          and source = 'hotel'
          and ab_shuntbase in ('APP_UID','USERID')
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
group by 1,2,3,4,5