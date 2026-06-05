with base as (
  select regexp_extract(url, '^[^?]+', 0) as url_path,
         get_json_object(payload, '$.refundRecords[*].amount.amount') as refund_amount,
         order_id
  from ods_order_log
  where dt = '${DATE}'
)
select order_id, refund_amount, url_path from base

