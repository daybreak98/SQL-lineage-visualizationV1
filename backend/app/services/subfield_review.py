"""Local review of observed subfield facts; never authorizes a rewrite."""

PORT_FIELDS = ("statement", "scope", "slot")
CONTROL_ROLES = frozenset({"CONDITION", "RELATIONAL", "STRUCTURE", "REPRESENTATION", "ERROR"})
TERMINAL_BINDING = "SQL_NAMED_RELATION_COLUMN"


def _port(record):
    return tuple(record[field] for field in PORT_FIELDS)


def _trace_port(root, mappings):
    """Follow at most one literal extraction through recorded CTE reads."""
    current = root
    visited = {_port(root)}
    chain = []
    path = None
    while reads := current.get("port_reads"):
        if len(reads) != 1:
            return None
        read = reads[0]
        producer = _port(read["producer"])
        if producer in visited or producer[0] != root["statement"] or not read.get("position"):
            return None
        tokens = read["path_tokens"]
        if read["kind"] == "EXTRACT" and path is None and tokens:
            path = tokens
        elif read["kind"] != "PASSTHROUGH" or tokens:
            return None
        next_mapping = mappings.get(producer)
        if next_mapping is None or next_mapping.get("root") is not False:
            return None
        chain.append({"consumer": dict(zip(PORT_FIELDS, _port(current))), **read})
        visited.add(producer)
        current = next_mapping

    # Missing port_reads alone cannot distinguish a physical endpoint from a
    # derived slot whose upstream binding was not emitted.
    if current.get("terminal_binding") != TERMINAL_BINDING:
        return None
    inputs = current["inputs"]
    if current["kind"] != "WHOLE_RAW" or len(inputs) != 1:
        return None
    origin = inputs[0]
    if origin.get("path_tokens") != []:
        return None
    source = {"source": origin["source"], "column": origin["column"]}
    return source, path or [], chain, current


def _observed_demand(root, mappings):
    traced = _trace_port(root, mappings)
    if traced is None:
        return None
    source, path, chain, _ = traced
    if not path:
        return None
    # Corroborate the path computed from the real reads. Flattened inputs are
    # provenance for the physical endpoint; they never provide an edge.
    if not any(all(item.get(k) == v for k, v in source.items())
               and item.get("path_tokens") == path for item in root["inputs"]):
        return None
    return {
        "protected_output": dict(zip(PORT_FIELDS, _port(root))),
        **source,
        "path_tokens": path,
        "port_reads": chain,
    }


def _group_demands(entries):
    sources = {}
    for entry in entries:
        statement = entry["protected_output"]["statement"]
        source, column = entry["source"], entry["column"]
        paths = sources.setdefault((statement, source, column), {})
        path = tuple((token["kind"], token["value"]) for token in entry["path_tokens"])
        paths.setdefault(path, {
            "path_tokens": entry["path_tokens"], "protected_outputs": [],
        })["protected_outputs"].append(entry["protected_output"])
    return [
        {"statement": statement, "source": source, "column": column, "paths": list(paths.values())}
        for (statement, source, column), paths in sources.items()
    ]


def _candidate_assessment(result, review, mappings, candidates):
    def unknown(reason):
        return {"status": "UNKNOWN", "entries": [], "reason": reason}

    coverage = result.get("coverage", {})
    if result["unknowns"] or coverage.get("parsed") is not True or coverage.get("partial"):
        return unknown("ANALYSIS_INCOMPLETE")
    # This first slice uses Spark's ordinary statement parse, not the Hive
    # session-macro path, which can hide declarations from projection evidence.
    if coverage.get("dialect") != "spark" or {key[0] for key in mappings} != {1}:
        return unknown("REQUIRES_SINGLE_SPARK_STATEMENT")
    if not review["protected_outputs"]:
        return unknown("PROTECTED_OUTPUTS_UNSPECIFIED")
    if any(f["decision"] == "RETAIN_WHOLE" for f in review["findings"]):
        return unknown("PROTECTED_WHOLE_CARRIER")
    demands = review["observed_path_demands"]["by_protected_output"]
    if {_port(d["protected_output"]) for d in demands} != {
        _port(port) for port in review["protected_outputs"]
    }:
        return unknown("PROTECTED_PATH_UNVERIFIED")
    if any(result.get(field) for field in ("generators", "windows", "row_selections")):
        return unknown("COMPLEX_ROW_SEMANTICS")
    if any(use.get("role") in CONTROL_ROLES or use.get("clause") != "SELECT"
           for use in result["uses"]):
        return unknown("CONTROL_OR_STRUCTURAL_USE")
    # Use records alone cannot detect row modifiers such as DISTINCT.
    if coverage.get("locally_reviewable_projection_only") is not True:
        return unknown("PROJECTION_ONLY_NOT_VERIFIED")

    # Accept only the closed projection fragment. Position ties a CTE
    # passthrough occurrence to its port read; the direct terminal has only
    # a rendered projection, so require an unambiguous whole-carrier use.
    verified_reads = set()
    terminals = {}
    for mapping in mappings.values():
        if (mapping is None or mapping.get("target") is not None
                or mapping.get("kind") not in {"EXTRACT", "WHOLE_RAW"}):
            return unknown("UNSUPPORTED_PROJECTION")
        traced = _trace_port(mapping, mappings)
        if traced is None:
            return unknown("UNCLOSED_PROJECTION")
        source, path, chain, terminal = traced
        if (mapping["kind"] == "EXTRACT") != bool(path):
            return unknown("UNSUPPORTED_PROJECTION")
        carrier = (source["source"], source["column"])
        terminals[_port(terminal)] = (carrier, terminal)
        verified_reads.update(
            (carrier, edge["position"]["start"], edge["position"]["end"])
            for edge in chain if edge["kind"] == "PASSTHROUGH"
        )

    remaining = []
    observed = {}
    for use in result["uses"]:
        carrier = (use.get("source"), use.get("column"))
        tokens = use.get("path_tokens")
        if use.get("kind") == "EXTRACT" and use.get("role") == "VALUE":
            if not tokens or any(token["kind"] != "key" for token in tokens):
                return unknown("UNSUPPORTED_PATH")
            observed.setdefault(carrier, set()).add(tokens[0]["value"])
        elif (use.get("kind"), use.get("role"), tokens) == ("WHOLE_RAW", "CARRIER", []):
            position = use.get("position") or {}
            if (carrier, position.get("start"), position.get("end")) not in verified_reads:
                remaining.append((carrier, use))
        else:
            return unknown("UNVERIFIED_CARRIER_USE")

    for carrier, terminal in terminals.values():
        matches = [
            i for i, (seen_carrier, use) in enumerate(remaining)
            if seen_carrier == carrier and use.get("position") and use.get("expression")
            and terminal.get("expression") in {
                use["expression"], f'{use["expression"]} AS {terminal["output"]}',
            }
        ]
        if len(matches) != 1:
            return unknown("UNVERIFIED_CARRIER_USE")
        remaining.pop(matches[0])
    if remaining:
        return unknown("UNVERIFIED_CARRIER_USE")

    closed = {(d["source"], d["column"]) for d in demands}
    for demand in demands:
        path = demand["path_tokens"]
        if any(token["kind"] != "key" for token in path):
            return unknown("UNSUPPORTED_PATH")
        observed.setdefault((demand["source"], demand["column"]), set()).add(path[0]["value"])

    entries = []
    seen = set()
    for candidate in candidates:
        source, column = candidate["source"], candidate["column"]
        carrier = (source, column)
        for key in candidate["keys"]:
            if not isinstance(key, str):
                return unknown("EXPECTED_LITERAL_OBJECT_KEY")
            identity = (*carrier, key)
            if identity in seen:
                continue
            seen.add(identity)
            if carrier not in closed:
                status, reason = "UNKNOWN", "CARRIER_PATH_UNVERIFIED"
            elif key in observed.get(carrier, ()):
                status, reason = "OBSERVED", "OVERLAPS_OBSERVED_PATH"
            else:
                status, reason = "NOT_OBSERVED_NEEDS_VALIDATION", "KEY_EXISTENCE_AND_EFFECT_UNVERIFIED"
            entries.append({"source": source, "column": column, "key": key,
                            "status": status, "reason": reason})
    statuses = {entry["status"] for entry in entries}
    status = ("UNKNOWN" if not statuses or "UNKNOWN" in statuses else
              "NOT_OBSERVED_NEEDS_VALIDATION" if "NOT_OBSERVED_NEEDS_VALIDATION" in statuses else
              "OBSERVED")
    return {"status": status, "entries": entries,
            "reason": "LOCAL_OBSERVATION_ONLY" if entries else "CANDIDATE_KEYS_UNSPECIFIED"}


def build_review(result, protected_outputs, candidate_keys=None) -> dict:
    """Review explicitly selected root projections by their one-based SQL slots.

    Tuple requests and control observations describe the analyzer's observed
    scope; they are not causal links to a selected output or deletion proofs.
    """
    review = {
        "status": "PROTECTED_OUTPUTS_UNSPECIFIED",
        "scope": "LOCAL_SQL_ANALYSIS",
        "protected_outputs": [],
        "unmatched_protected_outputs": [],
        "findings": [],
        "observed_control_uses": [],
        "unknowns": result["unknowns"],
        "observed_path_demands": {"by_protected_output": [], "by_source": []},
    }
    if not protected_outputs:
        if candidate_keys is not None:
            review["candidate_assessment"] = {
                "status": "UNKNOWN", "entries": [], "reason": "PROTECTED_OUTPUTS_UNSPECIFIED",
            }
        return review

    review["status"] = "REVIEW_ONLY"
    roots = {
        _port(mapping): mapping
        for mapping in result["mappings"] if mapping.get("root") is True
    }
    mappings = {}
    for mapping in result["mappings"]:
        key = _port(mapping)
        # A duplicated port cannot prove a uniquely bound producer.
        mappings[key] = None if key in mappings else mapping
    entries = []
    for key in dict.fromkeys(_port(port) for port in protected_outputs):
        port = dict(zip(PORT_FIELDS, key))
        review["protected_outputs"].append(port)
        mapping = roots.get(key)
        if mapping is None:
            review["unmatched_protected_outputs"].append(port)
        elif mapping["kind"] == "WHOLE_RAW" and mapping["inputs"]:
            review["findings"].append({
                "decision": "RETAIN_WHOLE",
                "basis": "PROTECTED_ROOT_WHOLE_RAW",
                "protected_output": port,
                "evidence": mapping,
            })
        if mapping is not None and mappings.get(key) is mapping:
            entry = _observed_demand(mapping, mappings)
            if entry is not None:
                entries.append(entry)

    review["observed_path_demands"] = {
        "by_protected_output": entries, "by_source": _group_demands(entries),
    }

    for use in result["uses"]:
        if use.get("role") in CONTROL_ROLES:
            review["observed_control_uses"].append(use)
        if use.get("kind") == "TUPLE_REQUEST" and use.get("active") is not True:
            review["findings"].append({
                "decision": "NEEDS_PROOF",
                "basis": "TUPLE_SYNTAX_REQUEST",
                "scope": "LOCAL_SQL_ANALYSIS",
                "evidence": use,
            })
    if candidate_keys is not None:
        review["candidate_assessment"] = _candidate_assessment(result, review, mappings, candidate_keys)
    return review
