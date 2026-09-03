# backend/app/main.py
#
# OpsPilot — FastAPI application entry point.
# CORS configured for frontend origin, lifespan manages the DB pool,
# all routers included.

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
import backend.app.database as db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database connection pool lifecycle."""
    logger.info("Starting up — initializing DB pool")
    await db.init_pool()
    if db.is_connected():
        logger.info("Database connected — full mode")
    else:
        logger.info("No database — running in DEMO mode")
    yield
    logger.info("Shutting down — closing DB pool")
    await db.close_pool()


app = FastAPI(
    title="OpsPilot",
    description="Workforce operations agent — supervised pipeline",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from backend.app.routers.employees import router as employees_router
from backend.app.routers.policies import router as policies_router
from backend.app.routers.requests import router as requests_router
from backend.app.routers.runs import router as runs_router
from backend.app.routers.approvals import router as approvals_router
from backend.app.routers.audit import router as audit_router
from backend.app.routers.evidence import router as evidence_router
from backend.app.routers.evaluation import router as evaluation_router

app.include_router(employees_router, prefix="/api/employees", tags=["employees"])
app.include_router(policies_router, prefix="/api/policies", tags=["policies"])
app.include_router(requests_router, prefix="/api/requests", tags=["requests"])
app.include_router(runs_router, prefix="/api/runs", tags=["runs"])
app.include_router(approvals_router, prefix="/api/approvals", tags=["approvals"])
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])
app.include_router(evidence_router, prefix="/api/runs", tags=["evidence"])
app.include_router(evaluation_router, prefix="/api/evaluation", tags=["evaluation"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
