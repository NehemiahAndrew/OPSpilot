"""OpsPilot — Request API routes.

POST /api/requests — creates an agent_request and starts an orchestrator run.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.app.database import fetch_one, execute, is_connected
from backend.app.models.tool_contract import ToolContext
from backend.app.orchestrator.events import OrchestratorEvent, event_bus
from backend.app.orchestrator.workflow import AgentOrchestrator
from backend.app.routers.runs import _runs, set_run_store

router = APIRouter()

# Ensure the runs router shares our run store
set_run_store(_runs)


class CreateRequest(BaseModel):
    raw_input: str


async def _get_business_id() -> str:
    """Return the demo business UUID."""
    row = await fetch_one("SELECT id FROM businesses ORDER BY created_at LIMIT 1")
    if row is None:
        raise HTTPException(status_code=503, detail="No business seeded")
    return row["id"]


async def _run_orchestrator(
    request_id: str,
    raw_input: str,
    business_id: str,
) -> None:
    """Background task: run the orchestrator for a request."""
    ctx = ToolContext(
        business_id=business_id,
        requesting_user_id="USER-001",
        user_role="manager",
        run_id="",
        step_id="",
    )
    orchestrator = AgentOrchestrator()
    run_state = await orchestrator.run(request_id, raw_input, ctx)
    _runs[run_state.run_id] = run_state


@router.post("")
async def create_request(
    body: CreateRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Create an agent request and start the orchestrator in the background."""
    business_id = await _get_business_id()
    request_id = str(uuid.uuid4())

    # Create request record
    await execute(
        """INSERT INTO agent_requests
           (id, business_id, raw_input, request_type, status, created_at)
           VALUES ($1, $2, $3, 'pending', 'received', $4)""",
        (request_id, business_id, body.raw_input, datetime.now(timezone.utc).isoformat()),
    )

    # Generate a run_id now so we can return it
    run_id = str(uuid.uuid4())

    # Seed the event stream so the SSE endpoint can subscribe immediately
    # (before the background orchestrator run stores the full run state).
    await event_bus.publish(
        OrchestratorEvent(
            run_id=run_id,
            event_type="run.created",
            step_number=0,
            agent="orchestrator",
            status="ok",
            message="Run created",
            metadata={"request_id": request_id},
        )
    )

    # Start orchestrator in background
    background_tasks.add_task(
        _run_orchestrator_background,
        run_id,
        request_id,
        body.raw_input,
        business_id,
    )

    return {"request_id": request_id, "run_id": run_id}


async def _run_orchestrator_background(
    run_id: str,
    request_id: str,
    raw_input: str,
    business_id: str,
) -> None:
    """Background task wrapper that stores the run result."""
    ctx = ToolContext(
        business_id=business_id,
        requesting_user_id="USER-001",
        user_role="manager",
        run_id=run_id,
        step_id="",
    )

    # Persist the run record so the DB layer (executor joins, approvals)
    # can link tools and approval records back to this run.
    await execute(
        """INSERT INTO agent_runs
           (id, request_id, business_id, started_at, status)
           VALUES ($1, $2, $3, $4, 'running')""",
        (run_id, request_id, business_id, datetime.now(timezone.utc).isoformat()),
    )

    orchestrator = AgentOrchestrator()
    run_state = await orchestrator.run(request_id, raw_input, ctx, run_id=run_id)

    status = run_state.status.value if hasattr(run_state.status, "value") else run_state.status
    await execute(
        """UPDATE agent_runs
           SET status = $1, completed_at = $2, final_decision = $3,
               authorization_tier = $4
           WHERE id = $5""",
        (
            status,
            run_state.completed_at.isoformat() if run_state.completed_at else None,
            json.dumps(run_state.decision, default=str) if run_state.decision else None,
            run_state.authorization_tier,
            run_state.run_id,
        ),
    )

    _runs[run_state.run_id] = run_state
