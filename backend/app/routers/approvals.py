"""OpsPilot — Human Approval API routes.

GET  /api/approvals              — paginated list of pending approvals
GET  /api/approvals/{id}         — approval detail incl. decision + evidence
POST /api/approvals/{id}/approve — approve (resumes the run into execution)
POST /api/approvals/{id}/reject  — reject (closes the run as rejected)

The approval record links to the full DecisionOutput, the
ConstitutionalCheckResult, the EvidenceManifest (stored in
decision_payload by the Action Executor) and the trajectory (run_id).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.database import execute, fetch_many, fetch_one, is_connected
from backend.app.models.tool_contract import ToolContext
from backend.app.orchestrator.workflow import AgentOrchestrator

# Share the in-memory run store with the runs/requests routers.
import backend.app.routers.runs as runs_mod

router = APIRouter()


class ApprovalReview(BaseModel):
    notes: str = ""


def _parse_payload(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError):
        return None


async def _get_approval(approval_id: str) -> Optional[Dict[str, Any]]:
    """Load an approval joined with its request + employee info."""
    return await fetch_one(
        """SELECT a.id, a.request_id, a.run_id, a.decision_id,
                  a.approval_reason, a.authorization_tier, a.risk_level,
                  a.status, a.reviewed_by_user_id, a.reviewed_at,
                  a.review_notes, a.created_at, a.decision_payload,
                  ar.employee_id, ar.request_type, ar.structured_request,
                  ar.business_id,
                  e.name AS employee_name
           FROM agent_approvals a
           LEFT JOIN agent_requests ar ON ar.id = a.request_id
           LEFT JOIN employees e ON e.id = ar.employee_id
           WHERE a.id = $1
           LIMIT 1""",
        (approval_id,),
    )


def _trajectory(run_id: str) -> list:
    """Trajectory (steps) for a run from the shared in-memory run store."""
    run_state = runs_mod._runs.get(run_id)
    if run_state is None:
        return []
    steps = []
    for step in getattr(run_state, "steps", []):
        steps.append(
            {
                "step_number": step.step_number,
                "agent": step.agent,
                "status": step.status,
                "started_at": step.started_at.isoformat()
                if step.started_at else None,
                "completed_at": step.completed_at.isoformat()
                if step.completed_at else None,
            }
        )
    return steps


def _enrich(approval: Dict[str, Any]) -> Dict[str, Any]:
    """Compose the human-readable approval record."""
    payload = _parse_payload(approval.get("decision_payload"))
    run_id = approval.get("run_id")
    out = {
        "id": approval["id"],
        "request_id": approval.get("request_id"),
        "run_id": run_id,
        "approval_reason": approval.get("approval_reason"),
        "authorization_tier": approval.get("authorization_tier"),
        "risk_level": approval.get("risk_level"),
        "status": approval.get("status"),
        "decision_id": approval.get("decision_id"),
        "employee_id": approval.get("employee_id"),
        "employee_name": approval.get("employee_name"),
        "request_type": approval.get("request_type"),
        "created_at": approval.get("created_at"),
        "reviewed_at": approval.get("reviewed_at"),
        "review_notes": approval.get("review_notes"),
        "decision": (payload or {}).get("decision"),
        "constitutional_check": (payload or {}).get("constitutional_check"),
        "evidence_manifest": (payload or {}).get("evidence_manifest"),
        "trajectory": _trajectory(run_id) if run_id else [],
    }
    return out


@router.get("")
async def list_approvals(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default="pending"),
) -> dict:
    """Paginated list of approval records, newest first."""
    if not is_connected():
        return {"approvals": [], "count": 0, "total": 0}
    clauses = []
    params: list = []
    if status:
        clauses.append("a.status = $1")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    rows = await fetch_many(
        f"""SELECT a.id, a.request_id, a.run_id, a.decision_id,
                   a.approval_reason, a.authorization_tier, a.risk_level,
                   a.status, a.created_at, a.decision_payload,
                   ar.employee_id, ar.request_type,
                   e.name AS employee_name
            FROM agent_approvals a
            LEFT JOIN agent_requests ar ON ar.id = a.request_id
            LEFT JOIN employees e ON e.id = ar.employee_id
            {where}
            ORDER BY a.created_at DESC
            LIMIT $2 OFFSET $3""",
        (*params, limit, offset),
    )

    total_row = await fetch_one(
        f"SELECT COUNT(*) AS total FROM agent_approvals a {where}",
        tuple(params),
    )
    total = total_row["total"] if total_row else 0

    return {
        "approvals": [_enrich(r) for r in rows],
        "count": len(rows),
        "total": total,
    }


@router.get("/{approval_id}")
async def get_approval(approval_id: str) -> dict:
    """Return a single approval with full decision + evidence context."""
    approval = await _get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return _enrich(approval)


async def _transition_approval(
    approval: Dict[str, Any],
    body: ApprovalReview,
    business_id: str,
    approval_decision: str,
    reviewer_id: str,
) -> Dict[str, Any]:
    """Mark an approval reviewed, resume the run, and write the audit row."""
    now = datetime.now(timezone.utc).isoformat()
    await execute(
        """UPDATE agent_approvals
           SET status = $1, reviewed_by_user_id = $2,
               reviewed_at = $3, review_notes = $4
           WHERE id = $5""",
        (approval_decision, reviewer_id, now, body.notes, approval["id"]),
    )

    run_id = approval.get("run_id")
    ctx = ToolContext(
        business_id=business_id,
        requesting_user_id=reviewer_id,
        user_role="admin",
        run_id=run_id or "",
        step_id="",
    )

    # Resume the run through the orchestrator so state + events are correct.
    orch = AgentOrchestrator()
    run_state = await orch.resume_after_approval(
        run_id=run_id,
        approval_decision=approval_decision,
        reviewer_notes=body.notes,
        ctx=ctx,
    )
    if run_id:
        runs_mod._runs[run_id] = run_state

    # Append to the audit trail (human decision, never auto-written).
    await execute(
        """INSERT INTO audit_logs
           (business_id, run_id, actor, action, target_type, target_id,
            risk_level, authorization_tier, approved_by, result, metadata)
           VALUES ($1, $2::uuid, $3, $4, $5, $6::uuid, $7, $8, $9, $10, $11::jsonb)""",
        (
            business_id,
            run_id,
            reviewer_id,
            f"approval.{approval_decision}",
            "approval",
            approval["id"],
            approval.get("risk_level") or "low",
            approval.get("authorization_tier") or 3,
            reviewer_id if approval_decision == "approved" else None,
            approval_decision,
            json.dumps({"approval_reason": approval.get("approval_reason"), "notes": body.notes}),
        ),
    )

    return {
        "approval_id": approval["id"],
        "status": approval_decision,
        "run_id": run_id,
        "run_status": run_state.status,
        "final_outcome": run_state.final_outcome,
    }


@router.post("/{approval_id}/approve")
async def approve_approval(approval_id: str, body: ApprovalReview) -> dict:
    """Approve a pending approval and resume the run into execution."""
    approval = await _get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval already reviewed (status: {approval['status']})",
        )
    business_id = approval.get("business_id")
    if not business_id:
        raise HTTPException(status_code=422, detail="Approval has no business context")
    return await _transition_approval(
        approval, body, business_id, "approved", "REVIEWER-001",
    )


@router.post("/{approval_id}/reject")
async def reject_approval(approval_id: str, body: ApprovalReview) -> dict:
    """Reject a pending approval and close the run as rejected."""
    approval = await _get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval already reviewed (status: {approval['status']})",
        )
    business_id = approval.get("business_id")
    if not business_id:
        raise HTTPException(status_code=422, detail="Approval has no business context")
    return await _transition_approval(
        approval, body, business_id, "rejected", "REVIEWER-001",
    )