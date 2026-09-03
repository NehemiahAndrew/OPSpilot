"""OpsPilot — Audit Writer API routes.

GET /api/audit — append-only audit trail, newest first.

The audit_logs table is write-only at the application layer; this route only
reads. Every completed run/appended action produces audit rows via the
Action Executor and the Approval router.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.app.database import fetch_many, fetch_one, is_connected

router = APIRouter()


@router.get("")
async def list_audit(
    business_id: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Paginated audit trail, newest first."""
    if not is_connected():
        return {"audit": [], "count": 0, "total": 0}
    clauses = []
    params: list = []
    if business_id:
        clauses.append("business_id = $1")
        params.append(business_id)
    if run_id:
        clauses.append("run_id = $2::uuid")
        params.append(run_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    limit_idx = len(params) + 1
    offset_idx = len(params) + 2
    rows = await fetch_many(
        f"""SELECT id, business_id, run_id, actor, action, target_type,
                   target_id, risk_level, authorization_tier, approved_by,
                   result, metadata, timestamp
            FROM audit_logs
            {where}
            ORDER BY timestamp DESC
            LIMIT ${limit_idx} OFFSET ${offset_idx}""",
        (*params, limit, offset),
    )

    total_row = await fetch_one(
        f"SELECT COUNT(*) AS total FROM audit_logs {where}",
        tuple(params),
    )
    total = total_row["total"] if total_row else 0

    return {
        "audit": rows,
        "count": len(rows),
        "total": total,
    }