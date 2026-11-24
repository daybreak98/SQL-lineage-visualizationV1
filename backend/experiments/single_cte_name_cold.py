"""Adapt the signed private witness on the actual cold resolver. Never replay it."""
import logging

from app.services.subfield import analyze_subfields
from experiments.binding_shadow import Limits
from experiments.single_cte_name_shadow import Capture
from experiments.strict_use_wire_v2 import MAX_BYTES, wire


def capture(sql, schemas, *, with_v2, bare, header):
    if with_v2:
        from experiments.strict_use_dev import CAPTURE_LIMITS, DevShadow, compact_packer
        args = (CAPTURE_LIMITS, DevShadow)
    else:
        args = (Limits(edges=512, memo_bytes=128*1024),)
    try:
        if header:
            from experiments.cte_header_path_shadow import HeaderCapture

            a = HeaderCapture(sql, "spark", schemas, *args)
        else:
            a = Capture(sql, "spark", schemas, *args)
    except Exception:
        # Observer setup failed before parsing. Keep the ordinary error/response contract.
        return analyze_subfields(sql, "spark", schemas), None, None, None
    facts = a.run()
    pack = compact_packer(a, facts) if with_v2 else None
    data = None
    try:
        # V2 keeps its original budget. The new view still obeys the smaller
        # signed-shadow bounds and can never suppress or replace a V2 result.
        if bare and len(a.shadow.records) <= 512 and a.shadow.bytes <= 128*1024:
            rows = [r for r in a.witnesses(facts) if r["anchor"]["kind"] == "SINGLE_INPUT_OUTPUT_NAME"]
            if rows:
                snap = a.shadow.snapshot
                block = dict(version="single-input-output-name:1", rules="spark:local-cte-slot:1",
                             basis="SAME_RUN_SINGLE_INPUT_CTE_SLOT", catalog_verified=False,
                             snapshot={k:snap[k] for k in ("id","sql_sha256","dialect","sqlglot","schema_sha256")},
                             witnesses=rows)
                encoded = wire(block)
                if len(encoded) <= MAX_BYTES:
                    data = encoded
    except Exception:
        logging.getLogger(__name__).debug("Local CTE preview unavailable", exc_info=True)
    header_data = None
    try:
        if header and len(a.shadow.records) <= 512 and a.shadow.bytes <= 128*1024:
            rows = a.header_witnesses(facts)
            if rows:
                from experiments.cte_header_path_shadow import VERSION

                snap = a.shadow.snapshot
                block = dict(version=VERSION, rules="spark:cte-header-ordinal:1",
                             basis="SAME_RUN_ACTUAL_CTE_HEADER_SLOT", catalog_verified=False,
                             value_equivalence="UNVERIFIED", rowset_equivalence="UNVERIFIED",
                             pruning_authorized=False,
                             snapshot={k:snap[k] for k in ("id","sql_sha256","dialect","sqlglot","schema_sha256")},
                             witnesses=rows)
                encoded = wire(block)
                if len(encoded) <= MAX_BYTES:
                    header_data = encoded
    except Exception:
        logging.getLogger(__name__).debug("CTE header evidence unavailable", exc_info=True)
    return facts, pack, data, header_data
