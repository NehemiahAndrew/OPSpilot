# backend/app/routers/policies.py
#
# Policies API routes.

from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.app.database import fetch_many, fetch_one, is_connected

router = APIRouter()


@router.get("")
async def list_policies(
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List policies, optionally filtered by category."""
    if not is_connected():
        return {"policies": [], "count": 0}
    if limit > 500:
        limit = 500

    if category:
        rows = await fetch_many(
            """SELECT p.id, p.policy_code, p.title, p.category, p.version,
                      p.effective_from, p.effective_until, p.is_active,
                      p.risk_level, p.rules, p.approval_requirements,
                      p.department_id, d.name AS department_name
               FROM company_policies p
               LEFT JOIN departments d ON d.id = p.department_id
               WHERE p.business_id = $1 AND p.category = $2
               ORDER BY p.version DESC
               LIMIT $3 OFFSET $4""",
            (_business_id(), category, limit, offset),
        )
    else:
        rows = await fetch_many(
            """SELECT p.id, p.policy_code, p.title, p.category, p.version,
                      p.effective_from, p.effective_until, p.is_active,
                      p.risk_level, p.rules, p.approval_requirements,
                      p.department_id, d.name AS department_name
               FROM company_policies p
               LEFT JOIN departments d ON d.id = p.department_id
               WHERE p.business_id = $1
               ORDER BY p.category, p.version DESC
               LIMIT $2 OFFSET $3""",
            (_business_id(), limit, offset),
        )

    return {"policies": rows, "count": len(rows)}


@router.get("/{policy_id}")
async def get_policy_detail(policy_id: str) -> dict:
    """Fetch a single policy by UUID or policy_code."""
    row = await fetch_one(
        """SELECT p.id, p.policy_code, p.title, p.category, p.version,
                  p.effective_from, p.effective_until, p.is_active,
                  p.risk_level, p.rules, p.approval_requirements,
                  p.department_id, d.name AS department_name,
                  p.created_at, p.updated_at
           FROM company_policies p
           LEFT JOIN departments d ON d.id = p.department_id
           WHERE p.business_id = $1 AND (p.id = $2 OR p.policy_code = $2)
           LIMIT 1""",
        (_business_id(), policy_id, policy_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return row


async def _business_id() -> str:
    """Return the demo business UUID (Acme Retail Group)."""
    row = await fetch_one("SELECT id FROM businesses ORDER BY created_at LIMIT 1")
    if row is None:
        raise HTTPException(status_code=503, detail="No business seeded")
    return row["id"]
