select b.order_id, amount_item
from ods_order_log b
lateral view explode(split(b.refund_amount, ',')) e as amount_item
where b.dt = '20260101'

