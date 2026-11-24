"""Local cold-run opt-in. No capability is inferred from client-supplied JSON."""
import os

from starlette.responses import Response

from app.middleware.local_delivery import is_loopback_client


FLAG = "SUBFIELD_SINGLE_INPUT_CTE_TRIAL"
HEADER_FLAG = "SUBFIELD_CTE_HEADER_ORDINAL_TRIAL"
MEMBER = b',"single_input_output_name_evidence":'
HEADER_MEMBER = b',"cte_header_ordinal_evidence":'
MAX_EXTRA = 32 * 1024


def modes(req, http):
    bare = os.environ.get(FLAG) == "1"
    header = os.environ.get(HEADER_FLAG) == "1"
    if ((bare or header) and http is not None and http.client is not None
            and is_loopback_client(http.client.host)
            and req.dialect == "spark" and "dialect" in req.model_fields_set
            and len(req.sql) <= 32768 and req.source_schemas is None
            and not req.include_two_step_evidence and not req.model_fields_set.intersection(
                {"protected_outputs", "candidate_keys", "strict_read_site"})):
        return bare, header
    return False, False


def append_if_fits(request, original, resolved):
    """Append only to final bytes, after V2/cache. The total delta over ordinary is bounded."""
    data = getattr(request.state, "single_cte_cold_bytes", None)
    header = getattr(request.state, "single_cte_header_bytes", None)
    if (not data and not header) or resolved.status_code != 200:
        return resolved
    raw = resolved.body
    if not raw.endswith(b"}") or not raw.startswith(b"{"):
        return resolved
    # Keep legacy V2/bare evidence first. New evidence never displaces it.
    extra = b""
    for field, payload in ((MEMBER,data),(HEADER_MEMBER,header)):
        if payload and len(raw) - len(original.body) + len(extra) + len(field) + len(payload) <= MAX_EXTRA:
            extra += field + payload
    if not extra:
        return resolved
    out = Response(raw[:-1] + extra + b"}", status_code=resolved.status_code, background=resolved.background)
    out.raw_headers.extend((k,v) for k,v in resolved.raw_headers if k.lower() != b"content-length")
    return out
