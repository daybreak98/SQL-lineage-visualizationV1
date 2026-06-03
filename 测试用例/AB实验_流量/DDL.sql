CREATE external TABLE IF NOT EXISTS ihotel_default.dw_ihotel_abtest_index_flow_di
(
    -- 公共维度字段
    order_date              string          COMMENT '业务日期，flow取t1.dt，order/order_base取order_date',
    ab_version              string          COMMENT 'AB实验版本',
    ab_rule_version         string          COMMENT 'AB实验规则版本',
    country_name            string          COMMENT '国家名称',
    city_name               string          COMMENT '城市名称',
    user_type               string          COMMENT '用户类型：新客/老客',
    is_big_order_user       string          COMMENT '是否大单用户：正常用户/大单用户',

    -- flow 指标字段
    uv                      string          COMMENT '查询UV，对应q_uv uv',
    s_all_uv                string          COMMENT '搜索总UV，对应s_all_UV',
    d_s_uv                  string          COMMENT '详情搜索UV，对应d_s_UV',
    b_ds_uv                 string          COMMENT '预订详情搜索UV，对应b_ds_UV',
    o_ds_order              string          COMMENT '订单数，对应o_ds_order',
    s2d                     string          COMMENT '搜索到详情转化率，d_s_UV / s_all_UV',
    d2b                     string          COMMENT '详情到预订转化率，b_ds_UV / d_s_UV',
    b2o                     string          COMMENT '预订到订单转化率，o_ds_order / b_ds_UV',
    s2o                     string          COMMENT '搜索到订单转化率，o_ds_order / s_all_UV',

    -- order 明细字段
    user_id                  string         COMMENT '用户ID',
    orig_device_id           string         COMMENT '原始设备ID，对应a.user_info["orig_device_id"]，通常与user_id不共存',
    init_gmv                 string         COMMENT '初始GMV',
    order_no                 string         COMMENT '订单号',
    room_night               string         COMMENT '间夜数',
    is_user_conpon           string         COMMENT '是否用券，沿用原SQL别名，疑似应为is_user_coupon',
    final_commission_after   string         COMMENT 'Q佣金',
    qyj                      string         COMMENT '权益金，C视角Q佣金组成部分',
    zbj                      string         COMMENT '追补价补，C视角Q佣金组成部分',
    xyb                      string         COMMENT '协议补，C视角Q佣金组成部分',
    qb                       string         COMMENT '券补，C视角Q佣金组成部分',
    coupon_substract_summary string         COMMENT '券抵扣汇总金额',

    -- order_base 聚合字段
    order_no_q              string          COMMENT '订单数，count distinct order_no',
    no_t0_cancel_order_no_q string          COMMENT 'T0未取消订单数'
)
    COMMENT '国际酒店AB实验流量、订单明细、订单基础指标统一宽表'
    PARTITIONED BY
        (
        dt                   string          COMMENT '分区日期，yyyyMMdd',
        type                 string          COMMENT '数据类型分区：flow/order/order_base'
        )
    STORED AS ORC
    TBLPROPERTIES
        (
        'orc.compress' = 'SNAPPY'
        );

