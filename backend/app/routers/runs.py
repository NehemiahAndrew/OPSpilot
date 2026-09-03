"""OpsPilot — Run API routes.

GET /api/runs                  — paginated list of runs
GET /api/runs/{run_id}         — current AgentRunState
GET /api/runs/{run_id}/stream      — SSE event stream
GET /api/runs/{run_id}/trajectory  — full audit-ready trajectory export
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.app.database import fetch_many, fetch_one, is_connected
from backend.app.orchestrator.events import event_bus

router = APIRouter()

# In-memory run store (imported from requests module at runtime)
_runs: dict = {}


def set_run_store(store: dict) -> None:
    """Set the shared run store reference."""
    global _runs
    _runs = store


async def _run_from_db(run_id: str) -> Optional[Dict[str, Any]]:
    """Best-effort load of a run row from the database (in-memory store miss)."""
    try:
        return await fetch_one(
            """SELECT id, request_id, business_id, status, started_at,
                      completed_at, final_decision, authorization_tier
               FROM agent_runs WHERE id = $1 LIMIT 1""",
            (run_id,),
        )
    except Exception:
        return None


@router.get("")
async def list_runs(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return a paginated list of runs."""
    all_runs = list(_runs.values())
    page = all_runs[offset : offset + limit]
    return {
        "runs": [r.model_dump() for r in page],
        "count": len(page),
        "total": len(all_runs),
    }


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict:
    """Return the current state of a run."""
    run = _runs.get(run_id)
    if run is None:
        row = await _run_from_db(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "run_id": row["id"],
            "request_id": row["request_id"],
            "business_id": row["business_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "final_decision": row["final_decision"],
            "authorization_tier": row["authorization_tier"],
        }
    return run.model_dump()


@router.get("/{run_id}/stream")
async def stream_events(
    run_id: str,
    last_event_id: Optional[str] = Query(default=None),
):
    """SSE endpoint for real-time run events.

    Uses Server-Sent Events protocol. Sends keep-alive every 15 seconds.
    Handles client disconnect cleanly. Replays last N events on reconnect
    via the Last-Event-ID / `last_event_id` query parameter.

    A run is valid if it is in the in-memory store OR the event bus has
    history for it (the run may still be in progress and not yet stored).
    """
    if run_id not in _runs and not event_bus.get_history(run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    queue = event_bus.subscribe(run_id, last_event_id=last_event_id)

    TERMINAL_EVENTS = {"run.completed", "run.failed", "run.blocked"}

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {event.to_sse()}\n\n"
                    if event.event_type in TERMINAL_EVENTS:
                        # The run is over — end the stream so the client
                        # can switch to its completed state.
                        return
                except asyncio.TimeoutError:
                    # Send keep-alive comment
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{run_id}/trajectory")
async def get_trajectory(run_id: str) -> dict:
    """Export the complete, audit-ready trajectory of a run."""
    run = _runs.get(run_id)
    if run is None:
        row = await _run_from_db(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "run_id": run_id,
            "request_id": row["request_id"] or "",
            "status": row["status"],
            "structured_request": None,
            "steps": [],
            "tool_calls": [],
            "evidence_manifest": None,
            "decision": None,
            "constitutional_result": None,
            "authorization_result": None,
            "approval": None,
            "audit_record": None,
        }

    decision = run.decision
    if isinstance(decision, dict):
        decision = json.loads(json.dumps(decision, default=str))

    approval = None
    audit_record = None
    approval_row = await fetch_one(
        """SELECT id, request_id, decision_id, approval_reason,
                  authorization_tier, risk_level, status,
                  reviewed_by_user_id, reviewed_at, review_notes,
                  created_at, decision_payload
           FROM agent_approvals WHERE run_id = $1
           ORDER BY created_at DESC LIMIT 1""",
        (run_id,),
    )
    if approval_row:
        raw_payload = approval_row["decision_payload"]
        parsed_payload = None
        if isinstance(raw_payload, str):
            try:
                parsed_payload = json.loads(raw_payload)
            except (TypeError, ValueError):
                parsed_payload = None
        elif isinstance(raw_payload, dict):
            parsed_payload = raw_payload
        approval = {
            "id": approval_row["id"],
            "request_id": approval_row["request_id"],
            "decision_id": approval_row["decision_id"],
            "approval_reason": approval_row["approval_reason"],
            "authorization_tier": approval_row["authorization_tier"],
            "risk_level": approval_row["risk_level"],
            "status": approval_row["status"],
            "reviewed_by_user_id": approval_row["reviewed_by_user_id"],
            "reviewed_at": approval_row["reviewed_at"],
            "review_notes": approval_row["review_notes"],
            "created_at": approval_row["created_at"],
            "decision_payload": parsed_payload,
        }
        audit_row = await fetch_one(
            """SELECT id, business_id, run_id, actor, action, target_type,
                      target_id, risk_level, authorization_tier, approved_by,
                      result, metadata, timestamp
               FROM audit_logs WHERE run_id = $1
               ORDER BY timestamp DESC LIMIT 1""",
            (run_id,),
        )
        if audit_row:
            audit_record = {
                "id": audit_row["id"],
                "business_id": audit_row["business_id"],
                "run_id": audit_row["run_id"],
                "actor": audit_row["actor"],
                "action": audit_row["action"],
                "target_type": audit_row["target_type"],
                "target_id": audit_row["target_id"],
                "risk_level": audit_row["risk_level"],
                "authorization_tier": audit_row["authorization_tier"],
                "approved_by": audit_row["approved_by"],
                "result": audit_row["result"],
                "metadata": audit_row["metadata"],
                "timestamp": audit_row["timestamp"],
            }

    return {
        "run_id": run.run_id,
        "request_id": run.request_id,
        "status": (
            run.status.value if hasattr(run.status, "value") else run.status
        ),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "structured_request": (
            run.structured_request.model_dump(mode="json")
            if run.structured_request else None
        ),
        "steps": [
            {
                "step_number": s.step_number,
                "step_id": s.step_id,
                "agent": s.agent,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in run.steps
        ],
        "tool_calls": [
            {
                "tool_call_id": tc.tool_call_id,
                "run_id": tc.run_id,
                "step_id": tc.step_id,
                "tool_name": tc.tool_name,
                "arguments": tc.arguments,
                "result": tc.result,
                "success": tc.success,
                "error_message": tc.error_message,
                "duration_ms": tc.duration_ms,
                "called_at": tc.called_at.isoformat(),
            }
            for tc in run.tool_calls
        ],
        "evidence_manifest": run.evidence_manifest,
        "decision": decision,
        "constitutional_result": run.constitutional_result,
        "authorization_result": {
            "tier": run.authorization_tier,
            "approved": bool(
                run.authorization_tier is not None and run.authorization_tier < 3
            ),
            "requires_approval": bool(
                run.authorization_tier is not None and run.authorization_tier >= 3
            ),
            "decision_type": (decision or {}).get("decision_type"),
        },
        "approval": approval,
        "audit_record": audit_record,
    }
