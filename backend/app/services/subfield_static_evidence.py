"""Optional local evidence for two literal extracts in separate SELECT slots."""
from hashlib import sha256

import sqlglot
from sqlglot import exp

from app.services.subfield import path_tokens
from app.services.subfield_composition import _position, build_snapshot, compose_demands


_ID = ('statement', 'scope', 'slot')


def _root_id(port):
    return ":".join(str(port[k]) for k in _ID)


def _eligible(mapping):
    if not mapping['root'] or mapping['kind'] != 'EXTRACT' or mapping.get('port_reads') or len(mapping['inputs']) != 1:
        return False
    tokens = mapping['inputs'][0]['path_tokens']
    parses = [i for i, token in enumerate(tokens) if token == {'kind': 'parse', 'value': 'json'}]
    # A negative filter only. A positive certificate still requires exact occurrence edges.
    return len(parses) == 1 and 0 < parses[0] < len(tokens) - 1


def static_extraction_evidence(sql, dialect, root, facts, *, retained=None, publish=None):
    coverage = facts['coverage']
    if (not coverage.get('parsed') or coverage.get('partial') or len(sql) > 16384 or
            len(facts['mappings']) > 64 or any(u['code'] != 'UNSUPPORTED_JSON_PATH' for u in facts['unknowns'])):
        return None
    ids = {(m['statement'], m['scope']) for m in facts['mappings']}
    if not 2 <= len(ids) <= 8 or any(statement != root['statement'] for statement, _ in ids):
        return None
    roots = [{k: m[k] for k in _ID} for m in facts['mappings'] if _eligible(m)]
    if root not in roots or len(roots) > 8:
        return None
    digest = sha256(sql.encode('utf-8')).hexdigest()
    if (coverage.get('sql_sha256'), coverage.get('dialect'), coverage.get('sqlglot')) != (digest, dialect, sqlglot.__version__):
        return None
    if retained is not None:
        return retained.get(_root_id(root))
    contexts = []
    sid = 'local:' + digest
    snapshot = build_snapshot(sql, sid, dialect, on_query=contexts.append)
    blocks = {}
    if (len(contexts) == 1 and snapshot['snapshot_id'] == sid and
            (snapshot['sql_sha256'], snapshot['dialect'], snapshot['sqlglot']) == (digest, dialect, sqlglot.__version__)):
        ctx = contexts[0]
        if ctx['tree'] is ctx['query'] and ctx['statement'] == root['statement'] and len({r['scope'] for r in roots}) == 1:
            for port in (roots if publish is not None else [root]):
                block = _extract(sql, digest, port, facts, snapshot, ctx, sid)
                if block is not None:
                    blocks[_root_id(port)] = block
    if publish is not None:
        publish(blocks)
    return blocks.get(_root_id(root))


def _extract(sql, digest, root, facts, snapshot, ctx, sid):
    scopes = {key: scope for scope, key in ctx['scope_ids'].items()}
    if len(scopes) > 8 or any(not isinstance(scope.expression, exp.Select) or
            any(v for k, v in scope.expression.args.items() if k not in {'expressions', 'from_', 'with_'}) or
            len(scope.selected_sources) != 1 for scope in scopes.values()):
        return None
    identity = dict(snapshot=sid, sql_sha256=digest)
    start = current = {**identity, **root}
    steps, call_sites = [], []
    while len(steps) < len(scopes):
        if any(e['consumer'] == current for e in steps):
            return None
        scope = scopes[current['scope']]
        projections = scope.expression.selects
        slot = current['slot']
        if not 1 <= slot <= len(projections):
            return None
        item = projections[slot - 1]
        rows = [r for r in snapshot['ports'] if r['port'] == current]
        maps = [m for m in facts['mappings'] if all(m[k] == current[k] for k in _ID)]
        if len(rows) != 1 or len(maps) != 1:
            return None
        row, mapping = rows[0], maps[0]
        name = item.alias_or_name
        if (row['root'] != (current == start) or mapping['root'] != row['root'] or
                not name or sum(i.alias_or_name.lower() == name.lower() for i in projections) != 1 or
                mapping['output'] != name or row['output'] != name):
            return None
        expr = item.this if isinstance(item, exp.Alias) else item
        anchor = item.args['alias'] if isinstance(item, exp.Alias) else item
        pos = _position(anchor)
        if not pos or pos != mapping['position'] or sql[pos['start']:pos['end']] != name:
            return None
        if current == start:
            root_position = pos
        ops = []
        column = expr
        if type(expr) in (exp.JSONExtractScalar, exp.JSONExtract):
            tokens = path_tokens(expr.expression)
            cp = _position(expr)
            if not tokens or not cp or sql[cp['start']:cp['end']].lower() != 'get_json_object':
                return None
            call_sites.append(cp)
            ops = [{'kind': 'EXTRACT', 'path_tokens': [{'kind': k, 'value': v} for k, v in tokens]}]
            column = expr.this
        if type(column) is not exp.Column or column.is_star:
            return None
        edges = [e for e in snapshot['relations'] if e['consumer'] == current]
        if len(edges) != 1:
            return None
        edge = edges[0]
        p = _position(column)
        if (not p or sql[p['start']:p['end']] != column.name or edge['evidence']['position'] != p or
                edge['role'] != 'VALUE' or edge['clause'] != 'SELECT' or edge['operations'] != ops):
            return None
        steps.append(edge)
        if 'source' in edge:
            src = edge['source']
            table = next(iter(scope.selected_sources.values()))[1]
            if (not isinstance(table, exp.Table) or src['relation'] != '.'.join(i.name for i in table.parts) or
                    src['column'].lower() != column.name.lower() or src['binding'] != 'SQL_NAMED_RELATION_COLUMN' or
                    any(src[k] != current[k] for k in ('snapshot', 'sql_sha256', 'statement', 'scope'))):
                return None
            break
        current = edge['producer']
        upstream = next(iter(scope.selected_sources.values()))[1]
        if (any(current[k] != start[k] for k in ('snapshot', 'sql_sha256', 'statement')) or
                scopes.get(current['scope']) is not upstream or not upstream.is_cte or
                not 1 <= current['slot'] <= len(upstream.expression.selects) or
                column.name.lower() != upstream.expression.selects[current['slot']-1].alias_or_name.lower()):
            return None
    else:
        return None
    if len(call_sites) != 2:
        return None
    # Only an explicitly located dynamic call at a different root slot can be isolated.
    siblings = [i.this if isinstance(i, exp.Alias) else i for n, i in
                enumerate(scopes[root['scope']].expression.selects, 1) if n != root['slot']]
    allowed = [_position(i) for i in siblings if type(i) in (exp.JSONExtractScalar, exp.JSONExtract)
               and path_tokens(i.expression) is None]
    proof = compose_demands([snapshot], [], [{'port': start, 'demand': {'kind': 'WHOLE_VALUE'}}])
    if any(u.get('code') != 'UNSUPPORTED_JSON_PATH' or u.get('statement') != root['statement'] or
           not u.get('position') or u['position'] not in allowed for u in [*facts['unknowns'], *proof['unknowns']]):
        return None
    values = [d for d in proof['source_demands'] if d.get('role') != 'ROWSET']
    if len(values) != 1 or values[0]['kind'] != 'VALUE_PATH' or values[0]['witness'] != steps:
        return None
    return {'status': 'REVIEW_ONLY', 'rowset_verified': False, 'pruning_authorized': False,
            'protected_output': start, 'projection_position': root_position, 'source_demand': values[0]}
