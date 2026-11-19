from copy import deepcopy

from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage
from app.services.subfield_review import build_review

A = ("SELECT get_json_object(e.payload, '$.item_id') AS item_id,\n"
     "       get_json_object(e.payload, '$.shop_id') AS shop_id\nFROM demo.events e")
PORTS = [dict(statement=1, scope='1:1', slot=n) for n in (1, 2)]
KEYS = [dict(source='demo.events', column='payload', keys=['item_id', 'absent'])]


def review(sql, ports=PORTS, **kwargs):
    return analyze_subfield_lineage(SubfieldRequest(sql=sql, dialect='spark', protected_outputs=ports,
                                                    candidate_keys=KEYS, **kwargs))


def test_direct_and_duplicate_key():
    for sql in (A, A.replace('$.shop_id', '$.item_id')):
        result = review(sql)
        r = result.pop('review')
        assert result == analyze_subfield_lineage(SubfieldRequest(sql=sql,dialect='spark'))
        assert r['status'] == 'REVIEW_ONLY'
        assert [(e['key'],e['status'],e['reason']) for e in r['candidate_assessment']['entries']] == [
            ('item_id','OBSERVED','OVERLAPS_OBSERVED_PATH'),
            ('absent','NOT_OBSERVED_NEEDS_VALIDATION','KEY_EXISTENCE_AND_EFFECT_UNVERIFIED')]
        reads = [d['direct_extract_read'] for d in r['observed_path_demands']['by_protected_output']]
        assert [w['port'] for w in reads] == PORTS
        assert [w['position']['start'] for w in reads] == [7,66]
        for w in reads:
            p = w['column_position']; assert sql[p['start']:p['end']] == 'payload'
    single = review(A, PORTS[1:])['review']
    assert len(single['observed_path_demands']['by_protected_output']) == 1
    assert single['candidate_assessment']['entries'][0]['status'] == 'OBSERVED'


def test_dynamic_and_ineligible_shapes():
    dynamic = review(A.replace("'$.shop_id'","concat('$.',e.k)"))['review']
    assert dynamic['candidate_assessment'] == dict(status='UNKNOWN',entries=[],reason='ANALYSIS_INCOMPLETE')
    for sql in (A.replace('$.shop_id','$.shop.id'), A.replace('$.shop_id','$.shop[0]'),
                A.replace("get_json_object(e.payload, '$.shop_id')", 'e.payload'),
                A.replace("e.payload, '$.shop_id'", "get_json_object(e.payload,'$.shop'), '$.id'"),
                A.replace('SELECT ', 'SELECT DISTINCT '), A+' WHERE e.k=1',
                A.replace(' AS shop_id',' AS item_id'), A+'; SELECT 1 AS extra',
                A.replace('demo.events e','(SELECT s.payload FROM demo.events s) e')):
        result = review(sql, PORTS[:1]); assert not any('direct_extract_read' in m for m in result['mappings'])
    assert 'direct_extract_read' not in review(A, source_schemas={'demo.events': {'columns':['payload']}})['mappings'][0]


def test_incomplete_or_reused_occurrences():
    original = review(A.replace('$.shop_id','$.item_id'))
    for change in ('missing','duplicate','wrong column','missing slot and use','foreign use position'):
        r = deepcopy(original)
        if change=='missing': r['uses'].pop()
        elif change=='duplicate': r['uses'][1] = r['uses'][0]
        elif change=='wrong column': r['uses'][1]['column']='other'
        elif change=='foreign use position': r['uses'][1]['position']['end'] += 10000
        else: r['uses'].pop(); r['mappings'].pop()
        result = build_review(r, PORTS[:1],KEYS)
        assert result['observed_path_demands']['by_protected_output'] == []
        assert result['candidate_assessment'] == dict(status='UNKNOWN',entries=[],reason='PROTECTED_PATH_UNVERIFIED')


def test_dispatch_ac_exact_sql_and_ambiguous_source():
    direct = "SELECT get_json_object(t.event_payload,'$.media_id') FROM lab.media_events t;"
    cte = ("WITH c AS (SELECT t.event_payload AS p FROM lab.media_events t)\n"
           "SELECT get_json_object(c.p,'$.media_id') FROM c;")
    keys = [dict(source='lab.media_events', column='event_payload', keys=['media_id'])]
    for sql, scope, observed in [
        (direct, '1:1', True), (cte, '1:2', True),
        (direct.replace(' FROM', ' AS media_id FROM'), '1:1', True),
        (cte.replace(' FROM c;', ' AS media_id FROM c;'), '1:2', True),
        (direct.replace('t.event_payload', 'event_payload').replace(' FROM', ' AS media_id FROM')
         .replace(' t;', ' t JOIN lab.other o ON t.id=o.id;'), '1:1', False),
    ]:
        port = dict(statement=1, scope=scope, slot=1)
        r = analyze_subfield_lineage(SubfieldRequest(sql=sql, dialect='spark', protected_outputs=[port],
                                                     candidate_keys=keys))
        review = r['review']
        a = review['candidate_assessment']
        print(scope, sql, a, [(m['output'], m['position']) for m in r['mappings'] if m['root']])
        assert a['status'] == ('OBSERVED' if observed else 'UNKNOWN')
        assert review['status'] == 'REVIEW_ONLY' and not r['coverage']['catalog_verified'] and not r['coverage']['engine_semantics_verified']
        assert review['path_demand_status'] == ('OBSERVED' if observed else 'ANALYSIS_INCOMPLETE')
        if observed:
            assert [(x['key'], x['status']) for x in a['entries']] == [('media_id','OBSERVED')]
            d, = review['observed_path_demands']['by_protected_output']
            assert d['protected_output'] == port and d['source'] == keys[0]['source']
            assert bool(d['port_reads']) == (scope == '1:2')
        else:
            assert a['entries'] == [] and not review['observed_path_demands']['by_protected_output']


def test_swapped_direct_witnesses_with_restored_ports_stay_unknown():
    for sql in (A, A.replace('$.shop_id', '$.item_id')):
        r = review(sql)
        left, right = r['mappings']
        left['direct_extract_read'], right['direct_extract_read'] = right['direct_extract_read'], left['direct_extract_read']
        for row, port in zip((left, right), PORTS):
            row['direct_extract_read']['port'] = port
        rejected = build_review(r, PORTS[:1], KEYS)
        assert rejected['candidate_assessment']['status'] == 'UNKNOWN'
        assert not rejected['observed_path_demands']['by_protected_output']


def test_dsh_unaliased_table_and_root_positions():
    sql = "SELECT get_json_object(events.payload,'$.a') FROM demo.events"
    port = PORTS[0]
    r = analyze_subfield_lineage(SubfieldRequest(sql=sql, dialect='spark', protected_outputs=[port],
        candidate_keys=[dict(source='demo.events',column='payload',keys=['a'])]))
    row, = r['mappings']
    demand, = r['review']['observed_path_demands']['by_protected_output']
    w = demand['direct_extract_read']
    assert demand['protected_output'] == port == w['port'] and demand['port_reads'] == []
    assert (w['source'], w['column'], w['path_tokens']) == ('demo.events','payload',[dict(kind='key',value='a')])
    assert row['position'] == w['position'] == r['uses'][0]['position']
    assert r['review']['path_demand_status'] == r['review']['candidate_assessment']['entries'][0]['status'] == 'OBSERVED'
    for span, start, token in [(row['position'],7,'get_json_object'), (w['base_qualifier']['reference_position'],23,'events'),
                              (w['column_position'],30,'payload'), (w['base_qualifier']['table_name_position'],55,'events')]:
        assert span['start'] == start and sql[start:span['end']] == token


def test_dsh_conflicting_or_multiple_relations_cannot_witness():
    expr = "SELECT get_json_object(events.payload,'$.a') FROM demo.events"
    for extra in (" AS e", " JOIN other.events ON 1=1", " JOIN other.tags AS u ON events.id=u.id"):
        r = analyze_subfield_lineage(SubfieldRequest(sql=expr+extra, dialect='spark', protected_outputs=PORTS[:1],
            candidate_keys=[dict(source='demo.events',column='payload',keys=['a'])]))
        assert r['review']['candidate_assessment']['status'] == 'UNKNOWN'
        assert not any(m.get('direct_extract_read') for m in r['mappings'])
