from app.services.subfield_local import analyze_local_bindings


def test_ordered_arms_distinguish_guards_values_and_implicit_null():
    sql = """WITH d AS (SELECT s.a AS payload, s.flag FROM db.src s)
    SELECT CASE WHEN d.flag=1 THEN get_json_object(d.payload,'$.x')
                WHEN d.flag=2 THEN private_udf(get_json_object(d.payload,'$.y')) END AS result FROM d"""
    result = analyze_local_bindings(sql, 'hive')
    case, = result['cases']
    first, second, fallback = case['arms']
    assert case['consumer']['slot'] == 1 and case['clause'] == 'SELECT'
    for arm, path in [(first, '$.x'), (second, '$.y')]:
        assert arm['guard']['bindings'][0]['binding']['producer']['slot'] == 2
        assert arm['value']['bindings'][0]['binding']['producer']['slot'] == 1
        assert [origin['path'] for origin in arm['value']['inputs']] == [path]
        assert arm['guard']['anchor_position']['line'] == arm['value']['anchor_position']['line']
    assert [arm['slot'] for arm in case['arms']] == [1, 2, 3]
    assert second['value']['kind'] == 'UNKNOWN'
    assert fallback['kind'] == 'IMPLICIT_NULL' and not fallback['value']['inputs']


def test_simple_case_ambiguous_arm_does_not_borrow_guard_or_sibling_source():
    sql = 'SELECT CASE a.flag WHEN 1 THEN bad WHEN 2 THEN b.good ELSE NULL END FROM db.a a, db.b b'
    result = analyze_local_bindings(sql, 'hive')
    case, = result['cases']
    assert case['operand']['bindings'][0]['binding']['column'] == 'flag'
    first, second, fallback = case['arms']
    assert first['value']['kind'] == 'UNKNOWN' and not first['value']['bindings']
    assert not first['guard']['inputs'] and not first['value']['inputs']
    assert second['value']['bindings'][0]['binding']['source'] == 'db.b'
    assert fallback['kind'] == 'ELSE' and not fallback['value']['inputs']
