/*
 * 案例 02：交易履约全链路生产脏 SQL
 * 拓扑：订单头 -> 商品明细 -> 库存分配 -> 拣配 -> 包裹运输 -> 签收，
 *       支付、退款、工单作为旁路在订单事实层汇入。
 * 注释中的分号;、\\d、\\s、\\w 和中文内容用于模拟调度平台复制痕迹。
 */
WITH

-- 订单头清洗：创建时间是履约时钟起点; 不包含后续阶段字段
ord_header_clean AS (
    SELECT
        cast(h.order_id AS string) AS order_key,
        cast(h.buyer_id AS string) AS buyer_key,
        cast(h.shop_id AS string) AS shop_key,
        cast(h.create_time AS timestamp) AS order_created_at,
        to_date(h.create_time) AS order_created_date,
        coalesce(h.order_status, 'unknown') AS order_status_code,
        cast(coalesce(h.order_amount, 0) AS decimal(20, 4)) AS order_gross_amount,
        cast(coalesce(h.discount_amount, 0) AS decimal(20, 4)) AS order_discount_amount,
        regexp_extract(coalesce(h.order_no, ''), '([A-Z]+)-(\\d+)', 2) AS order_number_sequence,
        get_json_object(h.order_ext_json, '$.promise.level') AS order_promise_level
    FROM prod_ord.order_header_di h
    WHERE h.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
      AND coalesce(h.test_order_flag, 0) = 0
),

-- 商品明细：每个 SKU 形成独立履约数量; 注释中 SELECT; 不执行
ord_item_clean AS (
    SELECT
        cast(it.order_id AS string) AS item_order_key,
        cast(it.order_item_id AS string) AS order_item_key,
        cast(it.sku_id AS string) AS item_sku_key,
        cast(greatest(coalesce(it.order_quantity, 0), 0) AS bigint) AS ordered_quantity,
        cast(coalesce(it.unit_price, 0) AS decimal(20, 4)) AS item_unit_price,
        cast(greatest(coalesce(it.order_quantity, 0), 0) * coalesce(it.unit_price, 0) AS decimal(20, 4)) AS item_line_amount,
        coalesce(it.fulfillment_mode, 'warehouse') AS item_fulfillment_mode,
        CASE WHEN it.is_gift = 1 THEN 'gift' ELSE 'sale' END AS item_sale_type
    FROM prod_ord.order_item_di it
    WHERE it.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 支付流水：多次支付与撤销在后续按订单聚合; 保留渠道语义
ord_payment_clean AS (
    SELECT
        cast(p.payment_id AS string) AS payment_key,
        cast(p.order_id AS string) AS payment_order_key,
        cast(p.pay_time AS timestamp) AS payment_occurred_at,
        to_date(p.pay_time) AS payment_date,
        upper(coalesce(p.channel_code, 'UNKNOWN')) AS payment_channel_code,
        cast(coalesce(p.paid_amount, 0) AS decimal(20, 4)) AS payment_amount,
        cast(coalesce(p.channel_fee, 0) AS decimal(20, 4)) AS payment_channel_fee,
        CASE WHEN p.payment_status = 'success' THEN 1 ELSE 0 END AS payment_success_flag,
        regexp_replace(coalesce(p.channel_trace_no, ''), '\\s+', '') AS payment_trace_compacted
    FROM prod_ord.payment_transaction_di p
    WHERE p.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 库存分配：仓库和批次决定后续拣配节点; 失败分配仍保留
ord_allocation_clean AS (
    SELECT
        cast(a.allocation_id AS string) AS allocation_key,
        cast(a.order_item_id AS string) AS allocation_item_key,
        cast(a.warehouse_id AS string) AS allocated_warehouse_key,
        cast(a.inventory_batch_id AS string) AS inventory_batch_key,
        cast(a.allocate_time AS timestamp) AS allocated_at,
        cast(coalesce(a.allocated_quantity, 0) AS bigint) AS allocated_quantity,
        coalesce(a.allocation_status, 'unknown') AS allocation_status_code,
        unix_timestamp(a.allocate_time) AS allocation_epoch_seconds
    FROM prod_ord.inventory_allocation_di a
    WHERE a.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 拣货打包：波次号常见空白与转义字符; 做业务清洗而非字段填充
ord_pick_pack_clean AS (
    SELECT
        cast(pp.package_id AS string) AS package_key,
        cast(pp.order_id AS string) AS package_order_key,
        cast(pp.warehouse_id AS string) AS package_warehouse_key,
        cast(pp.pick_start_time AS timestamp) AS pick_started_at,
        cast(pp.pack_finish_time AS timestamp) AS pack_finished_at,
        regexp_replace(coalesce(pp.wave_no, ''), '[\\r\\n\\t\\s]+', '') AS pick_wave_number,
        cast(coalesce(pp.picked_quantity, 0) AS bigint) AS picked_quantity,
        CASE WHEN pp.pack_status = 'completed' THEN 1 ELSE 0 END AS package_completed_flag,
        cast(
            unix_timestamp(pp.pack_finish_time) - unix_timestamp(pp.pick_start_time)
            AS bigint
        ) AS pick_pack_seconds
    FROM prod_ord.pick_pack_package_di pp
    WHERE pp.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 运输事件：JSON、标签展开和中文正则集中在物流事件; 注释有分号;
ord_shipment_event_clean AS (
    SELECT
        cast(se.shipment_event_id AS string) AS shipment_event_key,
        cast(se.package_id AS string) AS shipment_package_key,
        cast(se.carrier_id AS string) AS shipment_carrier_key,
        cast(se.event_time AS timestamp) AS shipment_event_at,
        to_date(se.event_time) AS shipment_event_date,
        coalesce(se.event_code, 'UNKNOWN') AS shipment_event_code,
        regexp_replace(coalesce(se.raw_text, ''), '\\s+', ' ') AS shipment_event_text_normalized,
        regexp_extract(coalesce(se.raw_text, ''), '(到达|发出|揽收|异常)', 1) AS shipment_event_chinese_group,
        get_json_object(se.event_payload, '$.route.node_id') AS shipment_route_node_id,
        get_json_object(se.event_payload, '$.geo.city') AS shipment_event_city,
        shipment_tag_lv.tag_name AS shipment_exception_tag
    FROM prod_ord.shipment_event_di se
    LATERAL VIEW OUTER explode(
        split(coalesce(se.tag_text, ''), ',')
    ) shipment_tag_lv AS tag_name
    WHERE se.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 签收事件：收件人与签收状态构成履约终点; 异常签收进入 SLA
ord_delivery_clean AS (
    SELECT
        cast(d.delivery_id AS string) AS delivery_key,
        cast(d.package_id AS string) AS delivery_package_key,
        cast(d.order_id AS string) AS delivery_order_key,
        cast(d.delivered_time AS timestamp) AS delivered_at,
        to_date(d.delivered_time) AS delivered_date,
        coalesce(d.delivery_status, 'unknown') AS delivery_status_code,
        regexp_replace(coalesce(d.receiver_name, ''), '[^\\u4e00-\\u9fa5A-Za-z·]', '') AS receiver_name_clean,
        CASE WHEN d.delivery_status = 'signed' THEN 1 ELSE 0 END AS delivery_signed_flag,
        CASE WHEN d.is_contactless = 1 THEN 'contactless' ELSE 'standard' END AS delivery_mode
    FROM prod_ord.delivery_result_di d
    WHERE d.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 退款记录：成功退款冲减履约 GMV; 退款原因单独分组
ord_refund_clean AS (
    SELECT
        cast(r.refund_id AS string) AS refund_key,
        cast(r.order_id AS string) AS refund_order_key,
        cast(r.order_item_id AS string) AS refund_item_key,
        cast(r.refund_time AS timestamp) AS refunded_at,
        to_date(r.refund_time) AS refund_date,
        cast(coalesce(r.refund_amount, 0) AS decimal(20, 4)) AS refund_amount,
        regexp_extract(coalesce(r.reason_text, ''), '(未发货|物流|质量|无理由|其他)', 1) AS refund_reason_category,
        CASE WHEN r.refund_status = 'success' THEN 1 ELSE 0 END AS refund_success_flag
    FROM prod_ord.refund_transaction_di r
    WHERE r.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- 售后工单：工单可能早于签收创建; 作为旁路服务质量指标
ord_ticket_clean AS (
    SELECT
        cast(t.ticket_id AS string) AS service_ticket_key,
        cast(t.order_id AS string) AS ticket_order_key,
        cast(t.create_time AS timestamp) AS ticket_created_at,
        cast(t.close_time AS timestamp) AS ticket_closed_at,
        coalesce(t.ticket_type, 'other') AS ticket_type_code,
        coalesce(t.ticket_status, 'open') AS ticket_status_code,
        regexp_replace(coalesce(t.description_text, ''), '[\\r\\n\\t]+', ' ') AS ticket_description_clean,
        cast(
            unix_timestamp(t.close_time) - unix_timestamp(t.create_time)
            AS bigint
        ) AS ticket_resolution_seconds
    FROM prod_ord.service_ticket_di t
    WHERE t.dt >= date_format(date_sub(current_date(), 45), 'yyyyMMdd')
),

-- SKU 维表：重量与温层影响仓配 SLA; 注释里的 DROP; 无效
ord_sku_dimension AS (
    SELECT
        cast(s.sku_id AS string) AS sku_key,
        coalesce(s.sku_name, '未命名商品') AS sku_name,
        coalesce(s.category_level2, 'unknown') AS sku_category_level2,
        cast(coalesce(s.unit_weight_kg, 0) AS decimal(12, 4)) AS sku_unit_weight_kg,
        coalesce(s.temperature_zone, 'normal') AS sku_temperature_zone,
        CASE WHEN s.is_fragile = 1 THEN 1 ELSE 0 END AS sku_fragile_flag,
        to_date(s.updated_at) AS sku_updated_date
    FROM prod_ord.sku_dimension_df s
    WHERE s.is_deleted = 0
),

-- 仓库维表：时区和区域用于 SLA 解释; 不参与支付链
ord_warehouse_dimension AS (
    SELECT
        cast(w.warehouse_id AS string) AS warehouse_key,
        coalesce(w.warehouse_name, '未命名仓') AS warehouse_name,
        coalesce(w.region_code, 'unknown') AS warehouse_region_code,
        coalesce(w.timezone_name, 'Asia/Shanghai') AS warehouse_timezone_name,
        cast(coalesce(w.daily_capacity, 0) AS bigint) AS warehouse_daily_capacity,
        CASE WHEN w.status = 'active' THEN 1 ELSE 0 END AS warehouse_active_flag
    FROM prod_ord.warehouse_dimension_df w
    WHERE w.snapshot_date = date_format(date_sub(current_date(), 1), 'yyyyMMdd')
),

-- 承运商维表：承诺时效按服务等级取值; 注释中包含分号;
ord_carrier_dimension AS (
    SELECT
        cast(ca.carrier_id AS string) AS carrier_key,
        coalesce(ca.carrier_name, '未知承运商') AS carrier_name,
        coalesce(ca.service_level, 'standard') AS carrier_service_level,
        cast(coalesce(ca.promised_hours, 72) AS int) AS carrier_promised_hours,
        cast(coalesce(ca.base_fee, 0) AS decimal(20, 4)) AS carrier_base_fee,
        get_json_object(ca.service_json, '$.coverage.level') AS carrier_coverage_level
    FROM prod_ord.carrier_dimension_df ca
    WHERE ca.status = 'active'
),

-- 商品明细先连接 SKU，再计算重量和易碎品语义
ord_item_enriched AS (
    SELECT
        it.item_order_key AS enriched_item_order_id,
        it.order_item_key AS enriched_order_item_id,
        it.item_sku_key AS enriched_sku_id,
        sku.sku_name AS enriched_sku_name,
        sku.sku_category_level2 AS enriched_category,
        it.ordered_quantity AS enriched_ordered_quantity,
        it.item_line_amount AS enriched_line_amount,
        it.ordered_quantity * sku.sku_unit_weight_kg AS enriched_total_weight_kg,
        sku.sku_temperature_zone AS enriched_temperature_zone,
        sku.sku_fragile_flag AS enriched_fragile_flag
    FROM ord_item_clean it
    LEFT JOIN ord_sku_dimension sku
        ON it.item_sku_key = sku.sku_key
),

-- 订单商品聚合：形成订单级数量、重量和品类集合
ord_item_rollup AS (
    SELECT
        ei.enriched_item_order_id AS item_rollup_order_id,
        count(DISTINCT ei.enriched_order_item_id) AS order_line_count,
        count(DISTINCT ei.enriched_sku_id) AS order_sku_count,
        sum(ei.enriched_ordered_quantity) AS total_ordered_quantity,
        sum(ei.enriched_line_amount) AS total_item_amount,
        sum(ei.enriched_total_weight_kg) AS total_shipment_weight_kg,
        max(ei.enriched_fragile_flag) AS contains_fragile_item_flag,
        collect_set(ei.enriched_temperature_zone) AS required_temperature_zones,
        collect_set(ei.enriched_category) AS purchased_categories
    FROM ord_item_enriched ei
    GROUP BY ei.enriched_item_order_id
),

-- 支付聚合：内联视图先筛成功流水，再按订单汇总
ord_payment_summary AS (
    SELECT
        success_payments.payment_order_key AS paid_order_id,
        min(success_payments.payment_occurred_at) AS first_successful_payment_at,
        max(success_payments.payment_occurred_at) AS last_successful_payment_at,
        sum(success_payments.payment_amount) AS total_successful_payment_amount,
        sum(success_payments.payment_channel_fee) AS total_payment_channel_fee,
        count(DISTINCT success_payments.payment_key) AS successful_payment_count,
        collect_set(success_payments.payment_channel_code) AS successful_payment_channels
    FROM (
        SELECT
            payment_key,
            payment_order_key,
            payment_occurred_at,
            payment_channel_code,
            payment_amount,
            payment_channel_fee
        FROM ord_payment_clean
        WHERE payment_success_flag = 1
    ) success_payments
    GROUP BY success_payments.payment_order_key
),

-- 分配阶段：库存分配连接仓库，计算下单到分配耗时
ord_allocation_stage AS (
    SELECT
        a.allocation_key AS stage_allocation_id,
        item.item_order_key AS stage_allocation_order_id,
        a.allocation_item_key AS stage_allocation_item_id,
        a.allocated_warehouse_key AS stage_warehouse_id,
        wh.warehouse_name AS stage_warehouse_name,
        wh.warehouse_region_code AS stage_warehouse_region,
        a.allocated_at AS stage_allocated_at,
        a.allocated_quantity AS stage_allocated_quantity,
        a.allocation_status_code AS stage_allocation_status,
        wh.warehouse_daily_capacity AS stage_warehouse_capacity
    FROM ord_allocation_clean a
    INNER JOIN ord_item_clean item
        ON a.allocation_item_key = item.order_item_key
    LEFT JOIN ord_warehouse_dimension wh
        ON a.allocated_warehouse_key = wh.warehouse_key
),

-- 拣配阶段：订单商品、库存分配与包裹形成顺序链
ord_package_stage AS (
    SELECT
        pp.package_key AS stage_package_id,
        pp.package_order_key AS stage_package_order_id,
        pp.package_warehouse_key AS stage_package_warehouse_id,
        min(alloc.stage_allocated_at) AS first_allocation_at,
        pp.pick_started_at AS stage_pick_started_at,
        pp.pack_finished_at AS stage_pack_finished_at,
        pp.pick_pack_seconds AS stage_pick_pack_seconds,
        pp.picked_quantity AS stage_picked_quantity,
        sum(alloc.stage_allocated_quantity) AS stage_allocated_quantity,
        CASE
            WHEN pp.picked_quantity >= sum(alloc.stage_allocated_quantity) THEN 1
            ELSE 0
        END AS stage_pick_complete_flag
    FROM ord_pick_pack_clean pp
    LEFT JOIN ord_allocation_stage alloc
        ON pp.package_order_key = alloc.stage_allocation_order_id
       AND pp.package_warehouse_key = alloc.stage_warehouse_id
    WHERE pp.package_completed_flag = 1
    GROUP BY
        pp.package_key,
        pp.package_order_key,
        pp.package_warehouse_key,
        pp.pick_started_at,
        pp.pack_finished_at,
        pp.pick_pack_seconds,
        pp.picked_quantity
),

-- 运输阶段：运输事件按包裹排序，首发与最新节点同时保留
ord_transport_stage AS (
    SELECT
        se.shipment_package_key AS stage_transport_package_id,
        max(se.shipment_carrier_key) AS stage_carrier_id,
        max(ca.carrier_name) AS stage_carrier_name,
        max(ca.carrier_service_level) AS stage_carrier_service_level,
        max(ca.carrier_promised_hours) AS stage_promised_hours,
        min(se.shipment_event_at) AS first_shipment_event_at,
        max(se.shipment_event_at) AS latest_shipment_event_at,
        count(1) AS shipment_event_count,
        count(DISTINCT se.shipment_route_node_id) AS traversed_route_node_count,
        collect_set(se.shipment_event_code) AS observed_shipment_codes,
        max(CASE WHEN se.shipment_exception_tag <> '' THEN 1 ELSE 0 END) AS shipment_exception_flag
    FROM ord_shipment_event_clean se
    LEFT JOIN ord_carrier_dimension ca
        ON se.shipment_carrier_key = ca.carrier_key
    GROUP BY se.shipment_package_key
),

-- 签收阶段：包裹链连接运输与签收，形成完整包裹 SLA
ord_delivery_stage AS (
    SELECT
        pkg.stage_package_id AS delivered_package_id,
        pkg.stage_package_order_id AS delivered_order_id,
        pkg.first_allocation_at AS delivered_first_allocation_at,
        pkg.stage_pick_started_at AS delivered_pick_started_at,
        pkg.stage_pack_finished_at AS delivered_pack_finished_at,
        trans.first_shipment_event_at AS delivered_first_shipment_at,
        d.delivered_at AS delivered_signed_at,
        trans.stage_carrier_name AS delivered_carrier_name,
        trans.stage_promised_hours AS delivered_promised_hours,
        trans.shipment_exception_flag AS delivered_exception_flag,
        cast(
            (unix_timestamp(d.delivered_at) - unix_timestamp(trans.first_shipment_event_at)) / 3600.0
            AS decimal(20, 4)
        ) AS delivered_transit_hours,
        d.delivery_signed_flag AS delivered_success_flag
    FROM ord_package_stage pkg
    LEFT JOIN ord_transport_stage trans
        ON pkg.stage_package_id = trans.stage_transport_package_id
    LEFT JOIN ord_delivery_clean d
        ON pkg.stage_package_id = d.delivery_package_key
),

-- 退款汇总：形成订单净履约金额旁路
ord_refund_summary AS (
    SELECT
        refund_order_key AS summarized_refund_order_id,
        sum(CASE WHEN refund_success_flag = 1 THEN refund_amount ELSE 0 END) AS successful_refund_amount,
        count(DISTINCT CASE WHEN refund_success_flag = 1 THEN refund_key END) AS successful_refund_count,
        max(refunded_at) AS latest_refund_at,
        collect_set(refund_reason_category) AS refund_reason_categories
    FROM ord_refund_clean
    GROUP BY refund_order_key
),

-- 工单汇总：相关子查询排除无订单头的孤儿工单
ord_service_summary AS (
    SELECT
        ticket.ticket_order_key AS summarized_ticket_order_id,
        count(DISTINCT ticket.service_ticket_key) AS service_ticket_count,
        avg(greatest(ticket.ticket_resolution_seconds, 0)) AS average_ticket_resolution_seconds,
        max(CASE WHEN ticket.ticket_status_code <> 'closed' THEN 1 ELSE 0 END) AS open_ticket_flag,
        collect_set(ticket.ticket_type_code) AS service_ticket_types
    FROM ord_ticket_clean ticket
    WHERE EXISTS (
        SELECT
            1
        FROM ord_header_clean header_probe
        WHERE header_probe.order_key = ticket.ticket_order_key
    )
    GROUP BY ticket.ticket_order_key
),

-- 订单履约事实：顺序阶段和三条旁路在订单粒度汇合
ord_fulfillment_fact AS (
    SELECT
        h.order_key AS fulfillment_order_id,
        h.buyer_key AS fulfillment_buyer_id,
        h.order_created_at AS fulfillment_created_at,
        pay.first_successful_payment_at AS fulfillment_paid_at,
        min(delivery.delivered_first_allocation_at) AS fulfillment_allocated_at,
        min(delivery.delivered_pick_started_at) AS fulfillment_pick_started_at,
        min(delivery.delivered_first_shipment_at) AS fulfillment_shipped_at,
        max(delivery.delivered_signed_at) AS fulfillment_delivered_at,
        items.total_ordered_quantity AS fulfillment_ordered_quantity,
        items.total_shipment_weight_kg AS fulfillment_weight_kg,
        pay.total_successful_payment_amount AS fulfillment_paid_amount,
        coalesce(refund.successful_refund_amount, 0) AS fulfillment_refund_amount,
        pay.total_successful_payment_amount - coalesce(refund.successful_refund_amount, 0) AS fulfillment_net_gmv,
        max(delivery.delivered_exception_flag) AS fulfillment_exception_flag,
        max(delivery.delivered_success_flag) AS fulfillment_delivery_success_flag,
        coalesce(service.service_ticket_count, 0) AS fulfillment_ticket_count
    FROM ord_header_clean h
    LEFT JOIN ord_item_rollup items
        ON h.order_key = items.item_rollup_order_id
    LEFT JOIN ord_payment_summary pay
        ON h.order_key = pay.paid_order_id
    LEFT JOIN ord_delivery_stage delivery
        ON h.order_key = delivery.delivered_order_id
    LEFT JOIN ord_refund_summary refund
        ON h.order_key = refund.summarized_refund_order_id
    LEFT JOIN ord_service_summary service
        ON h.order_key = service.summarized_ticket_order_id
    GROUP BY
        h.order_key,
        h.buyer_key,
        h.order_created_at,
        pay.first_successful_payment_at,
        items.total_ordered_quantity,
        items.total_shipment_weight_kg,
        pay.total_successful_payment_amount,
        refund.successful_refund_amount,
        service.service_ticket_count
),

-- 阶段事件流：将顺序时间点展开为可比较的事件集合
ord_stage_event_stream AS (
    SELECT
        fulfillment_order_id AS stage_order_id,
        fulfillment_created_at AS stage_event_at,
        'created' AS stage_name,
        1 AS stage_ordinal
    FROM ord_fulfillment_fact
    UNION ALL
    SELECT
        fulfillment_order_id AS stage_order_id,
        fulfillment_paid_at AS stage_event_at,
        'paid' AS stage_name,
        2 AS stage_ordinal
    FROM ord_fulfillment_fact
    UNION ALL
    SELECT
        fulfillment_order_id AS stage_order_id,
        fulfillment_allocated_at AS stage_event_at,
        'allocated' AS stage_name,
        3 AS stage_ordinal
    FROM ord_fulfillment_fact
    UNION ALL
    SELECT
        fulfillment_order_id AS stage_order_id,
        fulfillment_pick_started_at AS stage_event_at,
        'picking' AS stage_name,
        4 AS stage_ordinal
    FROM ord_fulfillment_fact
    UNION ALL
    SELECT
        fulfillment_order_id AS stage_order_id,
        fulfillment_shipped_at AS stage_event_at,
        'shipped' AS stage_name,
        5 AS stage_ordinal
    FROM ord_fulfillment_fact
    UNION ALL
    SELECT
        fulfillment_order_id AS stage_order_id,
        fulfillment_delivered_at AS stage_event_at,
        'delivered' AS stage_name,
        6 AS stage_ordinal
    FROM ord_fulfillment_fact
),

-- 阶段窗口：计算相邻阶段耗时和累计履约时长
ord_stage_timing AS (
    SELECT
        stream.stage_order_id AS timing_order_id,
        stream.stage_name AS timing_stage_name,
        stream.stage_ordinal AS timing_stage_ordinal,
        stream.stage_event_at AS timing_stage_event_at,
        lag(stream.stage_event_at, 1) OVER (
            PARTITION BY stream.stage_order_id
            ORDER BY stream.stage_ordinal
        ) AS previous_stage_event_at,
        cast(
            unix_timestamp(stream.stage_event_at)
            - unix_timestamp(
                lag(stream.stage_event_at, 1) OVER (
                    PARTITION BY stream.stage_order_id
                    ORDER BY stream.stage_ordinal
                )
            )
            AS bigint
        ) AS seconds_from_previous_stage,
        cast(
            unix_timestamp(stream.stage_event_at)
            - unix_timestamp(
                min(stream.stage_event_at) OVER (
                    PARTITION BY stream.stage_order_id
                )
            )
            AS bigint
        ) AS seconds_from_order_start,
        row_number() OVER (
            PARTITION BY stream.stage_order_id
            ORDER BY stream.stage_ordinal DESC
        ) AS latest_available_stage_rank
    FROM ord_stage_event_stream stream
    WHERE stream.stage_event_at IS NOT NULL
),

-- SLA 汇总：最终按订单输出阶段完整性和超时情况
ord_sla_rollup AS (
    SELECT
        timing.timing_order_id AS sla_order_id,
        count(DISTINCT timing.timing_stage_name) AS completed_stage_count,
        max(timing.timing_stage_ordinal) AS latest_stage_ordinal,
        max(timing.seconds_from_order_start) AS end_to_end_seconds,
        max(CASE WHEN timing.seconds_from_previous_stage < 0 THEN 1 ELSE 0 END) AS reverse_time_flag,
        max(CASE WHEN timing.seconds_from_previous_stage > 172800 THEN 1 ELSE 0 END) AS stage_delay_flag,
        collect_set(timing.timing_stage_name) AS completed_stage_names
    FROM ord_stage_timing timing
    GROUP BY timing.timing_order_id
),

-- 最终履约宽表：事实金额、服务质量和 SLA 汇总
ord_final_fulfillment_metrics AS (
    SELECT
        fact.fulfillment_order_id AS final_order_id,
        fact.fulfillment_buyer_id AS final_buyer_id,
        to_date(fact.fulfillment_created_at) AS final_order_date,
        fact.fulfillment_ordered_quantity AS final_ordered_quantity,
        fact.fulfillment_weight_kg AS final_shipment_weight_kg,
        fact.fulfillment_paid_amount AS final_paid_amount,
        fact.fulfillment_refund_amount AS final_refund_amount,
        fact.fulfillment_net_gmv AS final_net_gmv,
        fact.fulfillment_exception_flag AS final_exception_flag,
        fact.fulfillment_delivery_success_flag AS final_delivery_success_flag,
        fact.fulfillment_ticket_count AS final_ticket_count,
        sla.completed_stage_count AS final_completed_stage_count,
        sla.latest_stage_ordinal AS final_latest_stage_ordinal,
        sla.end_to_end_seconds AS final_end_to_end_seconds,
        sla.reverse_time_flag AS final_reverse_time_flag,
        sla.stage_delay_flag AS final_stage_delay_flag,
        CASE
            WHEN fact.fulfillment_delivery_success_flag = 1
             AND sla.stage_delay_flag = 0 THEN 'on_time'
            WHEN fact.fulfillment_delivery_success_flag = 1 THEN 'delayed'
            ELSE 'in_progress'
        END AS final_fulfillment_state
    FROM ord_fulfillment_fact fact
    LEFT JOIN ord_sla_rollup sla
        ON fact.fulfillment_order_id = sla.sla_order_id
)

SELECT
    'order_fulfillment' AS lineage_case_name,
    final.final_order_id AS order_id,
    final.final_buyer_id AS buyer_id,
    final.final_order_date AS order_date,
    final.final_ordered_quantity AS ordered_quantity,
    final.final_shipment_weight_kg AS shipment_weight_kg,
    final.final_paid_amount AS paid_amount,
    final.final_refund_amount AS refund_amount,
    final.final_net_gmv AS fulfilled_net_gmv,
    final.final_completed_stage_count AS completed_stage_count,
    final.final_latest_stage_ordinal AS latest_stage_ordinal,
    final.final_end_to_end_seconds AS end_to_end_seconds,
    final.final_ticket_count AS service_ticket_count,
    final.final_exception_flag AS shipment_exception_flag,
    final.final_stage_delay_flag AS stage_delay_flag,
    final.final_fulfillment_state AS fulfillment_state,
    current_timestamp() AS corpus_evaluated_at
FROM ord_final_fulfillment_metrics final
WHERE final.final_order_id IS NOT NULL;
