"""Reversible, same-run development candidate; no cache or replay."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
import logging

from sqlglot import exp

from app.api.strict_read_witness import row_boundary
from app.services.p25_strict.inner_shadow import InnerShadow, MAX_STAGES
from experiments.binding_shadow import Limits, ObservedAnalysis, Shadow as Recorder, span
from experiments.strict_use_wire_v2 import BLOCK, META, encode


FIELD = "named_source_binding"
VIA_VERSION = 1
MAX_HOPS = 8                 # actual relation instances, including the base table
CAPTURE_LIMITS = Limits(depth=MAX_HOPS - 1)
REGULAR_RULES = "binding-shadow-inner-2"  # c9's established warm proof envelope
CONDITIONAL_RULES = "binding-shadow-inner-3:conditional-slot-1"  # cold-only for now
NON_EQUAL_COMPARISONS = frozenset({exp.LT, exp.LTE, exp.GT, exp.GTE, exp.NEQ})


def _location(pos):
    return (pos["start"], pos["end"]) if pos else None


@dataclass(frozen=True)
class Hop:
    occurrence: tuple
    relation: tuple
    endpoint: tuple
    column: str
    qualifier: tuple
    visibility: tuple | None


class DevShadow(InnerShadow):
    # Keep c9/f3's already adopted lazy rank/accounting behavior while using
    # the product observer's anchored P descriptors and structural inventory.
    put = Recorder.put

    def __init__(self, *args):
        super().__init__(*args)
        self.sites = {}
        self.tails = {}  # actual same-snapshot producer key -> immutable closed suffix
        self.tail_bytes = {}
        self.boundary_grades = {}
        self.snapshot["rules"] = REGULAR_RULES

    def _producer_prefix_shape(self, on, anchor):
        if type(on) not in NON_EQUAL_COMPARISONS:
            return self.equality_shape(on, anchor)
        return all(type(column) is exp.Column and not column.db and not column.catalog
                   and self.anchored(column.args.get("table")) and self.anchored(column.this)
                   for column in (on.this, on.expression))

    def binding_stages(self, a, scope, clause):
        if not scope.is_cte or clause != "SELECT":
            yield from super().binding_stages(a, scope, clause)
            return
        # Only a producer's SELECT can use the wider structural inventory.
        # ON binding and finish_query's row-stage certificates still call
        # the equality-only path; declaration records below are not ON proof.
        q = scope.expression
        through_comparison = False
        for n, join, anchor, visible in self.stages(q, predicate_shape=self._producer_prefix_shape):
            through_comparison |= type(join.args["on"]) in NON_EQUAL_COMPARISONS
            if through_comparison and n == len(q.args["joins"]):
                for ref in visible:
                    self.relation(a.statement, a.scope_ids[scope], ref)
            yield n, join, anchor, visible

    def extract(self, analysis, call, tokens, scope, role, clause):
        if clause == "JOIN":
            # Retain the ON operand shape for row-stage grading only. It is
            # deliberately not added to the sites eligible for public identity.
            super().extract(analysis, call, tokens, scope, role, clause)
            return
        query = scope.expression
        if type(query) is not exp.Select or not scope.is_root:
            return
        owner = None
        if (role, clause) == ("VALUE", "SELECT"):
            item = call.parent
            if (type(item) is exp.Alias and item.parent is query and item.arg_key == "expressions"
                    and item.index is not None and (alias := self.anchored(item.args.get("alias")))):
                owner = (item.index + 1, alias)
        elif (role, clause) == ("CONDITION", "WHERE"):
            where = query.args.get("where")
            pred = call.parent
            if type(where) is exp.Where and type(pred) is exp.EQ and where.this is pred:
                other = pred.expression if pred.this is call else pred.this
                if type(other) is exp.Literal and other.is_string and (anchor := self.where_anchor(query)):
                    owner = (None, anchor)
        if owner is None:
            return
        super().extract(analysis, call, tokens, scope, role, clause)
        key = self.key("read", analysis.statement, analysis.scope_ids[scope], span(call))
        if self.records.get(key, {}).get("kind") == "LOCAL_EXTRACT":
            self.sites[key] = owner if self.sites.get(key, owner) == owner else None

    def _hop(self, occurrence):
        bound = self.records.get(occurrence, {})
        if bound.get("kind") != "COLUMN_BINDING" or not bound.get("qualifier"):
            return None
        relation, endpoint = bound["relation"], bound["endpoint"]
        decl = self.records.get(relation, {})
        if (relation[:4] != self.key("R", *occurrence[2:4]) or decl.get("kind") != "ROW_INPUT"
                or self.sql[slice(*bound["qualifier"])].lower() != decl["name"].lower()):
            return None
        if endpoint[1] == "BASE" and endpoint[2:] != (relation, bound["column"]):
            return None
        visibility = None
        statement, scope = occurrence[2:4]
        scope_stages = self.records.get(self.key("JS", statement, scope), {})
        if "join_stage" in bound:
            visibility = self.key("V", *occurrence[2:])
            proof = self.records.get(visibility, {})
            ordinal, count = bound["join_stage"], scope_stages.get("stage_count")
            if (proof.get("kind") != "JOIN_USE_VISIBLE" or proof["occurrence"] != occurrence
                    or proof["relation"] != relation or proof["ordinal"] != ordinal
                    or proof["clause"] != bound["clause"]
                    or scope_stages.get("kind") != "JOIN_SCOPE_STAGES"
                    or type(ordinal) is not int or type(count) is not int or not 1 <= ordinal <= count <= MAX_STAGES
                    or (bound["clause"] != "JOIN" and ordinal != count)
                    or (bound["clause"] == "JOIN" and proof["anchor"] != bound["operator_span"])
                    or self.sql[slice(*proof["anchor"])].upper() != "ON"
                    or decl["anchor"] not in proof["prefix_declarations"]):
                return None
            prefix = proof["prefix_declarations"]
            if (len(prefix) != ordinal + 1 or any(a[1] > b[0] for a, b in zip(prefix, prefix[1:]))
                    or prefix[-1][1] > proof["anchor"][0]
                    or self.sql[prefix[-1][1]:proof["anchor"][0]].strip()):
                return None
            members = [self.records.get(self.key("R", statement, scope, span), {}) for span in prefix]
            if (any(member.get("kind") != "ROW_INPUT" or member["anchor"] != span
                    for member, span in zip(members, prefix, strict=True))
                    or len({member["name"].casefold() for member in members}) != len(members)):
                return None
        elif scope_stages:
            return None
        return Hop(occurrence, relation, endpoint, bound["column"], bound["qualifier"], visibility)

    def _producer_input(self, consumer):
        """Check the actual selected output label/ordinal on every transition."""
        producer = consumer.endpoint
        if (len(producer) != 5 or producer[:3] != self.key("P", consumer.occurrence[2])
                or type(producer[4]) is not int or producer[4] <= 0):
            return None
        port = self.records.get(producer, {})
        if port.get("kind") != "COLUMN_PASSTHROUGH" or port.get("group") != "value_edges":
            return None
        occurrence, output_span = port["input"], port["output_span"]
        if (len(occurrence) != 5 or occurrence[:4] != self.key("O", *producer[2:4])
                or port["anchor"] != occurrence[4] or not 0 <= output_span[0] < output_span[1] <= len(self.sql)
                or self.sql[slice(*output_span)] != port["output_name"]
                or port["output_name"].lower() != consumer.column.lower()):
            return None
        record = self.records.get(occurrence, {})
        if record.get("clause") == "SELECT":
            return occurrence
        return None

    def _expand_tail(self, consumer, anchor, occurrence):
        # Follow only actual bound, bare-column producer slots. Reuse a closed
        # suffix even when reached through a different local occurrence.
        prefix, seen = [], set()
        while True:
            producer = consumer.endpoint
            # Even a cached suffix cannot attest another occurrence's choice
            # of producer/label. Only its already verified internal steps share.
            if occurrence is None:
                return None
            if producer in seen:
                return None
            tail = self.tails.get(producer)
            if tail is not None:
                if len(prefix) + len(tail) > self.limits.depth:
                    self.limit("DEPTH_BUDGET", anchor)
                    return None
                break
            if len(prefix) >= self.limits.depth:
                self.limit("DEPTH_BUDGET", anchor)
                return None
            seen.add(producer)
            hop = self._hop(occurrence)
            if hop is None:
                return None
            prefix.append((producer, hop))
            if hop.endpoint[1] == "BASE":
                tail = ()
                break
            if hop.endpoint[1] != "P":
                return None
            consumer = hop
            occurrence = self._producer_input(consumer)
        for port, hop in reversed(prefix):
            tail = (hop, *tail)
            if not self.remember(self.tail_bytes, port, tuple(item.occurrence for item in tail),
                                 1, "SUFFIX_MEMO_BUDGET", anchor):
                return None
            self.tails[port] = tail
        return tail

    def chain(self, read, row):
        local = self._hop(read["input"])
        if local is None or local.endpoint[1] != "P":
            return None  # native direct reads already have their own contract
        occurrence = self._producer_input(local)
        if occurrence is None:
            return None
        tail = self.tails.get(local.endpoint)
        if tail is None:
            tail = self._expand_tail(local, read["anchor"], occurrence)
        if not tail:
            return None
        terminal = tail[-1]
        if (self.records[terminal.relation]["source"], terminal.column) != (row["source"], row["column"]):
            return None
        hops = (local, *tail)
        for hop in hops:
            if not self.remember(self.paths, (hop.relation, hop.endpoint, read["role"]),
                                 read["path"], self.limits.paths, "DISTINCT_PATH_BUDGET", read["anchor"]):
                return None
            if hop.endpoint[1] == "P" and not self.remember(self.expanded, row["statement"], hop.relation,
                                                          self.limits.refs, "REFERENCE_BUDGET", read["anchor"]):
                return None
        return hops

    def grade_rows(self, hops):
        """Apply e8's separate row-stage grader to already verified V records."""
        used = tuple(hop.visibility for hop in hops if hop.visibility is not None)
        if not used:
            return None
        statement = used[0][2]
        # Equal validated stage/prefix coordinates have equal row semantics,
        # while their column occurrences, instances and value slots stay distinct.
        signature = (statement, tuple((vid[3], v["ordinal"], v["anchor"], tuple(v["prefix_declarations"]))
                                      for vid in used for v in [self.records[vid]]))
        if signature not in self.boundary_grades:
            self.boundary_grades[signature] = row_boundary(self.records, used, self.sid, statement, self.sql)
        return self.boundary_grades[signature]


def _stage(facts, shadow):
    uses = defaultdict(list)
    for index, row in enumerate(facts["uses"]):
        uses[row["statement"], _location(row.get("position"))].append((index, row))
    roots = defaultdict(list)
    root_scopes = set()
    for row in facts["mappings"]:
        if row.get("root") is True and row.get("target") is None:
            roots[row["statement"], row["scope"], row["slot"]].append(row)
            root_scopes.add((row["statement"], row["scope"]))

    line_starts = [0, *(i + 1 for i, c in enumerate(shadow.sql) if c == "\n")]
    instances = {}

    def pos(p):
        start, end = p
        line = bisect_right(line_starts, start)
        return {"start": start, "end": end, "line": line, "column_end": end - line_starts[line - 1]}

    def instance(relation):
        if relation not in instances:
            _, _, statement, scope, _ = relation
            record = shadow.records[relation]
            instances[relation] = {"statement": statement, "declaration_scope": scope, "name": record["name"],
                                   "declaration_position": pos(record["anchor"]),
                                   "table_part_positions": [pos(p) for p in record["parts"]]}
        return instances[relation]

    def column(hop):
        return {"column_position": pos(hop.occurrence[4]), "qualifier_position": pos(hop.qualifier)}

    def port(statement, scope, slot):
        return {"statement": statement, "scope": scope, "slot": slot}

    def visibility(hop):
        if hop.visibility is None:
            return {}
        proof = shadow.records[hop.visibility]
        return {"join_visibility": {"ordinal": proof["ordinal"], "on_position": pos(proof["anchor"]),
                                    "prefix_declarations": [pos(p) for p in proof["prefix_declarations"]]}}

    # Sort candidate sites by original text, not traversal/output order. Match
    # by the original occurrence only; flat source is a terminal cross-check.
    sites = defaultdict(list)
    for key, owner in shadow.sites.items():
        sites[key[2], key[4]].append((key, owner))
    pending = {}
    shadow.collecting = False
    for location, owned in sorted(sites.items()):
        native = uses.get(location, ())
        if len(owned) != 1 or len(native) != 1:
            continue
        [(key, owner)], [(index, row)] = owned, native
        read = shadow.records.get(key, {})
        if (owner is None or row.get("kind") != "EXTRACT" or FIELD in row or row.get("path_derivation")
                or read.get("kind") != "LOCAL_EXTRACT" or (key[2], key[3]) not in root_scopes
                or (read["role"], read["clause"]) != (row["role"], row["clause"])
                or read["literal"] != _location(row.get("json_path_position"))
                or [{"kind": k, "value": v} for k, v in read["path"]] != row["path_tokens"]):
            continue
        slot, anchor = owner
        if slot is not None:
            mappings = roots[key[2], key[3], slot]
            if len(mappings) != 1 or anchor != _location(mappings[0].get("position")):
                continue
        else:
            filter_ = shadow.records.get(shadow.key("FILTER", key[2], key[3]), {})
            if filter_.get("kind") != "FILTER" or filter_["anchor"] != anchor:
                continue
        hops = shadow.chain(read, row)
        if shadow.first_limit is not None:
            return {}  # lost witness budget: no partial additions
        if not hops:
            continue
        *via, terminal = hops
        identity = {"kind": "SQL_NAMED_RELATION_COLUMN", "via_version": VIA_VERSION, "scope": key[3],
                    **column(via[0]), "relation_instance": instance(terminal.relation),
                    "terminal_column_position": pos(terminal.occurrence[4]),
                    "terminal_qualifier_position": pos(terminal.qualifier),
                    "via": [{"relation_instance": instance(hop.relation), "producer": port(*hop.endpoint[2:]),
                             **visibility(hop), **(column(hop) if i else {})} for i, hop in enumerate(via)]}
        identity.update({"terminal_" + name: cert for name, cert in visibility(terminal).items()})
        # Only crossings newly needing conditional semantics receive the new
        # context. Previously accepted (sealed) producer transfers keep the
        # ordinary wire shape, as do local JOIN reads with a plain producer.
        transfer = shadow.grade_rows(hops[1:])
        if transfer is not None and transfer["use_prefix_status"] == "STAGE_UNVERIFIED":
            identity.update(identity_condition="ON_ROWS_PRODUCED_BY_SLOT", row_boundary=shadow.grade_rows(hops))
        if slot is None:
            identity["operator_position"] = pos(anchor)
        else:
            identity["consumer"] = port(key[2], key[3], slot)
        pending[index] = identity
    return pending


def capture_compact_identities(sql, dialect, schemas):
    """Observe exactly one resolver; defer optional staging and encoding."""
    try:
        analysis = ObservedAnalysis(sql, dialect, schemas, CAPTURE_LIMITS, DevShadow)
    except Exception:
        from app.services.subfield import analyze_subfields
        return analyze_subfields(sql, dialect, schemas), None
    facts = analysis.run()
    return facts, compact_packer(analysis, facts)


def compact_packer(analysis, facts):
    """Retain the existing V2 renderer for an already completed same-run observer."""
    if analysis.shadow_failed or not facts["coverage"]["parsed"] or facts["coverage"]["partial"]:
        return None
    shadow = analysis.shadow
    raw = dict(facts)  # the controller may add a top-level review later

    def pack():
        try:
            staged = {} if shadow.first_limit is not None else _stage(raw, shadow)
            snapshot = {k: shadow.snapshot[k] for k in META}
            if any("identity_condition" in proof for proof in staged.values()):
                # Do not admit new conditional semantics to c9's unchanged
                # warm verifier: it requires REGULAR_RULES exactly.
                snapshot["rules"] = CONDITIONAL_RULES
            return encode(raw, staged, snapshot, capture_budget=shadow.first_limit is not None)
        except Exception:
            logging.getLogger(__name__).debug("Compact identity attachment unavailable", exc_info=True)
            return None

    return pack
