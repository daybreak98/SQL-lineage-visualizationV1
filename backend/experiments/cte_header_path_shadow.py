"""Offline field mapping across an explicit CTE column list; no public wire."""
from collections import defaultdict

from sqlglot import exp

from app.services.subfield import analyze_subfields, only_projection_args
from experiments.binding_shadow import Limits, span
from experiments.single_cte_name_shadow import Capture, position


VERSION = "cte-header-path-shadow:1"


def _input(scope, source=None):
    """Return the actual sole FROM node if Scope agrees by object identity."""
    frm = scope.expression.args.get("from_")
    sources = scope.selected_sources
    if frm is None or len(sources) != 1:
        return None
    ref, resolved = next(iter(sources.values()))
    if (type(ref) is exp.Table and ref is frm.this
            and resolved is (ref if source is None else source)
            and not ref.alias_column_names
            and only_projection_args(ref, {"this", "db", "catalog", "alias"})):
        return ref


class HeaderCapture(Capture):
    """Reuse original token validation and single-root tracking from Capture."""

    def header_witnesses(self, facts):
        root = self.root
        shadow = self.shadow
        if (root is None or self.shadow_failed or shadow.first_limit
                or not facts["coverage"]["parsed"] or facts["coverage"]["partial"]
                or len(self.scope_ids) != 2 or not only_projection_args(root, {"with_", "from_", "expressions"})
                or len(root.selects) > 64 or any(i.is_star for i in root.selects)):
            return []
        with_ = root.args.get("with_")
        if not with_ or not only_projection_args(with_, {"expressions"}) or len(with_.expressions) != 1:
            return []
        cte, = with_.expressions
        producer = cte.this
        if (not only_projection_args(cte, {"this", "alias"}) or type(producer) is not exp.Select
                or not only_projection_args(producer, {"from_", "expressions"})
                or len(producer.selects) > 64 or any(i.is_star for i in producer.selects)):
            return []
        alias = cte.args["alias"]
        cte_name = self.token(alias.this)
        names = [x.name.lower() for x in alias.columns]
        anchors = [self.token(x) for x in alias.columns]
        scopes = {id(s.expression):s for s in self.scope_ids}
        consumer, source = scopes[id(root)], scopes[id(producer)]
        if (not consumer.is_root or not source.is_cte or source in self.open_scopes
                or not cte_name or not names or not all(anchors)
                or names != [x.lower() for x in source.outer_columns]
                or len(names) != len(producer.selects) or len(set(names)) != len(names)):
            return []
        ref, base = _input(consumer, source), _input(source)
        if (ref is None or base is None or ref.db or ref.catalog or ref.name.lower() != cte.alias.lower()
                or not all(self.token(x) for x in (*base.parts, *ref.parts))):
            return []
        ref_anchor = self.token(ref.args["alias"].this if ref.alias else ref.this)
        base_anchor = self.token(base.args["alias"].this if base.alias else base.this)
        if not ref_anchor or not base_anchor:
            return []

        st, sc, upstream = self.statement, self.scope_ids[consumer], self.scope_ids[source]
        key, record = shadow.key, shadow.records.get
        terminal_rel = key("R",st,upstream,base_anchor)
        terminal_row = record(terminal_rel, {})
        if terminal_row.get("kind") != "ROW_INPUT":
            return []
        ports, uses = defaultdict(list), defaultdict(list)
        for m in facts["mappings"]:
            ports[m["statement"],m["scope"],m["slot"]].append(m)
        for i,u in enumerate(facts["uses"]):
            uses[u["statement"],position(u.get("position"))].append((i,u))
        out = []
        for slot,item in enumerate(root.selects,1):
            if type(item) is not exp.Alias or not (output_name := self.token(item.args["alias"])):
                continue
            call = item.this
            if type(call) not in (exp.JSONExtract,exp.JSONExtractScalar) or type(call.this) is not exp.Column:
                continue
            col = call.this
            col_anchor, qual = self.token(col.this), self.token(col.args.get("table"))
            if not col_anchor or not qual or col.db or col.catalog or col.table.lower() != ref.alias_or_name.lower():
                continue
            read = record(key("read",st,sc,span(call)), {})
            located, mapping = uses[st,span(call)], ports[st,sc,slot]
            if (read.get("kind") != "LOCAL_EXTRACT" or read["clause"] != "SELECT" or read["role"] != "VALUE"
                    or read["input"] != key("O",st,sc,col_anchor) or len(located) != 1 or len(mapping) != 1):
                continue
            m, = mapping
            edges = m.get("port_reads", [])
            if not m["root"] or position(m.get("position")) != output_name or len(edges) != 1:
                continue
            edge, = edges
            port = edge["producer"]  # actual same-run bound_cte_read output, not inferred from visible names
            n = port["slot"]
            if (port["scope"] != upstream or port["statement"] != st or not 1 <= n <= len(names)
                    or names[n-1] != col.name.lower() or edge["kind"] != "EXTRACT"
                    or position(edge["position"]) != col_anchor
                    or position(edge.get("json_path_position")) != read["literal"]):
                continue
            registered = ports[st,upstream,n]
            if (len(registered) != 1 or registered[0]["root"]
                    or registered[0]["output"].lower() != names[n-1] or registered[0]["kind"] != "WHOLE_RAW"):
                continue
            producer_item = producer.selects[n-1]
            raw = producer_item.this if type(producer_item) is exp.Alias else producer_item
            if type(raw) is not exp.Column or raw.db or raw.catalog or raw.table.lower() != base.alias_or_name.lower():
                continue
            raw_anchor, raw_qual = self.token(raw.this), self.token(raw.args.get("table"))
            inner_name = self.token(producer_item.args["alias"]) if type(producer_item) is exp.Alias else raw_anchor
            if not raw_anchor or not raw_qual or not inner_name:
                continue
            transfer = record(key("P",st,upstream,n), {})
            occurrence = key("O",st,upstream,raw_anchor)
            terminal = record(occurrence, {})
            if (transfer.get("kind") != "COLUMN_PASSTHROUGH" or transfer["input"] != occurrence
                    or terminal.get("kind") != "COLUMN_BINDING" or terminal["relation"] != terminal_rel
                    or terminal["qualifier"] != raw_qual or terminal["endpoint"] != key("BASE",terminal_rel,raw.name)):
                continue
            index,u = located[0]
            tokens = [dict(kind=k,value=v) for k,v in read["path"]]
            if (u.get("kind") != "EXTRACT" or (u["role"],u["clause"]) != ("VALUE","SELECT")
                    or position(u.get("json_path_position")) != read["literal"]
                    or tokens != u["path_tokens"] or tokens != edge["path_tokens"]
                    or (u["source"],u["column"]) != (terminal_row["source"],raw.name)):
                continue
            out.append(dict(use_index=index, kind="CTE_HEADER_ORDINAL_PASSTHROUGH",
                            producer=dict(port), consumer=dict(statement=st,scope=sc,slot=slot),
                            cte_name_span=cte_name, header_name_span=anchors[n-1], producer_name_span=inner_name,
                            input_declaration_span=ref_anchor, column_span=col_anchor, qualifier_span=qual,
                            call_span=read["anchor"], literal_span=read["literal"], path_tokens=tokens,
                            terminal=dict(source=terminal_row["source"],column=raw.name,column_span=raw_anchor,
                                          qualifier_span=raw_qual,declaration_span=base_anchor)))
        return out


def observe(sql):
    """Return ordinary facts and a detached private witness; Spark only."""
    side = dict(version=VERSION,catalog_verified=False,value_equivalence="UNVERIFIED",
                rowset_equivalence="UNVERIFIED",pruning_authorized=False,witnesses=[])
    if len(sql) > 32768:
        return analyze_subfields(sql,"spark"),side
    a = HeaderCapture(sql,"spark",None,Limits(edges=512,memo_bytes=128*1024))
    facts = a.run()
    side["snapshot"] = dict(a.shadow.snapshot)
    try:
        side["witnesses"] = a.header_witnesses(facts)
    except Exception:
        side["reason"] = "SHADOW_UNAVAILABLE"
    return facts,side
