drop table ihotel_default.dw_ihotel_abtest_detail_flow_order_di;
create external table if not exists ihotel_default.dw_ihotel_abtest_detail_flow_order_di (
                                                                                             order_date string comment '统计日期，来自业务订单日期',
                                                                                             ab_exp_id string comment 'AB实验ID',
                                                                                             ab_exp_value string comment 'AB实验命中值',
                                                                                             ab_version string comment 'AB实验版本',
                                                                                             ab_rule_version string comment 'AB实验规则版本',
                                                                                             country_name string comment '国家',
                                                                                             city_name string comment '城市',
                                                                                             user_type string comment '用户类型：新客/老客',
                                                                                             is_big_order_user string comment '是否大单用户：正常用户/大单用户',

                                                                                             user_id string comment '用户ID，用于后续计算UV类不可累加指标',
                                                                                             search_pv string comment '搜索PV，用于后续计算搜索UV',
                                                                                             detail_pv string comment '详情PV，用于后续计算详情UV、搜后看详情UV',
                                                                                             booking_pv string comment '预订页PV，用于后续计算预订UV、搜后看详情再到预订UV',
                                                                                             order_pv string comment '下单PV，保留用户行为过程字段',
                                                                                             order_no string comment '订单号，用于后续计算订单量类不可累加指标',

                                                                                             column1 string comment '占位字段1',
                                                                                             column2 string comment '占位字段2',
                                                                                             column3 string comment '占位字段3',
                                                                                             column4 string comment '占位字段4',
                                                                                             column5 string comment '占位字段5',

                                                                                             q_commission_app string comment 'APP订单佣金',
                                                                                             q_commission_c_view_app string comment 'APP订单C视角佣金',
                                                                                             q_gmv_app string comment 'APP订单GMV',
                                                                                             q_coupon_amount_app string comment 'APP订单券补贴金额',
                                                                                             q_order_cnt_app string comment 'APP订单量',
                                                                                             q_order_user_cnt_app string comment 'APP下单用户数',
                                                                                             q_room_night_app string comment 'APP间夜量',
                                                                                             q_coupon_order_cnt_app string comment 'APP用券订单量',
                                                                                             order_no_q string comment 'APP有效订单量，取消率分母',
                                                                                             no_t0_cancel_order_no_q string comment 'APP非T0取消订单量，取消率分子辅助项'
)
    comment 'AB实验流量/订单明细宽表，同表存储 flow/order/order_base 等不同类型分区；flow分区落用户行为明细字段，指标查询时再聚合计算'
    partitioned by (
        dt string comment '数据分区日期，与源表 dt 一致',
        type string comment '数据类型分区：flow/order/order_base',
        user_id_type string comment '用户ID类型'
        )
    stored as orc;

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_commission_app order_commission_app string comment 'order分区：单订单APP佣金，查询时sum计算佣金';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_commission_c_view_app order_commission_c_view_app string comment 'order分区：单订单APP C视角佣金，查询时sum计算C视角佣金';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_gmv_app order_gmv_app string comment 'order分区：单订单GMV，查询时sum计算GMV';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_coupon_amount_app order_coupon_amount_app string comment 'order分区：单订单券补贴金额，查询时sum计算券额';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_order_cnt_app order_no_app string comment 'order分区：订单号，查询时count distinct计算订单量';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_order_user_cnt_app order_user_id string comment 'order分区：下单用户ID，查询时count distinct计算生单用户数';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_room_night_app order_room_night_app string comment 'order分区：单订单间夜量，查询时sum计算间夜量';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column q_coupon_order_cnt_app coupon_order_no_app string comment 'order分区：用券订单号，非用券为空，查询时count distinct计算用券订单量';


msck repair table ihotel_default.dw_ihotel_abtest_detail_flow_order_di;

drop table ihotel_default.dw_ihotel_abtest_detail_flow_di;
create table if not exists ihotel_default.dw_ihotel_abtest_detail_flow_di (
                                                                              ab_exp_id          string comment 'AB实验ID',
                                                                              ab_version         string comment 'AB实验版本/实验组',
                                                                              ab_rule_version    string comment 'AB实验规则版本',
                                                                              ab_exp_value       string comment '实验分流值，当前写数逻辑来自 device_id',

                                                                              page_type          string comment '页面类型，常见取值：s搜索页/d详情页/b预订页/o订单页',
                                                                              channel            string comment '渠道',
                                                                              newolduser         string comment '新老用户标识',

                                                                              hotel_grade        string comment '酒店星级/高低星标识；由写数语句中的 highlowstar 写入',

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
    stored as orc


alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column column1 order_country_name string comment 'flow分区：订单侧国家，o_ds_order订单侧过滤字段';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column column2 order_city_name string comment 'flow分区：订单侧城市，o_ds_order订单侧过滤字段';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column column3 order_user_type string comment 'flow分区：订单侧用户类型：新客/老客，o_ds_order订单侧过滤字段';

alter table ihotel_default.dw_ihotel_abtest_detail_flow_order_di
    change column column4 order_is_big_order_user string comment 'flow分区：订单侧是否大单用户：正常用户/大单用户，o_ds_order订单侧过滤字段';