from app.services.subfield import analyze_subfields
from app.services.subfield_local import analyze_local_bindings


def test_single_part_source_schema_only_excludes_columns_for_exact_complete_declaration():
    for relation, declared, complete, excluded in [
        ('src', 'src', True, True), ('src', 'src', False, False),
        ('lab.src', 'src', True, False), ('src', 'lab.src', True, False),
    ]:
        sql = f'SELECT ns.f(t.ok,t.missing), missing FROM {relation} t'
        schema = {declared: dict(columns=['ok'], complete=complete, version='1', evidence='fixture')}
        result = analyze_local_bindings(sql, 'hive', source_schemas=schema)
        facts = result['facts']
        assert [r['argument_slot'] for r in facts['opaque_call_arguments']] == ([1] if excluded else [1, 2])
        assert [r['binding']['column'] for r in result['column_bindings']] == (
            ['ok'] if excluded else ['ok', 'missing', 'missing'])
        assert sum(u['code'] == 'UNBOUND_COLUMN' for u in facts['unknowns']) == (2 if excluded else 0)
        assert set(facts['coverage']['source_schema_binding']['applied']) == ({declared} if excluded else set())
        assert facts['coverage']['catalog_verified'] is False


def test_complete_declaration_checks_qualified_argument_without_a_catalog_claim():
    sql = ('WITH t AS (SELECT s.present, s.absent FROM db.src s) '
           'SELECT ns.f(t.present,t.absent) FROM t')
    decl = {'db.src': {'columns': ['PRESENT'], 'complete': True, 'version': '1', 'evidence': 'fixture'}}
    for schemas, slots in [(None, [1, 2]), (decl, [1])]:
        result = analyze_local_bindings(sql, 'hive', source_schemas=schemas)
        facts = result['facts']
        assert [r['argument_slot'] for r in facts['opaque_call_arguments']] == slots
        assert all(r['source_binding_status'] == 'SQL_NAMED_RELATION_COLUMN'
                   for r in facts['opaque_call_arguments'])
        assert facts['coverage']['catalog_verified'] is False
        if schemas:
            [missing] = [u for u in facts['unknowns'] if u['code'] == 'UNBOUND_COLUMN']
            p = missing['position']
            assert sql[p['start']:p['end']] == 'absent'
            assert all(b['binding'].get('column') != 'absent' for b in result['column_bindings'])
    ambiguous = analyze_subfields('SELECT ns.f(j) FROM db.a a JOIN db.b b ON a.k=b.k', 'hive')
    assert not ambiguous['opaque_call_arguments']
    assert any(u['code'] == 'AMBIGUOUS_COLUMN' for u in ambiguous['unknowns'])


def test_opaque_argument_identity_comes_from_each_call_and_its_direct_operand():
    sql = ("SELECT /* 甲 */ alpha.f(t.j,concat(')', 'x,y')), alpha.f('x,y',t.j), beta.f(t.j), "
           "alpha.f(get_json_object(t.j,'$.part')), alpha.f(t.p) "
           "FROM (SELECT s.j, get_json_object(s.j,'$.part') AS p FROM lab.src s) t")
    facts = analyze_subfields(sql, 'hive')
    rows = facts['opaque_call_arguments']
    assert [(r['callee'], r['argument_slot'], r['source']['path']) for r in rows] == [
        ('alpha.f', 1, '$'), ('alpha.f', 2, '$'), ('beta.f', 1, '$'), ('alpha.f', 1, '$.part')]
    assert len({r['call_position']['start'] for r in rows}) == len(rows)
    assert [sql[r['call_span']['start']:r['call_span']['end']] for r in rows] == [
        "alpha.f(t.j,concat(')', 'x,y'))", "alpha.f('x,y',t.j)", 'beta.f(t.j)', 'alpha.f(t.p)']
    for r in rows:
        text = lambda pos: sql[pos['start']:pos['end']]
        assert text(r['call_position']) == r['callee'] and text(r['leaf_position']) == 'f'
        assert text(r['argument_position']) in ('t.j', 't.p')
        assert r['source']['source'] == 'lab.src' and r['source']['column'] == 'j'
        assert r['source_binding_status'] == 'SQL_NAMED_RELATION_COLUMN'
        assert r['semantics'] == 'OPAQUE' and r['operation'] == 'OPAQUE_CALL_ARGUMENT'
        assert any(d['code'] == 'UNKNOWN_FUNCTION' and d['position'] == r['leaf_position']
                   and d['statement'] == r['statement'] for d in facts['unknowns'])
