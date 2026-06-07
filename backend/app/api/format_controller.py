from fastapi import APIRouter

from app.models import FormatSqlRequest, FormatSqlResponse, Diagnostic

router = APIRouter()


@router.post("/sql/format", response_model=FormatSqlResponse)
async def format_sql(request: FormatSqlRequest) -> FormatSqlResponse:
    import sqlglot

    try:
        formatted = sqlglot.transpile(
            request.sql,
            read=request.dialect,
            write=request.dialect,
            pretty=True,
        )[0]
        return FormatSqlResponse(
            status="success",
            dialect=request.dialect,
            formatted_sql=formatted,
            diagnostics=[],
        )
    except Exception as e:
        return FormatSqlResponse(
            status="failed",
            dialect=request.dialect,
            formatted_sql=None,
            diagnostics=[
                Diagnostic(
                    code="SQL_FORMAT_ERROR",
                    level="error",
                    message=str(e),
                )
            ],
        )
