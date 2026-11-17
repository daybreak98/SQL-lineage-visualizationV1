import pytest

from app.services.subfield_local import analyze_local_bindings
from app.services.subfield_composition import build_snapshot


@pytest.mark.parametrize('dialect', ['hive', 'spark'])
def test_star_and_explicit_alias_have_a_unique_reader_only_if_proven(dialect):
    sql = 'SELECT p.k FROM (SELECT s.*, s.a AS k FROM src s) p'
    for columns in (['a', 'k'], ['a'], None):
        schema = None if columns is None else {'src': dict(columns=columns, complete=True,
                                                           version='1', evidence='fixture')}
        r = analyze_local_bindings(sql, dialect, source_schemas=schema)
        f = r['facts']
        root, = [m for m in f['mappings'] if m['root']]
        proven = columns == ['a']
        assert [i['column'] for i in root['inputs']] == (['a'] if proven else [])
        assert (root['kind'] == 'UNKNOWN') == (not proven)
        assert any(b['expression'] == 'p.k' for b in r['column_bindings']) == proven
        assert any(u['code'] == 'AMBIGUOUS_OUTPUT' for u in f['unknowns']) == (columns == ['a','k'])
        assert any(u['code'] == 'UNEXPANDED_STAR' for u in f['unknowns'])
        source, = [b for b in r['column_bindings'] if b['binding']['kind'] == 'NAMED_SOURCE']
        p = source['position']
        assert sql[p['start']:p['end']] == 'a'


def test_snapshot_context_does_not_disambiguate_star_output():
    sql = 'SELECT p.k FROM (SELECT s.*, s.a AS k FROM src s) p'
    context = {'source_schemas': {'src': dict(columns=['a'], complete=True, version='1', evidence='fixture')}}
    snapshot = build_snapshot(sql, 'star-review', 'hive', source_context=context)
    assert any(r.get('source', {}).get('column') == 'a' for r in snapshot['relations'])
    assert not any(r['consumer']['scope'] == '1:2' for r in snapshot['relations'])
