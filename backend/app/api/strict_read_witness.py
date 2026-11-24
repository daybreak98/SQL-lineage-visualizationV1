"""Project one sealed observer proof. No parsing, name lookup, fallback or graph export."""
from hashlib import sha256
import re


RULES = "binding-shadow-inner-3"
CHAIN = "SOURCE_CHAIN_UNVERIFIED"
VISIBLE = "SITE_NOT_VISIBLE"
UNAVAILABLE = "OBSERVER_UNAVAILABLE"
GROUPS = ("value_edges", "control_uses", "row_effects", "gaps")
VISIBILITY_GAPS = {"JOIN_OCCURRENCE_NOT_VISIBLE_OR_QUALIFIED", "JOIN_USE_VISIBILITY_UNVERIFIED"}
UNSUPPORTED_GAPS = {"UNSUPPORTED_JSON_PATH", "EXTRACTION_NOT_CERTIFIED", "EXTRACTION_ANCHOR_UNVERIFIED",
                    "JOIN_STAGE_UNSUPPORTED", "JOIN_OPERAND_UNVERIFIED", "QUALIFIER_REQUIRED"}


class _Refusal(Exception):
    pass


def require(ok, reason=CHAIN):
    if not ok:
        raise _Refusal(reason)


def vector(v):
    return type(v) in (list, tuple)


def key(v):
    """IDs in the observer are structural tuples (arrays after JSON serialization)."""
    if vector(v):
        return tuple(key(x) for x in v)
    require(type(v) in (str, int) or v is None)
    return v


def pair(p, sql, reason=CHAIN):
    require(vector(p) and len(p) == 2 and all(type(i) is int for i in p)
            and 0 <= p[0] < p[1] <= len(sql), reason)
    return tuple(p)


def out(p):
    return {"start": p[0], "end": p[1]}


def row_boundary(nodes, used, sid, statement, sql):
    """Grade row-stage witnesses independently; never weaken a validated V/P chain."""
    at_use = whole = "NO_JOIN"
    scopes = {}
    for vid in used:
        v = nodes[vid]  # Already validated as THIS proof's V, including exact prefix and ON.
        scopes.setdefault(vid[3], {})[v["ordinal"]] = v
    if scopes:
        at_use = whole = "STAGES_OBSERVED"
    for sc, points in scopes.items():
        record = nodes.get((sid, "JS", statement, sc)) or {}
        count = record.get("stage_count")
        known_count = (record.get("kind") == "JOIN_SCOPE_STAGES" and record.get("group") == "row_effects"
                       and type(count) is int and max(points) <= count <= 32)
        prefix_len = 0
        prev_inputs = ()
        for n in range(1, (count if known_count else max(points)) + 1):
            try:
                j = nodes.get((sid, "J", statement, sc, n)) or {}
                require(j.get("kind") == "INNER_ON_STAGE" and j["group"] == "row_effects" and j["ordinal"] == n)
                prev = (sid, "J", statement, sc, n-1) if n > 1 else None
                require(key(j["previous"]) == prev)
                inputs = key(j["inputs"])
                require(len(inputs) == n+1 and (not prev or inputs[:-1] == prev_inputs))
                require(all(r[:4] == (sid, "R", statement, sc) and (nodes.get(r) or {}).get("kind") == "ROW_INPUT"
                            for r in inputs))
                on = pair(j["anchor"], sql)
                require(sql[slice(*on)].upper() == "ON")
                if n in points:
                    require(on == key(points[n]["anchor"])
                            and tuple(r[4] for r in inputs) == key(points[n]["prefix_declarations"]))
                controls = key(j["controls"])
                for oid in controls:
                    ob = nodes.get(oid) or {}
                    vis = nodes.get((sid, "V", *oid[2:])) or {}
                    require(oid[:4] == (sid,"O",statement,sc) and ob.get("kind") == "COLUMN_BINDING"
                            and ob["clause"] == "JOIN" and ob["join_stage"] == n and key(ob["operator_span"]) == on
                            and key(ob["relation"]) in inputs and vis.get("kind") == "JOIN_USE_VISIBLE"
                            and key(vis["occurrence"]) == oid and vis["ordinal"] == n
                            and key(vis["relation"]) == key(ob["relation"]))
                for rid in key(j["reads"]):
                    read = nodes.get(rid) or {}
                    require(read.get("kind") == "LOCAL_EXTRACT" and key(read["input"]) in controls)
                for literal in j["literals"]:
                    pair(literal, sql)
            except (_Refusal, KeyError, IndexError, ValueError, TypeError, AttributeError):
                break
            prefix_len, prev_inputs = n, inputs
        if prefix_len < max(points):
            at_use = "STAGE_UNVERIFIED"
        if not known_count or prefix_len != count:
            whole = "STAGE_UNVERIFIED"
    return {"status":whole, "use_prefix_status":at_use, "rowset_equivalence":"UNVERIFIED"}


def _project(graph, sql, dialect, statement, start, end):
    require(type(graph) is dict and type(sql) is str, UNAVAILABLE)
    snap = graph.get("snapshot")
    require(type(snap) is dict and snap.get("rules") == RULES and snap.get("dialect") == dialect
            and snap.get("sql_sha256") == sha256(sql.encode("utf-8")).hexdigest()
            and isinstance(snap.get("id"), str) and bool(snap["id"]), UNAVAILABLE)
    require("budget_gap" in graph, UNAVAILABLE)
    require(graph["budget_gap"] is None, "BUDGET_EXCEEDED")
    require(type(statement) is int and statement >= 1, "SITE_NOT_MATCHED")
    requested = pair((start, end), sql, "SITE_NOT_MATCHED")
    sid = snap["id"]
    nodes, rows, gaps = {}, [], []
    stage_scopes, relation_scopes = set(), set()
    for group in GROUPS:
        require(isinstance(graph.get(group), list), UNAVAILABLE)
        for row in graph[group]:
            require(isinstance(row, dict) and row.get("group") == group, UNAVAILABLE)
            ident = key(row["id"])
            require(type(ident) is tuple and len(ident) >= 3 and ident[0] == sid, UNAVAILABLE)
            # Detect multiple matching read sites before building a proof.
            rows.append((ident, row))
            if len(ident) == 4 and ident[:3] == (sid,"JS",statement):
                stage_scopes.add(ident[3])
            if len(ident) == 5 and ident[2] == statement:
                if ident[1] in ("J", "V") or "join_stage" in row:
                    stage_scopes.add(ident[3])
                if ident[1] == "R" and row.get("kind") == "ROW_INPUT":
                    if ident[3] in relation_scopes:
                        stage_scopes.add(ident[3])
                    relation_scopes.add(ident[3])
            if group == "gaps":
                gaps.append((ident, row))
            if ident in nodes:
                nodes[ident] = None
            else:
                nodes[ident] = row

    def matching_gap(scope, positions, reasons):
        return any(len(k) >= 5 and k[2] == statement and (scope is None or scope == k[3])
                   and key(v.get("anchor")) in positions and v.get("reason") in reasons
                   for k, v in gaps)

    matches = [(k, v) for k, v in rows if k[1] == "read" and len(k) == 5 and k[2] == statement
               and key(v.get("anchor")) == requested]
    if not matches:
        if matching_gap(None, {requested}, UNSUPPORTED_GAPS):
            raise _Refusal("SITE_UNSUPPORTED")
        raise _Refusal("SITE_NOT_MATCHED")
    require(len(matches) == 1, "SITE_NOT_UNIQUE")
    rid, local = matches[0]
    scope = rid[3]
    require(isinstance(scope, str) and scope and rid[4] == requested)
    require(local.get("kind") == "LOCAL_EXTRACT", "SITE_UNSUPPORTED")
    call = pair(local["operator_span"], sql)
    literal = pair(local["literal"], sql)
    operand = pair(local["operand"], sql)
    require(sql[slice(*requested)].lower() == "get_json_object"
            and call[0] == requested[0] and requested[1] <= operand[0] < operand[1] <= literal[0]
            and literal[1] < call[1] and sql[call[1]-1] == ")"
            and re.fullmatch(r"\s*\(\s*", sql[requested[1]:operand[0]])
            and re.fullmatch(r"\s*,\s*", sql[operand[1]:literal[0]])
            and re.fullmatch(r"\s*\)", sql[literal[1]:call[1]]))
    require(sql[literal[0]] in "'\"" and sql[literal[1]-1] == sql[literal[0]])
    path = local["path"]
    require(vector(path) and 1 <= len(path) <= 32, "SITE_UNSUPPORTED")
    tokens = []
    for token in path:
        require(vector(token) and len(token) == 2, "SITE_UNSUPPORTED")
        t, v = token
        require((t == "key" and type(v) is str) or (t == "index" and type(v) is int and v >= 0),
                "SITE_UNSUPPORTED")
        tokens.append({"kind": t, "value": v})

    clause, role = local["clause"], local["role"]
    require((clause, role) in {("SELECT","VALUE"), ("WHERE","CONDITION"), ("JOIN","CONDITION")},
            "SITE_UNSUPPORTED")
    group = "value_edges" if role == "VALUE" else "control_uses"
    require(local["group"] == group)
    proofs = [(k, v) for k, v in rows if v.get("kind") == "STRICT_READ" and key(v.get("local_read")) == rid]
    if not proofs:
        # Input can be scrubbed at export. Operand end identifies this call's
        # own column, not a similarly named column elsewhere in the predicate.
        owned = {requested}
        for k, g in gaps:
            a = key(g.get("anchor"))
            if (len(k) >= 5 and k[2:4] == (statement, scope) and type(a) is tuple and len(a) == 2
                    and all(type(n) is int for n in a) and operand[0] <= a[0] and a[1] == operand[1]):
                owned.add(a)
        if matching_gap(scope, owned, VISIBILITY_GAPS):
            raise _Refusal(VISIBLE)
        if matching_gap(scope, owned, UNSUPPORTED_GAPS):
            raise _Refusal("SITE_UNSUPPORTED")
        raise _Refusal(CHAIN)

    require(len(proofs) == 1, "SITE_NOT_UNIQUE")
    pid, proof = proofs[0]
    require(pid == (sid, "proof", rid) and nodes.get(pid) is proof and proof["group"] == group
            and key(proof["anchor"]) == requested and proof["domain"] == ("VALUE" if role == "VALUE" else "CONTROL"))
    trail = key(proof["dependencies"])
    require(isinstance(trail, tuple) and 2 <= len(trail) <= 98 and len(trail) % 3 == 2
            and len(set(trail)) == len(trail))
    require(key(local.get("input")) == trail[0])
    seen_visibility, hops = [], []

    def fetch(ident, kind, reason=CHAIN):
        node = nodes.get(ident)
        require(isinstance(node, dict) and node.get("kind") == kind, reason)
        return node

    def relation(ident, sc, reason=CHAIN):
        require(isinstance(ident, tuple) and len(ident) == 5 and ident[:4] == (sid,"R",statement,sc), reason)
        rel = fetch(ident, "ROW_INPUT", reason)
        decl = pair(rel["anchor"], sql, reason)
        require(ident[4] == decl and rel["group"] == "row_effects" and sql[slice(*decl)] == rel["name"], reason)
        parts = rel["parts"]
        require(vector(parts) and len(parts) > 0, reason)
        original = [pair(p, sql, reason) for p in parts]
        require(all(a[1] <= b[0] for a,b in zip(original, original[1:]))
                and (original[-1] == decl or original[-1][1] <= decl[0])
                and ".".join(sql[slice(*p)] for p in original) == rel["source"], reason)
        return {"scope": sc, "name": rel["name"], "source": rel["source"],
                "decl_span": out(decl), "name_spans": [out(p) for p in original]}

    for i in range(0, len(trail), 3):
        oid, r_id = trail[i:i+2]
        require(isinstance(oid, tuple) and len(oid) == 5 and oid[:3] == (sid, "O", statement))
        sc = oid[3]
        ob = fetch(oid, "COLUMN_BINDING")
        require(isinstance(sc, str) and sc and key(ob["relation"]) == r_id)
        col = pair(ob["anchor"], sql)
        qual = pair(ob["qualifier"], sql)
        opnd = pair(ob["operand"], sql)
        require(oid[4] == col and sql[slice(*col)] == ob["column"]
                and opnd[0] <= qual[0] < qual[1] <= col[0] and opnd[1] == col[1])
        rel = relation(r_id, sc)
        require(sql[slice(*qual)].casefold() == rel["name"].casefold())
        hop_clause = clause if i == 0 else "SELECT"
        require(ob["clause"] == hop_clause and ob["role"] == (role if i == 0 else "VALUE")
                and ob["group"] == (group if i == 0 else "value_edges"))
        if i == 0:
            require(sc == scope and opnd == operand)
        binding_site = pair(ob["operator_span"], sql)
        if hop_clause == "SELECT":
            require(binding_site == col)
        else:
            require(sql[slice(*binding_site)].upper() == ("ON" if hop_clause == "JOIN" else "WHERE"))
        vis = None
        vid = (sid, "V", statement, sc, col)
        if "join_stage" in ob:
            n = ob["join_stage"]
            v = fetch(vid, "JOIN_USE_VISIBLE", VISIBLE)
            on = pair(v["anchor"], sql, VISIBLE)
            require(type(n) is int and 1 <= n <= 32 and type(v["ordinal"]) is int and n == v["ordinal"]
                    and key(v["occurrence"]) == oid and key(v["relation"]) == r_id
                    and v["clause"] == ob["clause"] and v["group"] == ob["group"]
                    and sql[slice(*on)].upper() == "ON", VISIBLE)
            prefix = v["prefix_declarations"]
            require(vector(prefix) and len(prefix) == n+1, VISIBLE)
            spans = [pair(p, sql, VISIBLE) for p in prefix]
            require(r_id[4] in spans and all(a[1] <= b[0] for a,b in zip(spans,spans[1:]))
                    and spans[-1][1] <= on[0] and not sql[spans[-1][1]:on[0]].strip(), VISIBLE)
            names = [relation((sid,"R",statement,sc,p), sc, VISIBLE)["name"].casefold() for p in spans]
            require(len(set(names)) == len(names), VISIBLE)
            if hop_clause == "JOIN":
                require(binding_site == on and on[1] <= qual[0], VISIBLE)
            seen_visibility.append(vid)
            vis = {"stage": n, "on_span": out(on), "input_prefix": [out(p) for p in spans]}
        else:
            require(hop_clause != "JOIN" and sc not in stage_scopes and vid not in nodes, VISIBLE)
        endpoint = key(ob.get("endpoint"))
        producer = None
        if i+2 < len(trail):
            port, next_o = trail[i+2:i+4]
            require(port == endpoint and len(port) == 5 and port[:3] == (sid,"P",statement)
                    and type(port[4]) is int and port[4] >= 1 and len(next_o) == 5
                    and next_o[:4] == (sid,"O",statement,port[3]))
            p = fetch(port, "COLUMN_PASSTHROUGH")
            require(p["group"] == "value_edges" and key(p["input"]) == next_o and key(p["anchor"]) == next_o[4])
            label = pair(p["output_span"], sql)
            require(sql[slice(*label)] == p["output_name"]
                    and p["output_name"].lower() == ob["column"].lower())
            producer = {"statement": statement, "scope": port[3], "slot": port[4]}
        else:
            require(endpoint == (sid, "BASE", r_id, ob["column"]) and key(proof["terminal"]) == endpoint)
        hops.append({"scope": sc, "column": ob["column"], "column_span": out(col),
                     "qualifier_span": out(qual), "relation": rel, "producer": producer, "visibility": vis})

    require(key(proof.get("stage_dependencies", ())) == tuple(seen_visibility), VISIBLE)
    last = hops[-1]
    terminal = {"source": last["relation"]["source"], "column": last["column"], "scope": last["scope"],
                "decl_span": last["relation"]["decl_span"], "column_span": last["column_span"]}
    return {"snapshot_id": sid, "rules_version": RULES, "scope": scope, "role": role,
            "clause": "ON" if clause == "JOIN" else clause, "call_span": out(call),
            "path_literal_span": out(literal), "path_tokens": tokens, "hops": hops, "terminal": terminal,
            "row_boundary": row_boundary(nodes, seen_visibility, sid, statement, sql)}


def project(graph, sql, dialect, statement, start, end):
    """Return (None, witness) or a closed vocabulary refusal and no partial witness."""
    try:
        return None, _project(graph, sql, dialect, statement, start, end)
    except _Refusal as exc:
        return exc.args[0], None
    except (KeyError, TypeError, IndexError, ValueError, AttributeError, RecursionError):
        return CHAIN, None
