import time

from fastapi import APIRouter

from app.models import ConvertSqlRequest, ConvertSqlResponse, Diagnostic, FormatSqlRequest, FormatSqlResponse

router = APIRouter()


def _normalize_dialect(dialect: str) -> str:
    value = dialect.strip().lower()
    aliases = {
        "sr": "starrocks",
    }
    normalized = aliases.get(value, value)
    if normalized in {"spark", "hive", "starrocks"}:
        return normalized
    return "spark"


@router.post("/sql/format", response_model=FormatSqlResponse)
async def format_sql(request: FormatSqlRequest) -> FormatSqlResponse:
    import sqlglot

    try:
        formatted = sqlglot.transpile(
            request.sql,
            read=_normalize_dialect(request.dialect),
            write=_normalize_dialect(request.dialect),
            pretty=True,
        )[0]
        return FormatSqlResponse(
            status="success",
            dialect=_normalize_dialect(request.dialect),
            formatted_sql=formatted,
            diagnostics=[],
        )
    except Exception as e:
        return FormatSqlResponse(
            status="failed",
            dialect=_normalize_dialect(request.dialect),
            formatted_sql=None,
            diagnostics=[
                Diagnostic(
                    code="SQL_FORMAT_ERROR",
                    level="error",
                    message=str(e),
                )
            ],
        )


@router.post("/sql/convert", response_model=ConvertSqlResponse)
async def convert_sql(request: ConvertSqlRequest) -> ConvertSqlResponse:
    import sqlglot

    started = time.perf_counter()
    source_dialect = _normalize_dialect(request.source_dialect)
    target_dialect = _normalize_dialect(request.target_dialect)

    try:
        converted = sqlglot.transpile(
            request.sql,
            read=source_dialect,
            write=target_dialect,
            pretty=request.pretty,
        )[0]
        return ConvertSqlResponse(
            status="success",
            source_dialect=source_dialect,
            target_dialect=target_dialect,
            converted_sql=converted,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            diagnostics=[],
        )
    except Exception as exc:
        return ConvertSqlResponse(
            status="failed",
            source_dialect=source_dialect,
            target_dialect=target_dialect,
            converted_sql=None,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            diagnostics=[
                Diagnostic(
                    code="SQL_CONVERT_ERROR",
                    level="error",
                    message=str(exc),
                )
            ],
        )
