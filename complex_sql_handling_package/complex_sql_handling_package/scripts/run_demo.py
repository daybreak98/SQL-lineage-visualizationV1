from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from complex_sql_guard import ComplexSqlAnalyzer  # noqa: E402


def main() -> None:
    sql = """
    /*+ MAPJOIN(dim_city) */
    with base as (
        select
            regexp_extract(url, 'https?://([^/]+)/([^?]+)\\?.*', 2) as url_path,
            get_json_object(data, '$.refundRecords[*].refundDetails[*].amount.amount') as refund_amount,
            order_id
        from ods_order_log
        where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
    )
    select b.order_id, b.url_path, b.refund_amount
    from base b
    lateral view explode(split(b.refund_amount, ',')) e as amount_item
    """
    result = ComplexSqlAnalyzer().analyze(sql, dialect="spark")
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2)[:5000])


if __name__ == "__main__":
    main()
