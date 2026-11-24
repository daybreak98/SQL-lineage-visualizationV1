"""Single static read lookup. Never accepts roots, never invokes key review."""
from hashlib import sha256
import os

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.services.subfield_parser import parse_with_json_path_positions

VERSION = "strict-read.v1"
MAX_CHARS = 16384
UPSTREAM_EXECUTOR_SHA = "f3113ed9173e6aea9a602bb224c1dbfe51b03083"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CallPosition(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def nonempty(self):
        if self.end <= self.start:
            raise ValueError("empty call position")
        return self


class StrictReadSite(StrictModel):
    sql_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)
    statement: int = Field(ge=1)
    call_position: CallPosition


def enabled():
    return os.environ.get("SUBFIELD_STRICT_READ_TRIAL") == "1"


def execute(sql, dialect):
    from app.services.p25_strict.binding_shadow import offline_analyze

    # A fresh snapshot even for two consecutive clicks in identical text.
    return offline_analyze(sql, dialect, enabled=True, inner_joins=True)[1]


def is_mixed(request):
    return bool(request.model_fields_set.intersection({"candidate_keys", "protected_outputs"})
                or request.include_two_step_evidence)


def refusal(sql, dialect, reason):
    return dict(version=VERSION, sql_sha256=sha256(sql.encode("utf-8")).hexdigest(),
                dialect=dialect, site=None, status="UNVERIFIED", reason=reason)


def prepare(request, mixed):
    """Cheap parent checks only. No parser, observer or unbounded IPC payload."""
    sql = request.sql
    def no(reason):
        return None, refusal(sql, request.dialect, reason)
    if mixed:
        return no("MIXED_REQUEST")
    if "dialect" not in request.model_fields_set or request.dialect != "spark":
        return no("DIALECT_UNSUPPORTED")
    if request.source_schemas is not None:
        return no("EXTERNAL_SCHEMA_UNSUPPORTED")
    if len(sql) > MAX_CHARS:
        return no("SQL_BUDGET_EXCEEDED")
    try:
        sel = StrictReadSite.model_validate(request.strict_read_site)
    except ValidationError:
        return no("INVALID_SELECTOR")
    if sel.sql_sha256 != sha256(sql.encode("utf-8")).hexdigest():
        return no("SQL_HASH_MISMATCH")
    if sel.statement != 1:
        return no("STATEMENT_UNSUPPORTED")
    start, end = sel.call_position.start, sel.call_position.end
    if end > len(sql) or sql[start:end].lower() != "get_json_object":
        return no("SITE_NOT_MATCHED")
    return dict(sql=sql, dialect=request.dialect, strict_read_site=sel.model_dump()), None


def worker_evidence(payload):
    """Only the bounded worker performs fresh AST parsing, observation and projection."""
    sql, dialect = payload["sql"], payload["dialect"]
    sel = StrictReadSite.model_validate(payload["strict_read_site"])
    common = dict(version=VERSION, sql_sha256=sel.sql_sha256, dialect=dialect, site=None)
    start, end = sel.call_position.start, sel.call_position.end

    def reject(reason):
        return {**common, "status":"UNVERIFIED", "reason":reason}

    try:
        # AST selector preflight is not a binding proof. The pinned executor
        # must separately witness this exact occurrence in its own snapshot.
        try:
            trees = [t for t in parse_with_json_path_positions(sql, dialect) if t is not None]
        except SqlglotError:
            return reject("STATEMENT_UNSUPPORTED")
        if len(trees) != 1 or type(trees[0]) is not exp.Select:
            return reject("STATEMENT_UNSUPPORTED")
        matches = [n for n in trees[0].walk() if type(n) in (exp.JSONExtractScalar, exp.JSONExtract)
                   and n.meta.get("start") == start and n.meta.get("end") == end-1]
        if not matches:
            return reject("SITE_NOT_MATCHED")
        if len(matches) != 1:
            return reject("SITE_NOT_UNIQUE")
        call = matches[0]
        if (type(call.this) is not exp.Column or not call.this.table or call.this.is_star
                or isinstance(call.parent, exp.Dot) or type(call.expression) is not exp.JSONPath
                or not call.expression.meta.get("json_path_position")):
            return reject("SITE_UNSUPPORTED")
        common["site"] = dict(statement=1, call_position=sel.call_position.model_dump())
        from app.api.strict_read_witness import project

        reason, witness = project(execute(sql, dialect), sql, dialect, 1, start, end)
        if reason or not witness:
            return reject(reason or "OBSERVER_UNAVAILABLE")
        # The selector preflight and qualified executor must describe the
        # very same original literal and argument, not merely the same name.
        from app.services.subfield import path_tokens

        literal = call.expression.meta["json_path_position"]
        tokens = path_tokens(call.expression)
        hop = witness["hops"][0]
        def token_span(node):
            return {"start":node.meta["start"], "end":node.meta["end"] + 1}
        if (not tokens or witness["path_tokens"] != [{"kind":t, "value":v} for t,v in tokens]
                or witness["path_literal_span"] != {"start":literal["start"], "end":literal["end"]}
                or hop["column_span"] != token_span(call.this.this)
                or hop["qualifier_span"] != token_span(call.this.args["table"])):
            return reject("OBSERVER_UNAVAILABLE")
        return {**common, "status":"WITNESSED", "witness":witness}
    except Exception:
        # Never return internal errors, raw SQL, paths or a partial physical chain.
        return reject("OBSERVER_UNAVAILABLE")
