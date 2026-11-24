"""Lossless same-response interning for already certified reads; not a resolver."""

from copy import deepcopy
import json
import re


BLOCK = "strict_use_evidence"
FIELD = "named_source_binding"
REF_KIND = "SQL_CTE_RELATION_CHAIN_REF"
FULL_KIND = "SQL_NAMED_RELATION_COLUMN"
MAX_HOPS = 8
MAX_BYTES = 32 * 1024
META = ("sql_sha256", "dialect", "schema_sha256", "sqlglot", "rules")
TERMINAL = ("relation_instance", "terminal_column_position", "terminal_qualifier_position")
_WIRE_SCALARS = (str, int, float, bool, type(None))


def wire(value, *, sort=False):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False, sort_keys=sort).encode("utf-8")


def _member_bytes(key, value):
    return len(wire({key: value})) - 1  # replace two braces with one comma


def _copy_wire(value):
    """Detach JSON data without rewalking a full, repeated proof graph."""
    kind = type(value)
    if kind is dict:
        return {k: _copy_wire(v) for k, v in value.items()}
    if kind is list:
        return [_copy_wire(v) for v in value]
    if kind is tuple:
        return tuple(_copy_wire(v) for v in value)
    if kind in _WIRE_SCALARS:
        return value
    return deepcopy(value)


def _must(allowed, message):
    if not allowed:
        raise ValueError(message)


def _snapshot(facts, snapshot):
    _must(isinstance(snapshot, dict) and set(snapshot) == set(META), "Unexpected snapshot shape")
    _must(all(isinstance(snapshot[k], str) and snapshot[k] for k in META), "Missing snapshot metadata")
    for key in ("sql_sha256", "schema_sha256"):
        _must(bool(re.fullmatch("[0-9a-f]{64}", snapshot[key])), "Invalid snapshot digest")
    _must(all(facts["coverage"].get(k) == snapshot[k] for k in ("sql_sha256", "dialect")),
          "Snapshot does not identify this response")


def _pos(value):
    _must(isinstance(value, dict) and type(value.get("start")) is int
          and type(value.get("end")) is int and 0 <= value["start"] < value["end"],
          "Missing source anchor")
    return value["start"], value["end"]


def _instance(obj, statement, scope=None):
    _must(isinstance(obj, dict) and type(obj.get("statement")) is int and obj["statement"] == statement
          and isinstance(obj.get("declaration_scope"), str) and obj["declaration_scope"]
          and (scope is None or obj["declaration_scope"] == scope)
          and isinstance(obj.get("name"), str) and obj["name"], "Incompatible relation instance")
    _pos(obj.get("declaration_position"))
    parts = obj.get("table_part_positions")
    _must(isinstance(parts, list) and parts, "Missing relation name anchors")
    for part in parts:
        _pos(part)


def _port(port, statement, scope=None):
    _must(isinstance(port, dict) and type(port.get("statement")) is int and port["statement"] == statement
          and isinstance(port.get("scope"), str) and port["scope"]
          and (scope is None or port["scope"] == scope)
          and type(port.get("slot")) is int and port["slot"] > 0, "Incompatible port")


def _qualified(proof):
    _pos(proof.get("column_position"))
    _pos(proof.get("qualifier_position"))


def _complete(row, proof):
    _must(isinstance(proof, dict) and proof.get("kind") == FULL_KIND
          and type(proof.get("via_version")) is int and proof["via_version"] == 1
          and not {"instance_ref", "tail_ref", "head_context"} & proof.keys(), "Expected complete V1 proof")
    via, sc = proof.get("via"), proof.get("scope")
    st = row.get("statement")
    _must(row.get("kind") == "EXTRACT" and not row.get("path_derivation") and type(st) is int and st > 0
          and isinstance(via, list) and via and isinstance(sc, str) and sc, "Unsupported proof occurrence")
    _, call_end = _pos(row.get("position"))
    literal_start, _ = _pos(row.get("json_path_position"))
    _qualified(proof)
    qualifier_start, qualifier_end = _pos(proof["qualifier_position"])
    column_start, column_end = _pos(proof["column_position"])
    _must(call_end <= qualifier_start < qualifier_end <= column_start < column_end <= literal_start,
          "Column anchor belongs to a different occurrence")
    if row.get("role") == "VALUE":
        _port(proof.get("consumer"), st, sc)
        _must("operator_position" not in proof, "Value occurrence carries a control operator")
    else:
        _must("consumer" not in proof, "Control occurrence borrows a value slot")
        _pos(proof.get("operator_position"))
    for i, hop in enumerate(via):
        _must(isinstance(hop, dict), "Malformed CTE hop")
        _instance(hop.get("relation_instance"), st, sc)
        if i:
            _qualified(hop)
        _port(hop.get("producer"), st)
        sc = hop["producer"]["scope"]
    _instance(proof.get("relation_instance"), st, sc)
    _pos(proof.get("terminal_column_position"))
    _pos(proof.get("terminal_qualifier_position"))


class _Table:
    def __init__(self):
        self.rows, self.ids, self.keys = [], {}, []

    def intern(self, row):
        key = wire(row, sort=True)
        if key not in self.ids:
            index = len(self.rows)
            self.ids[key] = index
            self.rows.append(_copy_wire(row))
            self.keys.append(key)
            return index, len(key) + bool(index)
        return self.ids[key], 0

    def rollback(self, length):
        while len(self.rows) > length:
            self.rows.pop()
            del self.ids[self.keys.pop()]


def encode(facts, staged, snapshot, *, max_added_bytes=MAX_BYTES, capture_budget=False):
    """Encode same-run complete bindings by existing use index; keep legacy facts intact.

    A budget-triggered empty or partial extension is explicit, not a coverage result.
    """
    _snapshot(facts, snapshot)
    _must(BLOCK not in facts and type(max_added_bytes) is int and 0 <= max_added_bytes <= MAX_BYTES,
          "Invalid extension input or byte budget")
    instances, tails = _Table(), _Table()
    header = {"version": 2, "snapshot": deepcopy(snapshot),
              "instances": instances.rows, "tails": tails.rows}
    full = lambda status, **extra: {**header, "status": status, **extra}
    # Reserve the worst possible budget-status overhead for an atomic prefix.
    # The final encoding typically consumes a few bytes less than the reserve.
    reasons = ("CAPTURE_BUDGET", "CHAIN_HOPS", "WIRE_BYTES")
    reserve = max(_member_bytes(BLOCK, full("BUDGET_EXCEEDED", reason=r)) for r in reasons)
    _must(max_added_bytes >= reserve, "Budget cannot encode an explicit status")
    pending, remaining = {}, max_added_bytes - reserve
    uses = facts["uses"]
    reason = "CAPTURE_BUDGET" if capture_budget else None
    if not capture_budget:
        order, located = [], set()
        for i, proof in staged.items():
            _must(type(i) is int and 0 <= i < len(uses) and FIELD not in uses[i], "Invalid native use index")
            row = uses[i]
            _complete(row, proof)
            site = row["statement"], _pos(row["position"])
            _must(site not in located, "Duplicate source occurrence")
            located.add(site)
            order.append((site, i))
        for _, i in sorted(order):
            proof = staged[i]
            via = proof["via"]
            if len(via) + 1 > MAX_HOPS:
                reason = "CHAIN_HOPS"
                break
            marks = len(instances.rows), len(tails.rows)
            cost = 0
            body = {k: proof[k] for k in TERMINAL}
            body["relation_instance"], cost = instances.intern(body["relation_instance"])
            attached = []
            for hop in via:
                relation, more = instances.intern(hop["relation_instance"])
                attached.append({**hop, "relation_instance": relation})
                cost += more
            first = attached[0]["relation_instance"]
            # Local JOIN visibility or other occurrence-local evidence is
            # never shared merely because the producer/terminal is shared.
            context = {k: v for k, v in attached[0].items() if k not in {"producer", "relation_instance"}}
            attached[0] = {"producer": attached[0]["producer"]}
            tail, more = tails.intern({**body, "via": attached})
            cost += more
            local = {k: v for k, v in proof.items() if k not in (*TERMINAL, "via_version", "via")}
            local.update(kind=REF_KIND, instance_ref=first, tail_ref=tail)
            if context:
                local["head_context"] = context
            cost += _member_bytes(FIELD, local)
            if cost > remaining:
                instances.rollback(marks[0])
                tails.rollback(marks[1])
                reason = "WIRE_BYTES"
                break
            remaining -= cost
            pending[i] = _copy_wire(local)
    head = (full("BUDGET_EXCEEDED", reason=reason) if reason
            else full("ATTACHED" if pending else "NOT_PROVED"))
    return {**facts, BLOCK: head,
            "uses": [{**row, FIELD: pending[i]} if i in pending else row for i, row in enumerate(uses)]}


def expand(encoded, expected_snapshot):
    """Strict inverse for V2 compatibility testing; reject dangling/orphaned references.

    Structural validation is not an attestation of externally supplied proofs.
    """
    _snapshot(encoded, expected_snapshot)
    block = encoded.get(BLOCK)
    _must(isinstance(block, dict) and type(block.get("version")) is int and block["version"] == 2
          and block.get("snapshot") == expected_snapshot, "Incompatible V2 snapshot")
    status, reason = block.get("status"), block.get("reason")
    _must((status == "BUDGET_EXCEEDED" and reason in {"WIRE_BYTES", "CHAIN_HOPS", "CAPTURE_BUDGET"})
          or (status in {"ATTACHED", "NOT_PROVED"} and reason is None), "Invalid extension status")
    tables = {name: block.get(name) for name in ("instances", "tails")}
    reached = {name: set() for name in tables}
    for rows in tables.values():
        _must(isinstance(rows, list) and all(isinstance(x, dict) for x in rows), "Invalid proof table")
        _must(len({wire(x, sort=True) for x in rows}) == len(rows), "Duplicate proof table entry")

    def lookup(name, index):
        _must(type(index) is int and 0 <= index < len(tables[name]), "Invalid proof reference")
        reached[name].add(index)
        return deepcopy(tables[name][index])

    uses, sites = [], set()
    for row in encoded["uses"]:
        ref = row.get(FIELD)
        if not isinstance(ref, dict) or ref.get("kind") != REF_KIND:
            uses.append(row)
            continue
        proof = lookup("tails", ref.get("tail_ref"))
        via = proof.get("via")
        _must(set(proof) == {*TERMINAL, "via"} and isinstance(via, list)
              and 1 <= len(via) < MAX_HOPS and all(isinstance(hop, dict) for hop in via),
              "Unclosed CTE suffix")
        _must(set(via[0]) == {"producer"}, "Local context may not be hidden in a tail")
        context = ref.get("head_context", {})
        _must(isinstance(context, dict) and not {"producer", "relation_instance"} & context.keys(),
              "Local context may not override the producer or the instance")
        local = lookup("instances", ref.get("instance_ref"))
        proof["relation_instance"] = lookup("instances", proof["relation_instance"])
        via[0].update(deepcopy(context))
        via[0]["relation_instance"] = local
        for hop in via[1:]:
            hop["relation_instance"] = lookup("instances", hop.get("relation_instance"))
        for k, value in ref.items():
            _must(k not in proof and k != "via_version", "Duplicate proof field")
            if k not in {"instance_ref", "tail_ref", "head_context", "kind"}:
                proof[k] = deepcopy(value)
        proof.update(kind=FULL_KIND, via_version=1)
        _complete(row, proof)
        site = row["statement"], _pos(row["position"])
        _must(site not in sites, "Duplicate source occurrence")
        sites.add(site)
        uses.append({**row, FIELD: proof})
    _must(all(len(reached[k]) == len(v) for k, v in tables.items()), "Orphaned proof table entry")
    _must((status != "ATTACHED" or sites) and (status != "NOT_PROVED" or not sites)
          and (reason != "CAPTURE_BUDGET" or not sites), "Status does not match published proofs")
    return {**{k: v for k, v in encoded.items() if k != BLOCK}, "uses": uses}
