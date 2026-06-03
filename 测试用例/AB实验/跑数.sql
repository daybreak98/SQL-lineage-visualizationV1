drop table ihotel_default.dw_ihotel_abtest_detail_flow_di;
create table if not exists ihotel_default.dw_ihotel_abtest_detail_flow_di (
                                                                              ab_exp_id          string comment 'AB实验ID',
                                                                              ab_version         string comment 'AB实验版本/实验组',
                                                                              ab_rule_version    string comment 'AB实验规则版本',
                                                                              ab_exp_value       string comment '实验分流值，当前写数逻辑来自 device_id',

                                                                              page_type          string comment '页面类型，常见取值：s搜索页/d详情页/b预订页/o订单页',
                                                                              channel            string comment '渠道',
                                                                              newolduser         string comment '新老用户标识',

                                                                              highlowstar        string comment '酒店星级/高低星标识；由写数语句中的 highlowstar 写入',

                                                                              pv                 bigint comment 'PV，当前写数逻辑为 count(distinct data.log_id)',

                                                                              city_code          string comment '城市编码',
                                                                              city_name          string comment '城市名称',
                                                                              country_name       string comment '国家名称'
)
    comment '国际酒店AB实验流量明细表，按实验、页面、渠道、人群、城市等维度沉淀PV及分流明细'
    partitioned by (
        dt                 string comment '日期分区，格式 yyyy-MM-dd',
        user_id_type       string comment '用户ID类型，如 uid/user_id/device_id'
        )
    stored as orc;
msck repair table ihotel_default.dw_ihotel_abtest_detail_flow_di;