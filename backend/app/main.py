from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health_controller import router as health_router
from app.api.analyze_controller import router as analyze_router
from app.api.metadata_controller import router as metadata_router
from app.api.format_controller import router as format_router
from app.db.sqlite import run_migrations

app = FastAPI(title="SQL Lineage Workbench", version="0.3.0-c09")

run_migrations()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(metadata_router, prefix="/api")
app.include_router(format_router, prefix="/api")
