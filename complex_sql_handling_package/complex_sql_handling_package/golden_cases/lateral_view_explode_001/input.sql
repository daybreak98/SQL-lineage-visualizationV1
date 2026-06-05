select
    t.order_id,
    item.amount as refund_amount
from default.order_table t
lateral view explode(t.refund_items) e as item
where t.dt='20260604';
