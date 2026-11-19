from copy import deepcopy
from unittest.mock import patch

import pytest

from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage
from app.services import subfield_static_evidence as evidence

B = """WITH b AS (SELECT t.j AS raw, t.k AS dyn FROM lab.src t),
     c AS (SELECT b.raw, b.dyn, get_json_object(b.raw,'$.a') AS child FROM b)
SELECT get_json_object(c.raw,'$.a.x') AS hit, c.raw AS whole,
       get_json_object(c.child,'$.x') AS nested,
       get_json_object(c.raw,concat('$.',c.dyn)) AS dynamic_value FROM c"""
HIST = "WITH c AS (SELECT get_json_object(s.j,'$.a') AS x FROM src s) SELECT get_json_object(c.x,'$.b') AS hit FROM c"


def run(sql, scope, slot, **kw):
    req = SubfieldRequest(sql=sql, dialect='spark', include_two_step_evidence=True, protected_outputs=[dict(statement=1, scope=scope, slot=slot)],
                          candidate_keys=[dict(source='lab.src', column='j', keys=['a'])], **kw)
    return analyze_subfield_lineage(req)


@pytest.mark.parametrize('sql,scope,slot,keys', [(B, '1:3', 3, ['x', 'a']), (HIST, '1:2', 1, ['b', 'a']),
                                                 (B, '1:3', 1, []), (B, '1:3', 4, [])])
def test_optional_chain(sql, scope, slot, keys):
    result = run(sql, scope, slot)
    block = result['review'].pop('static_extraction_evidence', None)
    assert bool(block) == bool(keys)
    if keys:
        steps = block['source_demand']['witness']
        assert [op['path_tokens'][0]['value'] for edge in steps for op in edge['operations']] == keys
        assert steps[0]['consumer'] == block['protected_output']
        assert steps[-1]['source']['column'] == 'j'
        if sql == B:
            assert [(p['start'],p['end']) for p in (e['evidence']['position'] for e in steps)] == [(223,228),(108,111),(20,21)]
    with patch.object(evidence, 'static_extraction_evidence', return_value=None):
        assert result == run(sql, scope, slot)


def test_identity_and_boundary():
    result = run(B,'1:3',3)
    root = dict(statement=1,scope='1:3',slot=3)
    for changed in [B.replace('\n','\r\n'), '-- prefix\n'+B]:
        assert evidence.static_extraction_evidence(changed,'spark',root,result) is None
    for k in ['sqlglot','dialect']:
        stale = deepcopy(result); stale['coverage'][k] = 'mismatch'
        assert evidence.static_extraction_evidence(B,'spark',root,stale) is None
    original = evidence.build_snapshot
    for failure in ['foreign','missing']:
        def changed(*args, **kw):
            snap = original(*args, **kw)
            edge = next(e for e in snap['relations'] if e['consumer']['scope']=='1:3' and e['consumer']['slot']==3)
            if failure == 'foreign': edge['producer']['snapshot']='foreign'
            else: snap['relations'].remove(edge)
            return snap
        with patch.object(evidence,'build_snapshot',changed):
            assert evidence.static_extraction_evidence(B,'spark',root,result) is None
    derived = "SELECT get_json_object(v.x,'$.b') AS hit FROM (SELECT s.j AS x FROM src s) v"
    for sql, scope, slot, kwargs in [(B.replace(' AS hit', ' AS nested'), '1:3', 3, {}),
                                     (B, '1:3', 3, dict(source_schemas={})), (derived, '1:2', 1, {})]:
        assert 'static_extraction_evidence' not in run(sql, scope, slot, **kwargs)['review']


@pytest.mark.parametrize('warm', [False, True])
def test_build_counts_and_review_equivalence(monkeypatch, warm):
    from time import perf_counter
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import subfield_fact_cache as cache
    from app.services import subfield, subfield_local

    monkeypatch.setenv('SUBFIELD_FACT_CACHE', '1')
    monkeypatch.setattr(cache, 'snapshots', cache.FactSnapshots())
    counters = [0, 0, 0]
    for i, (module, func) in enumerate([(subfield, 'analyze_subfields'),
                                         (subfield_local, 'analyze_local_bindings'), (evidence, 'build_snapshot')]):
        original = getattr(module, func)
        def count(*args, _i=i, _fn=original, **kwargs):
            counters[_i] += 1
            return _fn(*args, **kwargs)
        monkeypatch.setattr(module, func, count)
    with TestClient(app) as client:
        def post(sql, slot=None, key='a', scope='1:3'):
            req = dict(sql=sql, dialect='spark')
            if slot:
                req.update(include_two_step_evidence=True, protected_outputs=[dict(statement=1, scope=scope, slot=slot)],
                           candidate_keys=[dict(source='lab.src', column='j', keys=[key])])
            start = perf_counter()
            response = client.post('/api/sql/subfield-lineage', json=req)
            assert response.status_code == 200
            data = response.json()
            print('warm', warm, 'slot', slot, 'counts', tuple(counters), 'ms', round((perf_counter()-start)*1000, 2))
            assert '_two_step_v1' not in data
            return req, data
        if warm:
            post(B)
            assert counters == [1, 0, 0]
        first = None
        comparisons = []
        for slot, key in [(3,'a'), (3,'other'), (1,'a'), (4,'a'), (3,'a')]:
            req, result = post(B, slot, key)
            block = result['review'].pop('static_extraction_evidence', None)
            if slot == 3:
                first = first or block
                assert block and block == first and block['status'] == 'REVIEW_ONLY'
                assert block['rowset_verified'] is False and block['pruning_authorized'] is False
            else:
                assert block is None
            comparisons.append((req, result))
            assert counters == [1, 1, 1]
        # Detached, per-request legacy assessment, independently recomputed.
        for req, result in comparisons:
            with patch.object(evidence, 'static_extraction_evidence', side_effect=RuntimeError('entry failure')):
                assert client.post('/api/sql/subfield-lineage', json=req).json() == result
        _, changed = post('-- prefix\n'+B, 3)
        assert counters == [2, 2, 2]
        assert changed['review']['static_extraction_evidence']['projection_position']['start'] == first['projection_position']['start'] + 10
        post("SELECT get_json_object(t.j,'$.a') AS hit FROM src t", 1, scope='1:1')
        assert counters == [3, 2, 2]
        both = HIST.replace(' AS hit FROM c', " AS hit, get_json_object(c.x,'$.z') AS alt FROM c")
        for slot, path in [(2,'z'),(1,'b'),(2,'z')]:
            _, result = post(both, slot, scope='1:2')
            block = result['review']['static_extraction_evidence']
            assert block['protected_output']['slot'] == slot
            assert block['source_demand']['witness'][0]['operations'][0]['path_tokens'][0]['value'] == path
            assert counters == [4, 3, 3]


@pytest.mark.parametrize('func', ['_eligible', 'build_snapshot', 'compose_demands'])
def test_optional_faults_preserve_whole_legacy_response(func):
    with patch.object(evidence, 'static_extraction_evidence', return_value=None):
        expected = run(B, '1:3', 3)
    with patch.object(evidence, func, side_effect=RuntimeError('injected')) as fault:
        assert run(B, '1:3', 3) == expected
        assert fault.called


def test_two_output_detail_contract(monkeypatch):
    from hashlib import sha256
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.delenv('SUBFIELD_FACT_CACHE', raising=False)
    sql = HIST.replace(' AS hit FROM c', " AS hit, get_json_object(c.x,'$.z') AS alt FROM c")
    digest = sha256(sql.encode()).hexdigest()
    ports = [dict(statement=1, scope='1:2', slot=i) for i in (1, 2)]
    base = dict(sql=sql, dialect='spark', protected_outputs=ports,
                candidate_keys=[dict(source='src', column='j', keys=['a'])])
    with TestClient(app) as client:
        def post(payload):
            response = client.post('/api/sql/subfield-lineage', json=payload)
            assert response.status_code == 200
            return response.json()
        original = post(base)
        assert original['review']['candidate_assessment'] == dict(status='UNKNOWN', reason='PROTECTED_PATH_UNVERIFIED', entries=[])
        assert 'static_extraction_evidence' not in original['review']
        assert post(dict(base, include_two_step_evidence=True)) == original
        for port, second, alias in [(ports[1], 'z', 'alt'), (ports[0], 'b', 'hit')]:
            single = dict(base, protected_outputs=[port]); detail = dict(single, include_two_step_evidence=True)
            data = post(detail); block = data['review'].pop('static_extraction_evidence')
            assert block['status'] == 'REVIEW_ONLY' and block['rowset_verified'] is False and block['pruning_authorized'] is False
            assert data['review']['path_demand_status'] == 'ANALYSIS_INCOMPLETE'
            assert data == post(single)
            assert block['protected_output'] == dict(port, snapshot='local:'+digest, sql_sha256=digest)
            assert data['coverage']['sql_sha256'] == digest and data['coverage']['dialect'] == 'spark'
            assert block['source_demand']['witness'][0]['consumer'] == block['protected_output']
            assert [e['operations'][0]['path_tokens'][0]['value'] for e in reversed(block['source_demand']['witness'])] == ['a', second]
            p = block['projection_position']; assert sql[p['start']:p['end']] == alias
            assert 'static_extraction_evidence' not in post(dict(detail, source_schemas={}))['review']
        assert post(base) == original
