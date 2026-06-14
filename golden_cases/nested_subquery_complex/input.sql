SELECT
    count(distinct order_no)
from
    (
        select
            order_no
             ,partner_order_no
             ,user_id
             ,user_type
             ,is_valid
             ,if(channel = 'smart_app', 'wechat', channel) as channel
             ,corp_name
             ,order_date
             ,order_time
             ,commission_order_time
             ,checkin_date
             ,checkout_date
             ,stay_days
             ,room_night
             ,room_num
             ,pre_booking_days
             ,checkin_type
             ,checkin_checkout
             ,hotel_seq
             ,hotel_name
             ,cast(hotel_grade as int) as hotel_grade
             ,city_code
             ,city_name
             ,province_name
             ,country_name
             ,area
             ,cast(top_city as int) as top_city
             ,partner_hotel_id
             ,physical_room_id
             ,order_status
             ,pay_type
             ,pay_status
             ,presale
             ,qta_supplier_id
             ,wrapper_id
             ,wrapper_name
             ,cast(vendor_id as int) as vendor_id
             ,qta_product_id
             ,init_gmv
             ,commission
             ,bp_realized
             ,adr_range
             ,coupon_tag
             ,coupon_amount
             ,coupon_batch_nos
             ,points_deduction_amount_tag
             ,follow_amount
             ,beat_amount
             ,beat_ids
             ,exchange_amount
             ,exchange_amount_duobei
             ,exchange_amount_feiduobei
             ,frame_amount
             ,settle_base_price_diff
             ,voucher_pack_price
             ,commission_corp
             ,room_fee_corp
             ,follow_price_amount
             ,hour as h
             ,concat(dt, ' ', hour, ':00:00') as order_update_time
        from
            (
                select
                    order_no
                     ,partner_order_no
                     ,a.user_id
                     ,case
                          when y_hi_order_user.user_id is not null then '老客'
                          when b.min_order_date is not null and a.order_date = b.min_order_date then '新客'
                          when b.min_order_date is not null and a.order_date <> b.min_order_date then '老客'
                          when b_pre2.user_id is not null then '老客'
                          else '新客'
                    end as user_type
                     ,is_valid
                     ,terminal_channel as channel
                     ,corp_name
                     ,order_date
                     ,order_time
                     ,coalesce(commission_map['order_time'], order_time) as commission_order_time
                     ,checkin_date
                     ,checkout_date
                     ,datediff(checkout_date, checkin_date) as stay_days
                     ,coalesce(cast(room_night as int), 0) as room_night
                     ,coalesce(cast(room_num as int), 0) as room_num
                     ,datediff(checkin_date, order_date) as pre_booking_days
                     ,case
                          when datediff(checkout_date, checkin_date) = 1 and room_num = 1 then 1
                          when datediff(checkout_date, checkin_date) > 1 and room_num = 1 then 2
                          when datediff(checkout_date, checkin_date) = 1 and room_num > 1 then 3
                          else 4
                    end as checkin_type
                     ,concat_ws('~', checkin_date, checkout_date) as checkin_checkout
                     ,hotel_seq
                     ,hotel_name
                     ,star as hotel_grade
                     ,city_code
                     ,city_name
                     ,province_name
                     ,a.country_name
                     ,case
                          when province_name in ('香港','澳门') then '港澳'
                          when province_name in ('台湾') then 'APAC'
                          when a.country_name in ('日本','泰国','韩国','马来西亚','新加�?) then 'Top5'
                          when a.country_name in ('老挝','柬埔�?,'缅甸','印度尼西�?,'菲律�?,'越南') then 'APAC'
                          when area = 'Oceania' then 'APAC'
                          when region = 'APAC' then 'APAC'
                          when region = 'Americas' then '美洲'
                          when region = 'Europe' then '欧洲'
                          when region = 'ROW' then '其他'
                          else '其他'
                    end as area
                     ,case when (a.country_name = '日本' and city_name in ('东京','大阪','京都')) or (a.country_name = '韩国' and city_name in ('首尔','济州�?,'釜山')) then 1 else 0 end as top_city
                     ,partner_hotel_id
                     ,room_id as physical_room_id
                     ,order_status
                     ,pay_type
                     ,pay_status
                     ,is_apoint as presale
                     ,supplier_id as qta_supplier_id
                     ,supplier_code as wrapper_id
                     ,supplier_name as wrapper_name
                     ,vendor_id
                     ,sroom_id as qta_product_id
                     ,init_gmv
                     ,coalesce(cast(commission_corp + commission_map['settle_base_price_diff'] as double), 0) as commission
                     ,coalesce(cast(commission_map['bp_realized'] as double), 0) as bp_realized
                     ,case when init_gmv / room_night > 0 and init_gmv / room_night <= 200 then 1 when init_gmv / room_night > 200 and init_gmv / room_night <= 400 then 2 when init_gmv / room_night > 400 then 3 end as adr_range
                     ,if(plat_certificate > 0, 1, 0) as coupon_tag
                     ,coalesce(cast(commission_map['coupon_amount'] as double), 0) as coupon_amount
                     ,batch_series as coupon_batch_nos
                     ,if(points_deduction_amount > 0, 1, 0) as points_deduction_amount_tag
                     ,cast(coalesce(follow_price_amount, 0) as double) as follow_amount
                     ,coalesce(cast(coalesce(commission_map['beat_amount'], 0) as double), 0) as beat_amount
                     ,beat_ids
                     ,cast(coalesce(commission_map['exchange_amount'], 0) as double) as exchange_amount
                     ,cast(coalesce(commission_map['exchange_amount_duobei'], 0) as double) as exchange_amount_duobei
                     ,cast(coalesce(commission_map['exchange_amount_feiduobei'], 0) as double) as exchange_amount_feiduobei
                     ,cast(coalesce(commission_map['frame_amount_v2'], 0) + coalesce(commission_map['framework_amount'], 0) as double) as frame_amount
                     ,coalesce(cast(commission_map['settle_base_price_diff'] as double), 0) as settle_base_price_diff
                     ,cast(coalesce(commission_map['voucher_pack_price'], 0) as double) as voucher_pack_price
                     ,cast(commission_corp + coalesce(commission_map['settle_base_price_diff'], 0) as double) as commission_corp
                     ,room_fee_corp
                     ,case when supplier_code in ('hca9008oc4l','hca908oh60s','hca908oh60t') then coalesce(cast(follow_price_amount as double), 0) else cast(0 as double) end as follow_price_amount
                     ,dt
                     ,hour
                from
                    (
                        select
                            order_no
                             ,partner_order_no
                             ,user_id
                             ,order_date
                             ,is_valid
                             ,corp_name
                             ,order_time
                             ,commission_map
                             ,checkin_date
                             ,checkout_date
                             ,room_night
                             ,room_num
                             ,hotel_seq
                             ,hotel_name
                             ,star
                             ,city_code
                             ,city as city_name
                             ,country as country_name
                             ,province as province_name
                             ,partner_hotel_id
                             ,room_id
                             ,order_status
                             ,pay_type
                             ,pay_status
                             ,is_apoint
                             ,supplier_id
                             ,supplier_code
                             ,supplier_name
                             ,vendor_id
                             ,sroom_id
                             ,init_gmv
                             ,beat_ids
                             ,batch_series
                             ,ext_plat_certificate
                             ,plat_certificate
                             ,points_deduction_amount
                             ,follow_price_amount
                             ,commission_corp
                             ,room_fee_corp
                             ,terminal_channel
                             ,row_number() over(partition by dt, order_no order by hour desc) as rn
                             ,if(commission_map['order_date'] is null, order_date, commission_map['order_date']) as order_date1
                             ,dt
                             ,hour
                        from ihotel_default.dw_qunar_three_order_detail_intl_hi_back
                        where dt = '2026-06-07'
                          and hour = '00'
                          and if(commission_map['order_date'] is null, order_date, commission_map['order_date']) = dt
                    ) a
                        left join
                    (
                        select user_id, min(order_date) as min_order_date
                        from default.mdw_order_v3_international
                        where dt = '20260606' and (province_name in ('台湾','澳门','香港') or country_name != '中国') and terminal_channel_type in ('www','app','touch') and order_status not in ('CANCELLED','REJECTED') and is_valid = '1'
                        group by user_id
                    ) b on a.user_id = b.user_id
                        left join
                    (
                        select user_id
                        from ihotel_default.dw_qunar_three_order_detail_intl_hi
                        where dt = date_sub('2026-06-07', 1) and order_date = dt and (province in ('台湾','澳门','香港') or country != '中国') and order_status not in ('已删�?,'已经取消','已经拒单') and is_valid = '1' and order_no <> '103576132435' and user_id is not null and user_id <> ''
                        group by user_id
                    ) y_hi_order_user on a.user_id = y_hi_order_user.user_id
                        left join
                    (
                        select user_id, min(order_date) as pre2_min_order_date
                        from default.mdw_order_v3_international
                        where dt = date_sub('20260606', 1) and (province_name in ('台湾','澳门','香港') or country_name != '中国') and terminal_channel_type in ('www','app','touch') and order_status not in ('CANCELLED','REJECTED') and is_valid = '1' and user_id is not null and user_id <> ''
                        group by user_id
                    ) b_pre2 on a.user_id = b_pre2.user_id
                        left join temp.temp_yuchen_shen_c_country_area_relation ar on a.country_name = ar.country_name
                where rn = 1 and (province_name in ('台湾','澳门','香港') or a.country_name != '中国') and order_date1 = dt and order_no <> '103576132435'
            ) es_src
    ) order_json
    where user_type = '新客' and order_update_time between '2026-06-07 00:00:00' and '2026-06-07 00:59:59'
