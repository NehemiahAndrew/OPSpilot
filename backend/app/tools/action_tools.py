# backend/app/tools/action_tools.py
#
# Action tools — write to the database.
# These tools require explicit authorization tier validation.
# They are NEVER called directly by LLM agents.
# They are called only by the Action Executor after authorization has been confirmed.

import json
import time
import uuid
from datetime import datetime, timezone

from backend.app.models.tool_contract import ToolResult, ToolContext
from backend.app.database import fetch_one, execute


async def _write_audit(ctx: ToolContext, action: str, target_type: str,
                 target_id: str, metadata: dict, run_id: str) -> None:
    """Insert a row into the append-only audit_logs table."""
    await execute(
        """INSERT INTO audit_logs
           (business_id, run_id, actor, action, target_type, target_id,
            risk_level, metadata)
           VALUES ($1, $2::uuid, $3, $4, $5, $6::uuid, 'low', $7::jsonb)""",
        (
            ctx.business_id,
            run_id,
            ctx.requesting_user_id,
            action,
            target_type,
            target_id,
            json.dumps(metadata),
        ),
    )


# ======================================================================
# Leave request creation (Tier 2 — reversible)
# ======================================================================
async def create_leave_request(
    employee_id: str,
    dates: list,
    reason: str,
    policy_id: str,
    run_id: str,
    ctx: ToolContext,
) -> ToolResult:
    """Create a leave request. Tier 2 — reversible.

    Must be idempotent: check for duplicate before creating.
    Records in audit_logs.
    """
    start = time.perf_counter()
    args = {
        "employee_id": employee_id,
        "dates": [str(d) for d in dates],
        "reason": reason,
        "policy_id": policy_id,
        "run_id": run_id,
        "business_id": ctx.business_id,
    }
    tool_name = "create_leave_request"

    # Idempotency check
    dates_key = json.dumps([str(d) for d in dates])
    existing = await fetch_one(
        """SELECT id FROM agent_requests
           WHERE business_id = $1 AND employee_id = $2
             AND request_type = 'leave'
             AND status IN ('pending', 'processing', 'awaiting_approval')
             AND structured_request->>'dates' = $3
           LIMIT 1""",
        (ctx.business_id, employee_id, dates_key),
    )
    dur = int((time.perf_counter() - start) * 1000)
    if existing is not None:
        return ToolResult.fail(
            tool_name=tool_name, error="DUPLICATE_REQUEST",
            arguments=args, duration_ms=dur,
            data={"existing_request_id": str(existing["id"])},
        )

    request_id = str(uuid.uuid4())
    structured = {
        "dates": [str(d) for d in dates],
        "reason": reason,
        "policy_id": policy_id,
    }
    await execute(
        """INSERT INTO agent_requests
           (id, business_id, employee_id, request_type, status,
            structured_request, submitted_by_user_id)
           VALUES ($1, $2, $3, 'leave', 'pending', $4, $5)""",
        (request_id, ctx.business_id, employee_id,
         json.dumps(structured), ctx.requesting_user_id),
    )

    await _write_audit(
        ctx, "leave_request_created", "request", request_id, args, run_id,
    )

    dur = int((time.perf_counter() - start) * 1000)
    return ToolResult.ok(
        tool_name=tool_name,
        data={"request_id": request_id, "status": "pending"},
        arguments=args, duration_ms=dur,
    )
# ======================================================================
# Approval request creation (always allowed — creates pending record)
# ======================================================================
async def create_approval_request(
    run_id: str,
    decision_id: str,
    approval_reason: str,
    authorization_tier: int,
    risk_level: str,
    ctx: ToolContext,
) -> ToolResult:
    """Create a pending approval record. Always allowed.

    This is how Tier 3 actions get queued.
    """
    start = time.perf_counter()
    args = {
        "run_id": run_id,
        "decision_id": decision_id,
        "approval_reason": approval_reason,
        "authorization_tier": authorization_tier,
        "risk_level": risk_level,
        "business_id": ctx.business_id,
    }
    tool_name = "create_approval_request"

    # Resolve the request attached to this run
    row = await fetch_one(
        """SELECT ar.id AS request_id
           FROM agent_requests ar
           JOIN agent_runs r ON r.request_id = ar.id
           WHERE r.id = $1::uuid
           LIMIT 1""",
        (run_id,),
    )
    request_id = row["request_id"] if row else None

    approval_id = str(uuid.uuid4())
    await execute(
        """INSERT INTO agent_approvals
           (id, request_id, run_id, decision_id, approval_reason,
            authorization_tier, risk_level, status, reviewed_by_user_id)
           VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', $8)""",
        (approval_id, request_id, run_id, decision_id, approval_reason,
         authorization_tier, risk_level, ctx.requesting_user_id),
    )

    await _write_audit(
        ctx, "approval_request_created", "approval", approval_id, args, run_id,
    )

    dur = int((time.perf_counter() - start) * 1000)
    return ToolResult.ok(
        tool_name=tool_name,
        data={"approval_id": approval_id, "status": "pending"},
        arguments=args, duration_ms=dur,
    )
# ======================================================================
# Request status update (validates legal transitions)
# ======================================================================
LEGAL_TRANSITIONS = {
    "pending": ["processing", "awaiting_approval", "rejected", "completed"],
    "processing": ["awaiting_approval", "approved", "rejected", "completed"],
    "awaiting_approval": ["approved", "rejected"],
    "approved": ["completed"],
    "rejected": [],
    "completed": [],
}


async def update_request_status(
    request_id: str,
    new_status: str,
    ctx: ToolContext,
) -> ToolResult:
    """Update request status. Validates legal status transitions."""
    start = time.perf_counter()
    args = {
        "request_id": request_id,
        "new_status": new_status,
        "business_id": ctx.business_id,
    }
    tool_name = "update_request_status"

    row = await fetch_one(
        "SELECT id, status FROM agent_requests WHERE id = $1 AND business_id = $2 LIMIT 1",
        (request_id, ctx.business_id),
    )

    dur = int((time.perf_counter() - start) * 1000)
    if row is None:
        return ToolResult.fail(
            tool_name=tool_name, error="REQUEST_NOT_FOUND",
            arguments=args, duration_ms=dur,
        )

    current = row["status"]
    allowed = LEGAL_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        return ToolResult.fail(
            tool_name=tool_name, error="ILLEGAL_TRANSITION",
            arguments=args, duration_ms=dur,
            data={"current_status": current, "allowed_transitions": allowed},
        )

    await execute(
        "UPDATE agent_requests SET status = $1 WHERE id = $2",
        (new_status, request_id),
    )

    dur = int((time.perf_counter() - start) * 1000)
    return ToolResult.ok(
        tool_name=tool_name,
        data={
            "request_id": request_id,
            "previous_status": current,
            "new_status": new_status,
        },
        arguments=args, duration_ms=dur,
    )
