import json

from app.services.subfield_local import analyze_local_bindings


def test_with_insert_context_uses_resolver_scope_objects_and_ports():
    contexts = []
    sql = 'WITH d AS (SELECT s.x FROM db.src s) INSERT INTO db.dest SELECT d.x FROM d'
    result = analyze_local_bindings(sql, 'hive', on_query=contexts.append)
    context, = contexts
    assert context['tree'].key == 'insert' and context['query'].args['with_']
    producer, consumer = context['scope_ids']
    occurrence, = [entry for entry in result['column_bindings'] if entry['expression'] == 'd.x']
    assert occurrence['binding']['producer'] == context['ports'][producer][0]
    assert occurrence['consumer'] == context['ports'][consumer][0]
    assert context['scope_ids'][consumer] == occurrence['scope']
    assert json.loads(json.dumps(result)) == result
