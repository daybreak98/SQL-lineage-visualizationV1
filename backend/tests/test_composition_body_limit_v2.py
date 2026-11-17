"""Request body quota on the shipped ASGI application."""
from hashlib import sha256
import json
from unittest.mock import Mock

import httpx
import pytest

from app.api import subfield_controller
from app.middleware.local_delivery import MAX_REQUEST_BODY_BYTES


@pytest.mark.asyncio
@pytest.mark.parametrize('body_size,streamed,expected', [
    (None, False, 200),
    (MAX_REQUEST_BODY_BYTES, True, 200),
    (MAX_REQUEST_BODY_BYTES + 1, True, 413),
])
async def test_compose_raw_body_limit(monkeypatch, body_size, streamed, expected):
    from app.main import app

    sql = 'SELECT j FROM raw_src'
    payload = dict(mode='compose', snapshots=[dict(snapshot_id='a', sql=sql, dialect='hive')],
                   links=[], protected_outputs=[dict(port=dict(snapshot='a', statement=1, scope='1:1',
                       slot=1, sql_sha256=sha256(sql.encode()).hexdigest()))])
    body = json.dumps(payload, separators=(',', ':')).encode()
    if body_size is not None:
        body = body.ljust(body_size, b' ')
    calls = Mock(wraps=subfield_controller.compose_lineage)
    monkeypatch.setattr(subfield_controller, 'compose_lineage', calls)
    seen = []
    delivered = 0

    async def observe_asgi(scope, receive, send):
        seen.extend(scope['headers'])

        async def counted_receive():
            nonlocal delivered
            event = await receive()
            delivered += len(event.get('body', b''))
            return event

        await app(scope, counted_receive, send)

    async def chunks():
        for i in range(0, len(body), 65536):
            yield body[i:i+65536]

    transport = httpx.ASGITransport(app=observe_asgi, client=('127.0.0.1', 1234))
    async with httpx.AsyncClient(transport=transport, base_url='http://localhost') as client:
        response = await client.post('/api/sql/subfield-lineage', content=chunks() if streamed else body,
                                     headers={'Content-Type': 'application/json'})
    headers = dict(seen)
    if streamed:
        assert b'content-length' not in headers
        assert headers[b'transfer-encoding'] == b'chunked'
    else:
        assert int(headers[b'content-length']) == len(body)
    assert delivered == len(body)
    evidence = (f'actual_bytes={delivered}, limit={MAX_REQUEST_BODY_BYTES}, streamed={streamed}, '
                f'http={response.status_code}, service_calls={calls.call_count}')
    print(evidence)
    assert response.status_code == expected, evidence
    if expected == 413:
        calls.assert_not_called()
        assert response.json() == {'detail': 'Request body too large'}
    else:
        calls.assert_called_once()
        assert response.json()['status'] == 'REVIEW_ONLY'
