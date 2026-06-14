with base as (
    select
        regexp_extract(url, 'https?://([^/]+)/([^?]+)\?.*', 2) as url_path,
        get_json_object(data, '$.orderExtension.trackData.latestPurchaseOrder') as latest_purchase_order,
        order_id
    from default.ods_order_log
    where dt = '${DATE}'
)
select
    order_id,
    url_path,
    latest_purchase_order
from base;
