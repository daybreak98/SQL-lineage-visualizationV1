select hotel_seq
     ,total as `产单量`
     ,CONCAT(round(((a/total*3.5) --到店无房
    +(b/total*0.2) --到店无预订
    +((c+d)/total*0.3) --确认后推翻量（确认后涨价+确认后满房）
    +((e+f)/total*1) --  - 确认前推翻量（确认前涨价+确认前满房）
                       )*100,4),'%') as `加权缺陷率`
from
    (
        select hotel_seq
             ,COUNT(distinct case when a1.complain_type_new='到店无房' then a1.order_no else null end) as a
             ,COUNT(distinct case when a1.complain_type_new='到店无预订' then a1.order_no else null end) as b
             ,COUNT(distinct case when a1.complain_type_new='确认后满房' then a1.order_no else null end) as c
             ,COUNT(distinct case when a1.complain_type_new='确认后涨价' then a1.order_no else null end) as d
             ,COUNT(distinct case when a1.complain_type_new='确认前满房' then a1.order_no else null end) as e
             ,COUNT(distinct case when a1.complain_type_new='确认前涨价' then a1.order_no else null end) as f
             ,COUNT(distinct case when a1.complain_type_new='无拒单' then a1.order_no else null end) as i
             ,case
                  when COUNT(distinct a1.order_no) <= 5 then 5
                  else COUNT(distinct a1.order_no)
            end as total
        FROM
            (
                SELECT order_no,complain_type,checkin_date
                     ,CASE
                          WHEN defect_type IS NULL THEN complain_type
                          ELSE defect_type
                    END AS complain_type_new
                FROM fuwu.dwd_ord_htl_servicequality_di
                WHERE dt between '2025-05-13' AND '2026-05-13'
                  AND sale_channel='Q2Q'--勿动
                  AND is_international='1'--勿动
                  AND order_status <> 'DELETE'
                  AND (((balance_type='PROXY' OR is_guarantee=1) AND pay_status NOT IN ('PAY','PAY_FAILED')) OR (balance_type='CASH' AND is_guarantee='0'))--勿动
                  AND checkin_date between '2026-03-13' and '2026-05-13' --上上周期 采样开始时间和采样结束时间
            )a1
                left join
            (
                SELECT order_no,order_status,supplier_code,wrapper_name,country_name,c_isagent,c_supplier_id,hotel_seq
                FROM default.mdw_order_v3_international
                WHERE dt='20260513'
            )a2 ON a1.order_no=a2.order_no
        group by 1
    ) aa


