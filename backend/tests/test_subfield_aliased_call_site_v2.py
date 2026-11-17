from app.services.subfield_local import analyze_local_bindings
from app.services.subfield import analyze_subfields


def test_generator_and_union_positions_are_local_to_the_declared_output_slot():
    def interval(row):
        p = row['position']
        return p['start'], p['end']

    sql = ("SELECT u.k,u.v FROM lab.events t LATERAL VIEW OUTER\n"
           "explode(map('type',get_json_object(t.j,'$.kind'),\n"
           "'status',get_json_object(t.j,'$.kind'))) u AS k,v")
    f = analyze_subfields(sql, 'hive')
    assert [interval(m) for m in f['mappings']] == [(148,149),(150,151),(9,10),(13,14)]
    assert [interval(u) for u in f['uses']] == [(71,86),(111,126)]

    sql = ("SELECT q.kind FROM (\n  SELECT get_json_object(t.j,'$.kind') AS kind FROM lab.events t\n"
           "  UNION ALL\n  SELECT get_json_object(t.j,'$.kind') AS kind FROM lab.events t\n) q")
    f = analyze_subfields(sql, 'hive')
    leaves = {(m['scope'], m['slot']):m for m in f['mappings']}
    branches = leaves['1:3',1]['union_branches']
    assert [interval(b) for b in branches] == [(63,67),(140,144)]
    for b in branches:
        p = b['producer']
        assert leaves[p['scope'],p['slot']]['position'] == b['position']
    assert [interval(u) for u in f['uses']] == [(30,45),(107,122)]
    duplicate = analyze_subfields(sql.replace(' AS kind FROM', ' AS kind, t.j AS kind FROM'), 'hive')
    assert any(u['code'] == 'AMBIGUOUS_OUTPUT' for u in duplicate['unknowns'])
    assert not any(m.get('union_branches') for m in duplicate['mappings'])


def test_opaque_alias_has_a_call_anchor_and_two_readers_without_identity():
    sql = ("WITH p AS (SELECT private_box(get_json_object(s.j,'$.k')) AS v FROM lab.src s) "
           "SELECT l.v AS a,r.v AS b FROM p l JOIN p r ON l.v=r.v")
    result = analyze_local_bindings(sql, 'hive')
    [m] = [m for m in result['facts']['mappings'] if not m['root'] and m['output'] == 'v']
    pos = m['position']
    assert pos and sql[pos['start']:pos['end']] == 'private_box'
    assert m['kind'] == 'UNKNOWN' and [i['path'] for i in m['inputs']] == ['$.k']
    [source] = [b for b in result['column_bindings'] if b['binding']['kind'] == 'NAMED_SOURCE']
    assert [o['kind'] for o in source['operations']] == ['JSONExtractScalar','Anonymous']
    assert source['operations'][-1]['position'] == pos
    assert source['operations'][-1]['semantics'] == 'UNVERIFIED'
    readers = [b for b in result['column_bindings'] if b['clause']=='SELECT' and b['binding']['kind']=='PROJECTION']
    assert {b['consumer']['slot'] for b in readers} == {1, 2}
    assert all(b['binding']['producer'] == source['consumer'] for b in readers)
