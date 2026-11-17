from app.services.subfield_local import analyze_local_bindings


def test_tuple_slots_after_opaque_decode():
    sql = """WITH d AS (SELECT reflect('Decoder','decode',s.payload) AS body FROM db.src s)
    SELECT b.pg AS second, a.pg AS first, pg AS ambiguous FROM d
    LATERAL VIEW json_tuple(d.body,'left','right') a AS pg, renamed
    LATERAL VIEW json_tuple(a.renamed,'mix','pg') b AS mix, pg"""
    result = analyze_local_bindings(sql, 'hive')
    first, second = result['facts']['generators']
    bindings = result['column_bindings']
    ports = [(item['binding']['generator_id'], item['binding']['producer']['slot'])
             for item in bindings if item['expression'] in ('b.pg', 'a.pg')]
    assert ports == [(second['id'], 2), (first['id'], 1)]
    assert not any(item['expression'] == 'pg' for item in bindings)
    occurrence, = [item for item in bindings if item['expression'] == 'a.renamed']
    assert occurrence['generator_input_of'] == second['id']
    assert occurrence['binding']['producer']['slot'] == 2
    assert [port['key'] for port in second['outputs']] == ['mix', 'pg']
    assert all(sql[p['key_position']['start']:p['key_position']['end']] == repr(p['key']) for p in second['outputs'])
    assert not any(item['kind'] == 'TUPLE_REQUEST' for item in result['facts']['uses'])
    assert second['structure_inputs'][0]['column'] == 'payload'


def test_invalid_keys_and_duplicate_aliases():
    for args, aliases in [("s.j,s.k", 'x'), ("s.j,'a','b'", 'x'), ("s.j,'a','b'", 'x,X')]:
        result = analyze_local_bindings(f'SELECT g.x FROM db.src s LATERAL VIEW json_tuple({args}) g AS {aliases}', 'hive')
        assert not result['facts']['generators']
        assert not any(item['expression'] == 'g.x' for item in result['column_bindings'])
        if 's.k' in args:
            assert any(item['expression'] == 's.k' for item in result['column_bindings'])


def test_opaque_explode_rename():
    sql = 'SELECT nested.j FROM (SELECT g.item AS j FROM db.src s LATERAL VIEW explode(private_array(s.j)) g AS item) nested'
    result = analyze_local_bindings(sql, 'hive')
    generator, = result['facts']['generators']
    inner, = [item for item in result['column_bindings'] if item['expression'] == 'g.item']
    outer, = [item for item in result['column_bindings'] if item['expression'] == 'nested.j']
    assert inner['binding']['generator_id'] == generator['id']
    assert outer['binding']['producer'] == inner['consumer']
    assert generator['input_semantics'] == 'UNKNOWN'
    assert not any(item['kind'] == 'EXTRACT' for item in result['facts']['mappings'])
