"""Read-only analysis of JSON paths for the subfield workbench."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.middleware.local_delivery import MAX_SQL_CHARS
from app.api.subfield_fact_cache import FactCacheRoute, fact_key, read_facts, propose_facts
from app.api.composition_controller import CompositionRequest, compose_lineage

router = APIRouter(route_class=FactCacheRoute)


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


class SubfieldRequest(BaseModel):
    mode: Literal["analyze"] = "analyze"
    sql: str = Field(min_length=1, max_length=MAX_SQL_CHARS)
    dialect: Literal["hive", "spark"] = "spark"
    source_schemas: dict[str, SourceSchema] | None = None
    include_two_step_evidence: bool = False
    protected_outputs: list[ProtectedOutput] | None = None
    candidate_keys: list[CandidateKeys] | None = Field(default=None, max_length=25)


@router.post("/sql/subfield-lineage")
def analyze_subfield_lineage(request: SubfieldRequest | CompositionRequest, http_request: Request = None) -> dict:
    if isinstance(request, CompositionRequest):
        return compose_lineage(request)

    from app.services.subfield import SourceSchemaConflict, analyze_subfields

    schemas = {relation: schema.model_dump()
               for relation, schema in (request.source_schemas or {}).items()}
    reviewing = request.protected_outputs is not None or request.candidate_keys is not None
    key = fact_key(http_request, request.sql, request.dialect, schemas, analyze_subfields)
    result = read_facts(key)
    retained = result.pop("_two_step_v1", None) if result is not None else None
    if result is None:
        try:
            result = analyze_subfields(request.sql, request.dialect, schemas)
        except SourceSchemaConflict as exc:
            raise HTTPException(status_code=422, detail={
                "code": "CONFLICTING_SOURCE_SCHEMAS", "relations": exc.relations,
            }) from exc
        if not reviewing:
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
    return result
