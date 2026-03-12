from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from autoflow.api.database import init_db
from autoflow.api.routes import execution, logs, workflows, ai
from autoflow.config import DASHBOARD_DIR
from autoflow.engine.registry import registry

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("AutoFlow starting up")
    init_db()
    registry.discover()

    # Sync YAML workflows to DB cache on startup
    from autoflow.api.routes.workflows import get_service
    service = get_service()
    count = service.sync_all_to_db()
    log.info("Synced %d YAML workflows to DB cache", count)

    log.info("AutoFlow ready")
    yield
    log.info("AutoFlow shutting down")


app = FastAPI(title="AutoFlow", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflows.router)
app.include_router(execution.router)
app.include_router(logs.router)
app.include_router(ai.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}


if DASHBOARD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
