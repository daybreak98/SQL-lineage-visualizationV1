"""Review the observed local COALESCE inputs; no deletion or rewrite advice."""

from collections import Counter, defaultdict, deque


PORT_FIELDS = ("statement", "scope", "slot")
COALESCE_MAX_ARGUMENTS = 8


def is_coalesce_port_model(mapping):
    """Select recognized model tags, including those requiring an unresolved review."""
    return mapping.get("port_model") in ("COALESCE_2", "COALESCE_N")


def _port(record):
    return tuple(record[field] for field in PORT_FIELDS)


def _port_dict(key):
    return dict(zip(PORT_FIELDS, key))


def _positioned(read):
    position = read.get("position")
    if not isinstance(position, dict):
        return False
    start, end = position.get("start"), position.get("end")
    return type(start) is int and type(end) is int and 0 <= start < end


def _read_producer(read):
    producer = read.get("producer")
    if not isinstance(producer, dict):
        return None
    statement, scope, slot = (producer.get(field) for field in PORT_FIELDS)
    if type(statement) is int and type(scope) is str and scope and type(slot) is int and slot > 0:
        return statement, scope, slot
    return None


def _terminal(mapping):
    inputs = mapping.get("inputs", ())
    if (mapping.get("terminal_binding") != "SQL_NAMED_RELATION_COLUMN"
            or mapping.get("kind") != "WHOLE_RAW" or len(inputs) != 1):
        return None
    origin = inputs[0]
    if origin.get("path_tokens") != [] or not origin.get("source") or not origin.get("column"):
        return None
    return origin["source"], origin["column"]


def _branch(root, mappings, argument_count):
    # Edges are indexed consumer -> producer for the reverse traversal.
    reachable = {root: mappings[root]}
    incoming = defaultdict(list)
    pending = Counter()
    endpoints = {}
    unresolved = []
    extended = argument_count > 2
    unbound_producers = defaultdict(list)

    def gap(consumer, reason, slot=None, prefix=()):
        item = {"port": _port_dict(consumer), "reason": reason}
        if slot is not None:
            item["argument_slot"] = slot
        if extended and prefix:
            item["port_reads"] = list(prefix)
        unresolved.append(item)

    def binding_gap(consumer, reason, slot=None):
        if extended and consumer != root:
            # Attach the actually reached root slots after demand propagation.
            unbound_producers[consumer].append(reason)
        else:
            gap(consumer, reason, slot)

    queue = deque([root])
    while queue:
        consumer = queue.popleft()
        mapping = reachable[consumer]
        reads = mapping.get("port_reads") or []
        if consumer == root:
            slots = {slot: [] for slot in range(1, argument_count + 1)}
            for read in reads:
                slot = read.get("argument_slot")
                if (read.get("kind") == "COALESCE_INPUT"
                        and type(slot) is int and slot in slots):
                    slots[slot].append(read)
                else:
                    gap(consumer, "UNEXPECTED_COALESCE_EDGE")
            valid = []
            for slot, matches in slots.items():
                if len(matches) != 1:
                    gap(consumer, "MISSING_OR_AMBIGUOUS_ARGUMENT", slot)
                elif matches[0].get("path_tokens", []) != []:
                    gap(consumer, "UNSUPPORTED_ARGUMENT_PATH", slot)
                else:
                    valid.append(matches[0])
        elif not reads:
            endpoint = _terminal(mapping)
            if endpoint is None:
                binding_gap(consumer, "TERMINAL_BINDING_UNVERIFIED")
            else:
                endpoints[consumer] = endpoint
            continue
        else:
            if len(reads) != 1 or mapping.get("terminal_binding"):
                binding_gap(consumer, "AMBIGUOUS_PRODUCER_EDGE")
                continue
            read = reads[0]
            kind, tokens = read.get("kind"), read.get("path_tokens")
            if not ((kind == "EXTRACT" and tokens) or (kind == "PASSTHROUGH" and tokens == [])):
                binding_gap(consumer, "UNSUPPORTED_PRODUCER_EDGE")
                continue
            valid = reads

        for read in valid:
            producer = _read_producer(read)
            target = mappings.get(producer)
            if (producer is None or producer[0] != root[0] or target is None or target.get("root") is not False
                    or not _positioned(read)):
                binding_gap(consumer, "PRODUCER_BINDING_UNVERIFIED", read.get("argument_slot"))
                continue
            incoming[consumer].append((producer, read))
            pending[producer] += 1
            if producer not in reachable:
                reachable[producer] = target
                queue.append(producer)

    ready = deque(port for port in reachable if not pending[port])
    demands = defaultdict(list)
    demands[root].append((None, (), ()))
    by_source = {}
    processed = set()
    while ready:
        consumer = ready.popleft()
        processed.add(consumer)
        for reason in unbound_producers.get(consumer, ()):
            if demands[consumer]:
                for slot, _, evidence in demands[consumer]:
                    gap(consumer, reason, slot, evidence)
            else:
                gap(consumer, reason)
        if consumer in endpoints:
            for slot, path, evidence in demands[consumer]:
                if not path:
                    gap(consumer, "LITERAL_PATH_UNVERIFIED", slot, evidence)
                    continue
                paths = by_source.setdefault(endpoints[consumer], {})
                paths.setdefault(path, []).append({
                    "argument_slot": slot,
                    "reason": "COALESCE_ARGUMENT_OBSERVATION",
                    "terminal_port": _port_dict(consumer),
                    "port_reads": list(evidence),
                })
        for producer, read in incoming[consumer]:
            step = {"consumer": _port_dict(consumer), **read}
            for slot, path, evidence in demands[consumer]:
                if read["kind"] == "COALESCE_INPUT":
                    slot = read["argument_slot"]
                elif read["kind"] == "EXTRACT":
                    if path:
                        gap(consumer, "MULTIPLE_EXTRACTIONS_UNSUPPORTED", slot, evidence)
                        continue
                    path = tuple((token["kind"], token["value"]) for token in read["path_tokens"])
                demands[producer].append((slot, path, evidence + (step,)))
            pending[producer] -= 1
            if not pending[producer]:
                ready.append(producer)

    for port in reachable:
        if port not in processed:
            gap(port, "CYCLIC_OR_BLOCKED_PORT")

    entry = {
        "protected_output": _port_dict(root),
        "status": "UNRESOLVED" if unresolved else "OBSERVED",
        "rowset_verified": False,
        "unresolved": unresolved,
        "by_source": [
            {"source": source, "column": column, "paths": [
                {"path_tokens": [{"kind": kind, "value": value} for kind, value in path],
                 "reasons": reasons}
                for path, reasons in paths.items()
            ]}
            for (source, column), paths in by_source.items()
        ],
    }
    if extended:
        entry["argument_count"] = argument_count
    return entry


def _unresolved_root(key, reason, argument_count=None):
    entry = {
        "protected_output": _port_dict(key), "status": "UNRESOLVED", "by_source": [],
        "rowset_verified": False,
        "unresolved": [{"port": _port_dict(key), "reason": reason}],
    }
    if argument_count is not None:
        entry["argument_count"] = argument_count
    return entry


def build_branch_review(result, protected_outputs) -> dict:
    """Report observed path demands for explicitly selected, modeled roots."""
    mappings = {}
    roots = set()
    for mapping in result["mappings"]:
        key = _port(mapping)
        mappings[key] = None if key in mappings else mapping
        if mapping.get("root") is True and is_coalesce_port_model(mapping):
            roots.add(key)
    entries = []
    for key in dict.fromkeys(_port(output) for output in protected_outputs or ()):
        if key not in roots:
            continue
        mapping = mappings[key]
        if mapping is None:
            entries.append(_unresolved_root(key, "AMBIGUOUS_PROTECTED_PORT"))
        elif mapping.get("port_model") == "COALESCE_2":
            entries.append(_branch(key, mappings, 2))
        else:
            count = mapping.get("argument_count")
            if type(count) is not int or count < 3:
                entries.append(_unresolved_root(key, "INVALID_ARGUMENT_COUNT"))
            elif count > COALESCE_MAX_ARGUMENTS:
                entries.append(_unresolved_root(key, "ARITY_LIMIT", count))
            else:
                entries.append(_branch(key, mappings, count))
    status = ("UNRESOLVED" if any(e["status"] == "UNRESOLVED" for e in entries)
              else "OBSERVED" if entries else "NOT_APPLICABLE")
    return {"status": status, "rowset_verified": False, "by_protected_output": entries}
