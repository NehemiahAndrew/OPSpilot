# backend/app/routers/employees.py
#
# Employees API routes.

from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.app.database import fetch_many, fetch_one, is_connected

router = APIRouter()


@router.get("")
async def list_employees(
    department_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List employees, optionally filtered by department."""
    if not is_connected():
        return {"employees": [], "count": 0}
    if limit > 500:
        limit = 500

    if department_id:
        rows = await fetch_many(
            """SELECT e.id, e.emp_code, e.name, e.first_name, e.last_name,
                      e.email, e.role, e.department_id, d.name AS department_name,
                      e.status, e.employment_type, e.manager_id, e.hire_date
               FROM employees e
               LEFT JOIN departments d ON d.id = e.department_id
               WHERE e.department_id = $1 AND e.business_id = $2
               ORDER BY e.emp_code
               LIMIT $3 OFFSET $4""",
            (department_id, _business_id(), limit, offset),
        )
    else:
        rows = await fetch_many(
            """SELECT e.id, e.emp_code, e.name, e.first_name, e.last_name,
                      e.email, e.role, e.department_id, d.name AS department_name,
                      e.status, e.employment_type, e.manager_id, e.hire_date
               FROM employees e
               LEFT JOIN departments d ON d.id = e.department_id
               WHERE e.business_id = $1
               ORDER BY e.emp_code
               LIMIT $2 OFFSET $3""",
            (_business_id(), limit, offset),
        )

    return {"employees": rows, "count": len(rows)}


@router.get("/{employee_id}")
async def get_employee_detail(employee_id: str) -> dict:
    """Fetch a single employee by UUID or emp_code."""
    row = await fetch_one(
        """SELECT e.id, e.emp_code, e.name, e.first_name, e.last_name,
                  e.email, e.role, e.department_id, d.name AS department_name,
                  e.status, e.employment_type, e.manager_id, e.hire_date,
                  e.created_at, e.updated_at
           FROM employees e
           LEFT JOIN departments d ON d.id = e.department_id
           WHERE e.business_id = $1 AND (e.id = $2 OR e.emp_code = $2)
           LIMIT 1""",
        (_business_id(), employee_id, employee_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    manager = None
    if row.get("manager_id"):
        mgr = await fetch_one(
            "SELECT name, emp_code FROM employees WHERE id = $1 LIMIT 1",
            (row["manager_id"],),
        )
        if mgr:
            manager = {"name": mgr["name"], "emp_code": mgr["emp_code"]}

    result = dict(row)
    result["manager"] = manager
    return result


async def _business_id() -> str:
    """Return the demo business UUID.

    The seed pipeline creates exactly one business (Acme Retail Group).
    This helper keeps the routers simple until multi-tenant auth lands.
    """
    row = await fetch_one("SELECT id FROM businesses ORDER BY created_at LIMIT 1")
    if row is None:
        raise HTTPException(status_code=503, detail="No business seeded")
    return row["id"]
