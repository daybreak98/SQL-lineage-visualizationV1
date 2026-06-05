select order_id
from ods_order_log
where dt = ${zdt.addDay(-1).format("yyyyMMdd")}

