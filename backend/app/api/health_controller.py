from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "service": "sql-lineage-workbench-backend",
        "version": "0.3.0-c06",
    }
