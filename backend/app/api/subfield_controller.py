"""Read-only analysis of JSON paths for the subfield workbench."""

import logging
import os
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SkipValidation, model_validator

from app.api import single_cte_cold, strict_identity_cache, strict_read_trial
from app.middleware.local_delivery import MAX_SQL_CHARS, is_loopback_client
from app.api.strict_read_route import StrictReadRoute
from app.api.subfield_fact_cache import fact_key, read_facts, propose_facts
from app.api.composition_controller import CompositionRequest, compose_lineage

router = APIRouter(route_class=StrictReadRoute)


class SourceSchema(BaseModel):
    columns: list[str]
    complete: bool = False
    version: str = ""
    evidence: str = ""


class ProtectedOutput(BaseModel):
    statement: int = Field(ge=1)
    scope: str
    slot: int = Field(ge=1)


class CandidateKeys(BaseModel):
    source: str = Field(min_length=1)
    column: str = Field(min_length=1)
    keys: list[Annotated[str, Field(max_length=256)]] = Field(min_length=1, max_length=50)
    key_format: Literal["literal_key"] | None = Field(
        default=None, description="keys are exact top-level JSON member names; path expressions are unsupported.",
    )


class SubfieldRequest(BaseModel):
    mode: Literal["analyze"] = "analyze"
    sql: str = Field(min_length=1, max_length=MAX_SQL_CHARS)
    dialect: Literal["hive", "spark"] = "spark"
    source_schemas: dict[str, SourceSchema] | None = None
    include_two_step_evidence: bool = False
    # Ignore even a malformed optional selector while disabled. When enabled,
    # validate in the addon so legacy review never turns into a selector 422.
    strict_read_site: SkipValidation[strict_read_trial.StrictReadSite | None] = None
    protected_outputs: list[ProtectedOutput] | None = None
    candidate_keys: list[CandidateKeys] | None = Field(default=None, max_length=25)

    @model_validator(mode="before")
    @classmethod
    def validate_candidate_key_formats(cls, value):
        # Validate at request level, where the original array indices are known.
        candidates = value.get("candidate_keys") if isinstance(value, dict) else None
        if not isinstance(candidates, (list, tuple)):
            return value
        errors = []
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            fields = []
            if candidate.get("key_format") not in (None, "literal_key"):
                fields.append("key_format")
            fields.extend(field for field in ("path", "paths", "literal_key") if field in candidate)
            errors.extend({"loc": ["body", "candidate_keys", index, field]} for field in fields)
        if errors:
            # Only fixed field names and original indices are safe to return.
            raise HTTPException(status_code=422, detail={
                "code": "UNSUPPORTED_CANDIDATE_KEY_FORMAT",
                "message": "Supply top-level member names in keys with key_format='literal_key'; JSON paths are not supported.",
                "loc": errors[0]["loc"],
                "errors": errors,
            })
        return value


@router.post("/sql/subfield-lineage")
def analyze_subfield_lineage(request: SubfieldRequest | CompositionRequest, http_request: Request = None) -> dict:
    if isinstance(request, CompositionRequest):
        return compose_lineage(request)

    from app.services.subfield import SourceSchemaConflict, analyze_subfields

    schemas = {relation: schema.model_dump()
               for relation, schema in (request.source_schemas or {}).items()}
    reviewing = request.protected_outputs is not None or request.candidate_keys is not None
    has_selector = "strict_read_site" in request.model_fields_set
    strict = has_selector and strict_read_trial.enabled()
    mixed = strict and strict_read_trial.is_mixed(request)
    lookup_only = strict and not mixed
    # Development-only ordinary analyze. Explicit selector/two-step requests
    # keep the original controller, cache and optional proof lease.
    dev = (os.environ.get("SUBFIELD_STRICT_USE_DEV") == "1" and not has_selector
           and not request.include_two_step_evidence and http_request is not None
           and is_loopback_client(http_request.client.host if http_request.client else None))
    cache_bypass = lookup_only or dev
    key = None if cache_bypass else fact_key(http_request, request.sql, request.dialect, schemas, analyze_subfields)
    result = None if cache_bypass else read_facts(key)
    pack = hit = descriptor = generation = None
    if dev:
        descriptor, generation, hit = strict_identity_cache.lookup(http_request, request, schemas)
        if hit is not None:
            result = dict(hit.facts)
    retained = result.pop("_two_step_v1", None) if result is not None else None
    if result is None:
        try:
            bare, header = single_cte_cold.modes(request, http_request)
            if bare or header:
                from experiments.single_cte_name_cold import capture

                result, pack, extra, header_extra = capture(
                    request.sql, schemas, with_v2=dev, bare=bare, header=header)
                if extra:
                    http_request.state.single_cte_cold_bytes = extra
                if header_extra:
                    http_request.state.single_cte_header_bytes = header_extra
            elif dev:
                from experiments.strict_use_dev import capture_compact_identities

                result, pack = capture_compact_identities(request.sql, request.dialect, schemas)
            else:
                result = analyze_subfields(request.sql, request.dialect, schemas)
        except SourceSchemaConflict as exc:
            raise HTTPException(status_code=422, detail={
                "code": "CONFLICTING_SOURCE_SCHEMAS", "relations": exc.relations,
            }) from exc
        if not reviewing and not cache_bypass:
            propose_facts(http_request, key, result)
    if reviewing:
        from app.services.subfield_review import build_review

        ports = [output.model_dump() for output in request.protected_outputs or []]
        if request.candidate_keys is None:
            result["review"] = build_review(result, ports)
        else:
            result["review"] = build_review(
                result, ports,
                candidate_keys=[item.model_dump() for item in request.candidate_keys],
            )
        from app.services.subfield_branch_review import build_branch_review, is_coalesce_port_model

        if ports and any(is_coalesce_port_model(mapping) for mapping in result["mappings"]):

            branch_review = build_branch_review(result, ports)
            if branch_review.get("by_protected_output"):
                result["review"]["observed_branch_demands"] = branch_review
        if (request.include_two_step_evidence and len(ports) == 1 and request.source_schemas is None
                and "dialect" in request.model_fields_set):
            try:
                from app.services.subfield_static_evidence import static_extraction_evidence

                def publish(blocks):
                    facts = {k: v for k, v in result.items() if k != "review"}
                    propose_facts(http_request, key, {**facts, "_two_step_v1": blocks})

                evidence = static_extraction_evidence(request.sql, request.dialect, ports[0], result,
                                                      retained=retained, publish=publish if key is not None else None)
                if evidence is not None:
                    result["review"]["static_extraction_evidence"] = evidence
            except Exception:
                logging.getLogger(__name__).debug("Optional two-step evidence unavailable", exc_info=True)
    if strict and http_request is not None:
        # Do not hold up ordinary serialization or cache processing. The APIRoute
        # appends the optional block only after it has the original HTTP Response.
        http_request.state.strict_read_pending = (request, mixed)
    if dev and (pack is not None or hit is not None):
        raw = {k: v for k, v in result.items() if k != "review"}
        http_request.state.strict_identity_pending = (raw, pack, hit, descriptor, generation, result)
    return result
