from app.services.subfield import analyze_subfields


def test_unrelated_declarations_preserve_macro_but_same_name_function_blocks_it():
    sql = "CREATE TEMPORARY MACRO read_x(doc STRING) get_json_object(doc,'$.x'); CREATE TABLE db.audit(id INT); CREATE TEMPORARY FUNCTION other AS 'example.Other'; "
    call = 'SELECT read_x(s.j) AS x FROM db.src s'
    facts = analyze_subfields(sql + call, 'hive')
    assert any(use['path'] == '$.x' and use['macro']['call']['statement'] == 4 for use in facts['uses'])
    shadow = analyze_subfields(sql + "CREATE TEMPORARY FUNCTION read_x AS 'example.Shadow'; " + call, 'hive')
    assert not any(use['path'] == '$.x' for use in shadow['uses'])


def test_group_alias_collision_keeps_independent_qualified_read():
    sql = "SELECT t.other AS k FROM db.src t GROUP BY k + get_json_object(t.v,'$.x')"
    facts = analyze_subfields(sql, 'hive')
    read, = [use for use in facts['uses'] if use['clause'] == 'GROUP_BY']
    assert (read['column'], read['path'], read['role']) == ('v', '$.x', 'RELATIONAL')
    gap, = [item for item in facts['unknowns'] if item['code'] == 'POSSIBLE_OUTPUT_ALIAS']
    assert sql[gap['position']['start']:gap['position']['end']] == 'k'
