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


def _closed_direct_demands(result, mappings):
    """Each slot must consume one distinct, positioned use. No partial success."""
    coverage = result.get("coverage", {})
    if (not mappings or result["unknowns"] or coverage.get("dialect") != "spark"
            or coverage.get("parsed") is not True or coverage.get("partial")
            or coverage.get("locally_reviewable_projection_only") is not True
            or len(result["uses"]) != len(mappings)):
        return {}
    by_site = {}
    for use in result["uses"]:
        p = use.get("position") or {}
        site = use.get("statement"), p.get("start"), p.get("end")
        if (None in site or site in by_site or (use["kind"], use["role"], use["clause"]) !=
                ("EXTRACT", "VALUE", "SELECT")):
            return {}
        by_site[site] = use
    entries = {}
    for key, mapping in mappings.items():
        w = (mapping or {}).get("direct_extract_read")
        if (not w or w.get("projection_count") != len(mappings) or _port(w["port"]) != key
                or key[:2] != (1, "1:1") or not 1 <= key[2] <= len(mappings)
                or not mapping["root"] or mapping["target"] is not None or mapping["kind"] != "EXTRACT"
                or w.get("binding") != TERMINAL_BINDING):
            return {}
        p = w["position"]
        # The independently emitted projection anchor is its alias (or the
        # function token for the lone unnamed root). Never let a sibling use
        # satisfy this slot, even if both roots read the same key.
        anchor = mapping.get("position") or {}
        previous = mappings.get((*key[:2], key[2] - 1)) or {}
        lower = (previous.get("position") or {}).get("end", 0)
        if (not anchor or p["start"] < lower or
                (anchor != p and p["end"] > anchor["start"]) or
                mapping.get("port_reads") or mapping.get("terminal_binding") or
                len(mapping["inputs"]) != 1 or
                any(mapping["inputs"][0][k] != w[k] for k in ("source", "column", "path_tokens"))):
            return {}
        use = by_site.pop((key[0], p["start"], p["end"]), None)
        if (not use or use["position"] != p or any(use[k] != w[k] for k in ("source", "column", "path_tokens"))):
            return {}
        entries[key] = {"protected_output": w["port"], **{k: w[k] for k in ("source", "column", "path_tokens")},
                        "port_reads": [], "direct_extract_read": w}
    return entries if not by_site else {}


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


def _candidate_assessment(result, review, mappings, candidates, direct):
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
        if _port(mapping) in direct:
            continue  # Already matched to a distinct direct use. No WHOLE_RAW terminal.
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

    # Compare only spellings from the verified SQL projection. This index is
    # for explanations; aliases, identifier quoting and catalog identity
    # cannot be recovered from the flattened source label.
    source_spellings = {}
    for (source, _), _terminal in terminals.values():
        if source.isascii():
            source_spellings.setdefault(source.lower(), set()).add(source)

    # No per-carrier exclusion proof exists for an unregistered expression.
    # Only absence needs this inventory; a located positive read stands on its own.
    counts = coverage.get("projection_slot_counts") or {}
    projection_scope_closed = bool(counts) and set(mappings) == {
        (1, scope, slot) for scope, size in counts.items() for slot in range(1, size + 1)
    }
    entries = []
    seen = set()
    for candidate in candidates:
        source, column = candidate["source"], candidate["column"]
        carrier = (source, column)
        carrier_reason = "CARRIER_PATH_UNVERIFIED"
        if carrier not in closed and source.isascii():
            spellings = source_spellings.get(source.lower(), ())
            if source not in spellings and any((name, column) in closed for name in spellings):
                carrier_reason = ("SOURCE_NAME_CASE_AMBIGUOUS" if len(spellings) > 1
                                  else "SOURCE_NAME_CASE_MISMATCH_UNVERIFIED")
        for key in candidate["keys"]:
            if not isinstance(key, str):
                return unknown("EXPECTED_LITERAL_OBJECT_KEY")
            identity = (*carrier, key)
            if identity in seen:
                continue
            seen.add(identity)
            if carrier not in closed:
                status, reason = "UNKNOWN", carrier_reason
            elif key in observed.get(carrier, ()):
                status, reason = "OBSERVED", "OVERLAPS_OBSERVED_PATH"
            elif not projection_scope_closed:
                status, reason = "UNKNOWN", "PROJECTION_SCOPE_NOT_CLOSED"
            else:
                status, reason = "NOT_OBSERVED_NEEDS_VALIDATION", "KEY_EXISTENCE_AND_EFFECT_UNVERIFIED"
            entries.append({"source": source, "column": column, "key": key,
                            "status": status, "reason": reason})
    statuses = {entry["status"] for entry in entries}
    status = ("UNKNOWN" if not statuses or "UNKNOWN" in statuses else
              "NOT_OBSERVED_NEEDS_VALIDATION" if "NOT_OBSERVED_NEEDS_VALIDATION" in statuses else
              "OBSERVED")
    reason = "LOCAL_OBSERVATION_ONLY" if entries else "CANDIDATE_KEYS_UNSPECIFIED"
    if any(entry["reason"] == "PROJECTION_SCOPE_NOT_CLOSED" for entry in entries):
        reason = "PROJECTION_SCOPE_NOT_CLOSED"
    return {"status": status, "entries": entries, "reason": reason}


def _filtered_key_evidence(result, ports, candidates):
    coverage = result["coverage"]
    if (len(ports) != 1 or len(result["mappings"]) != 1 or len(result["uses"]) != 2
            or result["unknowns"] or coverage["partial"] or not coverage["parsed"]):
        return None
    mapping, = result["mappings"]
    site = mapping.get("filtered_read_site")
    if not site or not mapping["root"] or _port(mapping) != _port(ports[0]):
        return None
    value, control = site["value"], site["control"]
    if (_port(value["port"]) != _port(mapping) or value["binding"] != TERMINAL_BINDING
            or (control["statement"], control["scope"]) != _port(mapping)[:2]):
        return None
    def matches(use, fact, role, clause, kind, tokens):
        return (all(use[k] == fact[k] for k in ("source", "column", "position"))
                and use["statement"] == mapping["statement"] and use["path_tokens"] == tokens
                and (use["role"], use["clause"], use["kind"]) == (role, clause, kind))
    uses = result["uses"]
    if (not any(matches(u, value, "VALUE", "SELECT", "EXTRACT", value["path_tokens"]) for u in uses)
            or not any(matches(u, control, "CONDITION", "WHERE", "WHOLE_RAW", []) for u in uses)
            or not any(c["source"] == value["source"] and c["column"] == value["column"]
                       and value["path_tokens"][0]["value"] in c["keys"] for c in candidates)):
        return None
    return {"status": "OBSERVED", "basis": "LOCAL_VALUE_READ_ONLY", "rowset_verified": False,
            "pruning_authorized": False,
            "analysis": {**{k: coverage[k] for k in ("sql_sha256", "dialect", "sqlglot")},
                         "rule": "SINGLE_SOURCE_FILTER_EQ_V1", "schema_basis": "SQL_NAMED_RELATIONS"},
            "value": {**value, "role": "VALUE", "clause": "SELECT",
                      "relation_alias": control["relation_alias"], "relation_alias_position": control["relation_alias_position"]},
            "control": control}


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
    direct = _closed_direct_demands(result, mappings)
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
            entry = direct.get(key) or _observed_demand(mapping, mappings)
            if entry is not None:
                entries.append(entry)

    review["observed_path_demands"] = {
        "by_protected_output": entries, "by_source": _group_demands(entries),
    }

    coverage = result.get("coverage", {})
    analysis_status = coverage.get("analysis_status")
    if analysis_status == "NO_ANALYZABLE_SQL":
        review["path_demand_status"] = "NO_ANALYZABLE_SQL"
    elif (analysis_status == "ANALYSIS_INCOMPLETE" or coverage.get("parsed") is not True
          or coverage.get("partial") or result["unknowns"] or review["unmatched_protected_outputs"]):
        review["path_demand_status"] = "ANALYSIS_INCOMPLETE"
    elif {_port(entry["protected_output"]) for entry in entries} == {
        _port(port) for port in review["protected_outputs"]
    }:
        review["path_demand_status"] = "OBSERVED"
    elif analysis_status == "NO_JSON_USE_IN_SCOPE":
        review["path_demand_status"] = "NO_JSON_USE_IN_SCOPE"
    else:
        review["path_demand_status"] = "ANALYSIS_INCOMPLETE"

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
        review["candidate_assessment"] = _candidate_assessment(result, review, mappings, candidate_keys, direct)
        local = _filtered_key_evidence(result, review["protected_outputs"], candidate_keys)
        if local is not None:
            review["observed_candidate_read"] = local
    return review
