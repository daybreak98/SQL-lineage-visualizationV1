"""Bounded, read-only adapter for caller-scoped V2 composition.

POST /api/sql/subfield-lineage with mode=compose uses the existing SQL guard.
Snapshots contain unchanged SQL and explicit dialect; ports carry its UTF-8
SHA-256. Links require caller evidence and an explicit partition (null means
unknown). Their binding_status is a caller assertion, never API verification.
Returned local_snapshots, caller_contracts and unresolved_boundaries distinguish
local observations from external premises. All results remain REVIEW_ONLY.
Limits: 8 snapshots, 128 links/roots, 64 KiB combined SQL, 2 MiB raw HTTP body (enforced before decoding).
"""
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.middleware.local_delivery import MAX_REQUEST_BODY_BYTES, MAX_SQL_CHARS


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotInput(ContractModel):
    snapshot_id: str = Field(min_length=1, max_length=128)
    sql: str = Field(min_length=1, max_length=MAX_SQL_CHARS)
    dialect: Literal["hive", "spark"]
    source_context: dict | None = None


class SnapshotIdentity(ContractModel):
    snapshot: str = Field(min_length=1, max_length=128)
    sql_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    statement: int = Field(ge=1)
    scope: str = Field(pattern=r"^[1-9][0-9]*:[1-9][0-9]*$", max_length=64)

    @model_validator(mode="after")
    def consistent_scope(self):
        if int(self.scope.split(":")[0]) != self.statement:
            raise ValueError("Scope must belong to the stated statement")
        return self


class CompositionPort(SnapshotIdentity):
    slot: int = Field(ge=1)


class ConsumerSource(SnapshotIdentity):
    relation: str = Field(min_length=1, max_length=512)
    column: str | None = Field(max_length=256)
    binding: Literal["SQL_NAMED_RELATION_COLUMN", "SQL_RELATION_ROWS"]


class CallerLink(ContractModel):
    consumer_source: ConsumerSource
    producer_port: CompositionPort
    binding_status: Literal["EXPLICIT_VIRTUAL_SLOT", "VERIFIED_SCHEMA_SLOT"]
    evidence: dict = Field(min_length=1)
    partition: dict | None


class PathKey(ContractModel):
    kind: Literal["key"]
    value: str = Field(strict=True)


class PathIndex(ContractModel):
    kind: Literal["index"]
    value: int = Field(strict=True, ge=0)


PathToken = Annotated[PathKey | PathIndex, Field(discriminator="kind")]


class Demand(ContractModel):
    kind: Literal["WHOLE_VALUE", "VALUE_PATH", "UNKNOWN"] = "WHOLE_VALUE"
    path_tokens: list[PathToken] | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def explicit_path(self):
        if self.kind == "VALUE_PATH" and not self.path_tokens:
            raise ValueError("VALUE_PATH requires explicit path tokens")
        return self


class CompositionOutput(ContractModel):
    port: CompositionPort
    demand: Demand = Field(default_factory=Demand)


class CompositionRequest(ContractModel):
    mode: Literal["compose"]
    snapshots: list[SnapshotInput] = Field(min_length=1, max_length=8)
    links: list[CallerLink] = Field(max_length=128)
    protected_outputs: list[CompositionOutput] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def identity_and_budget(self):
        ids = [item.snapshot_id for item in self.snapshots]
        if len(ids) != len(set(ids)):
            raise ValueError("Snapshot identities must be unique")
        if sum(len(item.sql) for item in self.snapshots) > MAX_SQL_CHARS:
            raise ValueError("Combined SQL exceeds the single-request SQL budget")
        if len(self.model_dump_json().encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
            raise ValueError("Composition request exceeds body budget")
        return self


def compose_lineage(request: CompositionRequest) -> dict:
    from app.services.subfield_composition import build_snapshot, compose_demands

    snapshots = [build_snapshot(item.sql, item.snapshot_id, item.dialect, item.source_context)
                 for item in request.snapshots]
    links = [link.model_dump() for link in request.links]
    sources = [edge["source"] for snapshot in snapshots
               for edge in snapshot["relations"] + snapshot["row_relations"] if "source" in edge]
    if any(link["consumer_source"] not in sources for link in links):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_COMPOSITION_CONTRACT", "message": "Consumer source does not exist in these snapshots"})
    try:
        result = compose_demands(snapshots, links, [
            output.model_dump(exclude_none=True) for output in request.protected_outputs])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_COMPOSITION_CONTRACT", "message": str(exc)}) from exc
    result["local_snapshots"] = snapshots
    result["caller_contracts"] = links
    result["unresolved_boundaries"] = list(result["unknowns"])
    for demand in result["source_demands"]:
        boundary = {"code": "SOURCE_OUTSIDE_EXPLICIT_LINKS", "source": demand["source"]}
        if (not any(link["consumer_source"] == demand["source"] for link in links)
                and boundary not in result["unresolved_boundaries"]):
            result["unresolved_boundaries"].append(boundary)
    result["coverage_boundary"]["caller_bindings_verified"] = False
    return result
