"""Experimental adapter, not wired to the product or the public cache."""
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import secrets

NAMESPACE = "strict-facts:v1"
MAX_DESCRIPTOR_BYTES = 16 * 1024

def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(blob):
    return sha256(blob).hexdigest()

@dataclass(frozen=True)
class Descriptor:
    sql: str
    dialect: str
    dialect_mode: str
    schema: object
    parser_version: str
    resolver_version: str
    rules_version: str
    wire_version: str
    budget_version: str
    identity_mode: str
    flags: object

    def key(self):
        # Actual resolver input context supplied by the caller. Retain JSON order,
        # explicit/omitted distinctions and exact spellings; never parse for a key.
        raw = wire([self.sql, self.dialect, self.dialect_mode, self.schema,
                    self.parser_version, self.resolver_version, self.rules_version,
                    self.wire_version, self.budget_version, self.identity_mode, self.flags])
        if len(raw) > MAX_DESCRIPTOR_BYTES:
            raise ValueError("strict descriptor exceeds the inherited cap")
        desc = wire([digest(self.sql.encode("utf-8")), self.dialect, self.dialect_mode,
                     digest(wire(self.schema)), self.resolver_version, self.rules_version,
                     self.wire_version, self.budget_version, self.identity_mode, self.flags])
        return NAMESPACE, self.parser_version, desc

@dataclass(frozen=True)
class Capture:
    key: tuple
    facts: dict
    proof: list
    status: str

@dataclass(frozen=True)
class _Pending:
    owner: object
    key: tuple
    blob: bytes
    generation: int

class Sidecar:
    def __init__(self, private_store, *, verifier, verified_once=False):
        self.store = private_store
        self.verifier = verifier
        self._owner = object()
        # Local-to-this-cache proof admission seal. No disk or caller-provided
        # data is trusted; only this instance can admit a verified envelope.
        self._seal = secrets.token_bytes(32) if verified_once else None

    def _tag(self, blob):
        return hmac.digest(self._seal, blob, "sha256")

    def _admissible(self, descriptor, facts, proof):
        # New enrichment lives only in proof. The caller/verifier must know the
        # authoritative raw fact shape (old named_source_binding is allowed).
        return (type(facts) is dict and "review" not in facts and "strict_read_evidence" not in facts
                and type(proof) is list and bool(proof) and self.verifier(descriptor, facts, proof) is True)

    def lookup(self, descriptor, *, allowed):
        if not allowed:
            return None
        try:
            key = descriptor.key()
            raw = self.store.get(key)
            if raw is None:
                return None
            if self._seal is not None:
                signature, raw = raw[:32], raw[32:]
                if not hmac.compare_digest(signature, self._tag(raw)):
                    return None
            item = json.loads(raw)
            if (item["identity"] != digest(wire([key[0], key[1], key[2].decode("utf-8")]))
                    or item["status"] != "COMPLETE"
                    or (self._seal is None and not self._admissible(descriptor, item["facts"], item["proof"]))):
                return None
            return Capture(key, item["facts"], item["proof"], item["status"])
        except Exception:
            return None

    def prepare(self, descriptor, capture, *, allowed, generation):
        # generation must be sampled before running the single resolver.
        if not allowed:
            return None
        try:
            key = descriptor.key()
            if (capture.key != key or capture.status != "COMPLETE"
                    or not self._admissible(descriptor, capture.facts, capture.proof)):
                return None
            blob = wire({"identity": digest(wire([key[0], key[1], key[2].decode("utf-8")])),
                         "status": capture.status, "facts": capture.facts, "proof": capture.proof})
            if self._seal is not None:
                blob = self._tag(blob) + blob
            return _Pending(self._owner, key, blob, generation)
        except Exception:
            return None

    def publish(self, pending, *, completed):
        # Call only after the base response succeeded within the original fill
        # window and the normal local-delivery authorization still passes.
        if not completed or pending is None or pending.owner is not self._owner:
            return
        try:
            self.store.put(pending.key, pending.blob, pending.generation)
        except Exception:
            pass
