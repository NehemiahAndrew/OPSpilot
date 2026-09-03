"""OpsPilot — READ TOOLS.

All read tools are pure queries against the PostgreSQL database. They
never mutate state. Every tool returns a ToolResult so the Context
Assembly Agent, Evidence Manifest, and Audit Writer get a uniform shape.

IMPORTANT: if multiple employees match a name, get_employee returns
success=False with error="AMBIGUOUS_EMPLOYEE" and a list of matches.
It NEVER silently picks one.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, Optional

from backend.app.database import fetch_many, fetch_one
from backend.app.models import ToolContext, ToolResult


# ======================================================================
# Internal helpers
# ======================================================================
def _employee_row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up an employee row for external consumption."""
    return {
        "employee_id": str(row["id"]),
        "emp_code": row.get("emp_code"),
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "name": row.get("name"),
        "email": row.get("email"),
        "role": row.get("role"),
        "job_title": row.get("role"),
        "department_id": str(row["department_id"]) if row.get("department_id") else None,
        "manager_id": str(row["manager_id"]) if row.get("manager_id") else None,
        "status": row.get("status"),
        "employment_type": row.get("employment_type"),
        "hire_date": str(row["hire_date"]) if row.get("hire_date") else None,
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
    }


# ======================================================================
# Employee lookup
# ======================================================================
async def get_employee(
    identifier: str,
    ctx: ToolContext,
) -> ToolResult:
    """Look up an employee by name or ID.

    If multiple employees match a name, returns success=False with
    error="AMBIGUOUS_EMPLOYEE" and data=list of matches.
    Never silently picks one.
    """
    start = time.perf_counter()
    args = {"identifier": identifier, "business_id": ctx.business_id}
    tool_name = "get_employee"

    row = await fetch_one(
        "SELECT * FROM employees WHERE business_id = $1 AND id = $2 LIMIT 1",
        (ctx.business_id, identifier),
    )
    if row is None:
        row = await fetch_one(
            "SELECT * FROM employees WHERE business_id = $1 AND emp_code = $2 LIMIT 1",
            (ctx.business_id, identifier),
        )
    if row is None and identifier:
        # Exact full-name match — but if more than one employee shares the
        # exact name we must surface ambiguity, never silently pick one.
        rows = await fetch_many(
            "SELECT * FROM employees WHERE business_id = $1 AND name = $2 ORDER BY name",
            (ctx.business_id, identifier),
        )
        if len(rows) > 1:
            dur = int((time.perf_counter() - start) * 1000)
            return ToolResult.fail(
                tool_name=tool_name, error="AMBIGUOUS_EMPLOYEE",
                arguments=args, duration_ms=dur,
                data=[_employee_row_to_dict(r) for r in rows],
            )
        if rows:
            row = rows[0]

    if row is None:
        pattern = f"%{identifier}%"
        rows = await fetch_many(
            """SELECT * FROM employees
               WHERE business_id = $1
                 AND (name ILIKE $2 OR first_name ILIKE $2 OR last_name ILIKE $2)
               ORDER BY name""",
            (ctx.business_id, pattern),
        )
        if len(rows) == 0:
            dur = int((time.perf_counter() - start) * 1000)
            return ToolResult.fail(
                tool_name=tool_name, error="EMPLOYEE_NOT_FOUND",
                arguments=args, duration_ms=dur,
            )
        if len(rows) > 1:
            dur = int((time.perf_counter() - start) * 1000)
            return ToolResult.fail(
                tool_name=tool_name, error="AMBIGUOUS_EMPLOYEE",
                arguments=args, duration_ms=dur,
                data=[_employee_row_to_dict(r) for r in rows],
            )
        row = rows[0]

    dur = int((time.perf_counter() - start) * 1000)
    return ToolResult.ok(
        tool_name=tool_name, data=_employee_row_to_dict(row),
        arguments=args, duration_ms=dur,
    )


async def get_employee_by_id(
    employee_id: str,
    ctx: ToolContext,
) -> ToolResult:
    """Look up an employee by their UUID or emp_code."""
    start = time.perf_counter()
    args = {"employee_id": employee_id, "business_id": ctx.business_id}
    tool_name = "get_employee_by_id"

    row = await fetch_one(
        """SELECT * FROM employees
           WHERE business_id = $1 AND (id = $2 OR emp_code = $2)
           LIMIT 1""",
        (ctx.business_id, employee_id),
    )

    dur = int((time.perf_counter() - start) * 1000)
    if row is None:
        return ToolResult.fail(
            tool_name=tool_name, error="EMPLOYEE_NOT_FOUND",
            arguments=args, duration_ms=dur,
        )
    return ToolResult.ok(
        tool_name=tool_name, data=_employee_row_to_dict(row),
        arguments=args, duration_ms=dur,
    )


# ======================================================================
# Leave balance
# ======================================================================
async def get_leave_balance(
    employee_id: str,
    as_of_date: date,
    ctx: ToolContext,
) -> ToolResult:
    """Get an employee's leave balance for a given year."""
    start = time.perf_counter()
    args = {
        "employee_id": employee_id,
        "as_of_date": str(as_of_date),
        "business_id": ctx.business_id,
    }
    tool_name = "get_leave_balance"

    query = """
        SELECT lb.*, e.name AS employee_name, e.emp_code
        FROM leave_balances lb
        JOIN employees e ON e.id = lb.employee_id
        WHERE e.business_id = $1
          AND (lb.employee_id = $2 OR e.emp_code = $2)
          AND lb.leave_type = 'annual'
          AND lb.year = $3
        LIMIT 1
    """
    row = await fetch_one(
        query, (ctx.business_id, employee_id, as_of_date.year),
    )

    dur = int((time.perf_counter() - start) * 1000)
    if row is None:
        return ToolResult.fail(
            tool_name=tool_name, error="LEAVE_BALANCE_NOT_FOUND",
            arguments=args, duration_ms=dur,
        )

    data = {
        "leave_balance_id": str(row["id"]),
        "employee_id": str(row["employee_id"]),
        "employee_name": row.get("employee_name"),
        "emp_code": row.get("emp_code"),
        "leave_type": row.get("leave_type"),
        "annual_entitlement": float(row["annual_entitlement"]) if row.get("annual_entitlement") else 0,
        "available_days": float(row["available_days"]) if row.get("available_days") else 0,
        "used_days": float(row["used_days"]) if row.get("used_days") else 0,
        "remaining_days": float(row["remaining_days"]) if row.get("remaining_days") else 0,
        "year": row.get("year"),
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }
    return ToolResult.ok(
        tool_name=tool_name, data=data, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Policy lookup
# ======================================================================
async def get_policy(
    category: str,
    ctx: ToolContext,
    department_id: Optional[str] = None,
) -> ToolResult:
    """Get policies by category.

    Department-specific policies are included alongside company-wide
    ones. Where they conflict, department-specific policies override
    company-wide ones.
    """
    start = time.perf_counter()
    args = {
        "category": category,
        "department_id": department_id,
        "business_id": ctx.business_id,
    }
    tool_name = "get_policy"

    query = """
        SELECT * FROM company_policies
        WHERE business_id = $1 AND category = $2 AND is_active = true
        ORDER BY
          CASE WHEN department_id IS NOT NULL THEN 0 ELSE 1 END,
          version DESC
    """
    rows = await fetch_many(query, (ctx.business_id, category))

    dur = int((time.perf_counter() - start) * 1000)
    if not rows:
        return ToolResult.fail(
            tool_name=tool_name, error="POLICY_NOT_FOUND",
            arguments=args, duration_ms=dur,
        )

    policies = []
    for row in rows:
        policies.append({
            "policy_id": str(row["id"]),
            "policy_code": row.get("policy_code"),
            "title": row.get("title"),
            "category": row.get("category"),
            "version": row.get("version"),
            "is_active": row.get("is_active"),
            "rules": row.get("rules"),
            "department_id": str(row["department_id"]) if row.get("department_id") else None,
            "risk_level": row.get("risk_level"),
            "effective_from": str(row["effective_from"]) if row.get("effective_from") else None,
            "effective_until": str(row["effective_until"]) if row.get("effective_until") else None,
            "approval_requirements": row.get("approval_requirements"),
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
        })

    return ToolResult.ok(
        tool_name=tool_name, data=policies, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Schedule lookup
# ======================================================================
async def get_schedule(
    employee_id: str,
    date_range_start: date,
    date_range_end: date,
    ctx: ToolContext,
) -> ToolResult:
    """Get an employee's schedule for a date range."""
    start = time.perf_counter()
    args = {
        "employee_id": employee_id,
        "date_range_start": str(date_range_start),
        "date_range_end": str(date_range_end),
        "business_id": ctx.business_id,
    }
    tool_name = "get_schedule"

    query = """
        SELECT s.*, e.emp_code, e.name AS employee_name
        FROM schedules s
        JOIN employees e ON e.id = s.employee_id
        WHERE e.business_id = $1
          AND (s.employee_id = $2 OR e.emp_code = $2)
          AND s.shift_date BETWEEN $3 AND $4
        ORDER BY s.shift_date
    """
    rows = await fetch_many(
        query,
        (ctx.business_id, employee_id, date_range_start, date_range_end),
    )

    dur = int((time.perf_counter() - start) * 1000)
    schedules = []
    for row in rows:
        schedules.append({
            "schedule_id": str(row["id"]),
            "employee_id": str(row["employee_id"]),
            "emp_code": row.get("emp_code"),
            "employee_name": row.get("employee_name"),
            "date": str(row["shift_date"]),
            "shift_start": str(row["shift_start"]) if row.get("shift_start") else None,
            "shift_end": str(row["shift_end"]) if row.get("shift_end") else None,
            "shift_type": row.get("shift_type"),
            "status": row.get("status"),
        })

    return ToolResult.ok(
        tool_name=tool_name, data=schedules, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Team coverage
# ======================================================================
async def get_team_coverage(
    department_id: str,
    target_date: date,
    ctx: ToolContext,
) -> ToolResult:
    """Calculate team coverage for a department on a given date.

    Returns employees_available, minimum_required, is_coverage_sufficient,
    and the list of available_employees.
    """
    start = time.perf_counter()
    args = {
        "department_id": department_id,
        "target_date": str(target_date),
        "business_id": ctx.business_id,
    }
    tool_name = "get_team_coverage"

    dept = await fetch_one(
        "SELECT * FROM departments WHERE id = $1 AND business_id = $2 LIMIT 1",
        (department_id, ctx.business_id),
    )

    dur = int((time.perf_counter() - start) * 1000)
    if dept is None:
        return ToolResult.fail(
            tool_name=tool_name, error="DEPARTMENT_NOT_FOUND",
            arguments=args, duration_ms=dur,
        )

    min_required = dept["minimum_coverage_headcount"]

    # All active employees in the department with their schedule for the date
    rows = await fetch_many(
        """SELECT e.id AS employee_id, e.name, e.emp_code,
                  s.status AS schedule_status
           FROM employees e
           LEFT JOIN schedules s
               ON s.employee_id = e.id AND s.shift_date = $1
           WHERE e.department_id = $2
             AND e.business_id = $3
             AND e.status = 'active'
           ORDER BY e.name""",
        (target_date, department_id, ctx.business_id),
    )

    available = []
    unavailable = []
    for row in rows:
        emp = {
            "employee_id": str(row["employee_id"]),
            "name": row["name"],
            "emp_code": row.get("emp_code"),
        }
        if row.get("schedule_status") == "WORKING":
            available.append(emp)
        else:
            emp["status"] = row.get("schedule_status") or "NO_SHIFT"
            unavailable.append(emp)

    employees_available = len(available)
    data = {
        "department_id": department_id,
        "department_name": dept.get("name"),
        "target_date": str(target_date),
        "employees_available": employees_available,
        "minimum_required": min_required,
        "is_coverage_sufficient": employees_available >= min_required,
        "available_employees": available,
        "unavailable_employees": unavailable,
    }
    return ToolResult.ok(
        tool_name=tool_name, data=data, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Pending requests (duplicate detection)
# ======================================================================
async def get_pending_requests(
    employee_id: str,
    ctx: ToolContext,
) -> ToolResult:
    """Get pending requests for an employee (for duplicate detection).

    Accepts a UUID employee id or an emp_code (EMP-001).
    """
    start = time.perf_counter()
    args = {"employee_id": employee_id, "business_id": ctx.business_id}
    tool_name = "get_pending_requests"

    query = """
        SELECT ar.id, ar.request_type, ar.status, ar.created_at,
               ar.structured_request
        FROM agent_requests ar
        LEFT JOIN employees e ON e.id = ar.employee_id
        WHERE ar.business_id = $1
          AND (ar.employee_id = $2 OR e.emp_code = $2)
          AND ar.status IN ('pending', 'processing', 'awaiting_approval')
        ORDER BY ar.created_at DESC
    """
    rows = await fetch_many(query, (ctx.business_id, employee_id))

    dur = int((time.perf_counter() - start) * 1000)
    requests = []
    for row in rows:
        requests.append({
            "request_id": str(row["id"]),
            "request_type": row.get("request_type"),
            "status": row.get("status"),
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
            "structured_request": row.get("structured_request"),
        })
    return ToolResult.ok(
        tool_name=tool_name, data=requests, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Task assignments
# ======================================================================
async def get_task_assignments(
    employee_id: str,
    ctx: ToolContext,
) -> ToolResult:
    """Get task assignments for an employee."""
    start = time.perf_counter()
    args = {"employee_id": employee_id, "business_id": ctx.business_id}
    tool_name = "get_task_assignments"

    query = """
        SELECT t.*, e.emp_code, e.name AS employee_name
        FROM tasks t
        JOIN employees e ON e.id = t.assigned_to
        WHERE t.business_id = $1
          AND (t.assigned_to = $2 OR e.emp_code = $2)
        ORDER BY t.due_date ASC
    """
    rows = await fetch_many(query, (ctx.business_id, employee_id))

    dur = int((time.perf_counter() - start) * 1000)
    tasks = []
    for row in rows:
        tasks.append({
            "task_id": str(row["id"]),
            "title": row.get("title"),
            "description": row.get("description"),
            "assigned_to": str(row["assigned_to"]) if row.get("assigned_to") else None,
            "employee_name": row.get("employee_name"),
            "priority": row.get("priority"),
            "status": row.get("status"),
            "due_date": str(row["due_date"]) if row.get("due_date") else None,
        })
    return ToolResult.ok(
        tool_name=tool_name, data=tasks, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Attendance records
# ======================================================================
async def get_attendance(
    employee_id: str,
    days_back: int,
    ctx: ToolContext,
) -> ToolResult:
    """Get attendance records for an employee over the past N days.

    Returns records plus late_count and warning_count.
    """
    start = time.perf_counter()
    args = {
        "employee_id": employee_id,
        "days_back": days_back,
        "business_id": ctx.business_id,
    }
    tool_name = "get_attendance"

    query = """
        SELECT a.*, e.emp_code, e.name AS employee_name
        FROM attendance_records a
        JOIN employees e ON e.id = a.employee_id
        WHERE e.business_id = $1
          AND (a.employee_id = $2 OR e.emp_code = $2)
          AND a.date >= CURRENT_DATE - INTERVAL '1 day' * $3
        ORDER BY a.date DESC
    """
    rows = await fetch_many(query, (ctx.business_id, employee_id, days_back))

    dur = int((time.perf_counter() - start) * 1000)
    records = []
    late_count = 0
    warning_count = 0
    for row in rows:
        status = row.get("status")
        if status == "late":
            late_count += 1
        if status == "formal_warning":
            warning_count += 1
        records.append({
            "attendance_id": str(row["id"]),
            "employee_id": str(row["employee_id"]),
            "emp_code": row.get("emp_code"),
            "employee_name": row.get("employee_name"),
            "date": str(row["date"]),
            "scheduled_start": str(row["scheduled_start"]) if row.get("scheduled_start") else None,
            "actual_start": str(row["actual_start"]) if row.get("actual_start") else None,
            "status": status,
            "notes": row.get("notes"),
        })

    data = {
        "records": records,
        "late_count": late_count,
        "warning_count": warning_count,
        "total_records": len(records),
    }
    return ToolResult.ok(
        tool_name=tool_name, data=data, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Historical decisions
# ======================================================================
async def get_historical_decisions(
    employee_id: str,
    request_type: str,
    ctx: ToolContext,
    limit: int = 5,
) -> ToolResult:
    """Get historical decisions for an employee.

    Results are labeled as HISTORICAL — never treat as current policy.
    """
    start = time.perf_counter()
    args = {
        "employee_id": employee_id,
        "request_type": request_type,
        "limit": limit,
        "business_id": ctx.business_id,
    }
    tool_name = "get_historical_decisions"

    query = """
        SELECT h.*, e.emp_code, e.name AS employee_name
        FROM historical_decisions h
        LEFT JOIN employees e ON e.id = h.employee_id
        WHERE h.business_id = $1
          AND (h.employee_id = $2 OR e.emp_code = $2)
          AND h.request_type = $3
        ORDER BY h.created_at DESC
        LIMIT $4
    """
    rows = await fetch_many(
        query,
        (ctx.business_id, employee_id, request_type, limit),
    )

    dur = int((time.perf_counter() - start) * 1000)
    decisions = []
    for row in rows:
        decisions.append({
            "decision_id": str(row["id"]),
            "employee_id": str(row["employee_id"]) if row.get("employee_id") else None,
            "emp_code": row.get("emp_code"),
            "employee_name": row.get("employee_name"),
            "request_type": row.get("request_type"),
            "decision": row.get("decision"),
            "reason": row.get("reason"),
            "decided_by": row.get("decided_by"),
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
        })

    data = {
        "decisions": decisions,
        "total_count": len(decisions),
        "label": "HISTORICAL",
        "warning": "These are previous operational decisions, NOT current policy.",
    }
    return ToolResult.ok(
        tool_name=tool_name, data=data, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Evidence lookup
# ======================================================================
async def get_evidence(
    evidence_id: str,
    ctx: ToolContext,
) -> ToolResult:
    """Get a piece of evidence by ID."""
    start = time.perf_counter()
    args = {"evidence_id": evidence_id, "business_id": ctx.business_id}
    tool_name = "get_evidence"

    row = await fetch_one(
        "SELECT * FROM agent_evidence WHERE id = $1 AND run_id IS NOT NULL LIMIT 1",
        (evidence_id,),
    )

    dur = int((time.perf_counter() - start) * 1000)
    if row is None:
        return ToolResult.fail(
            tool_name=tool_name, error="EVIDENCE_NOT_FOUND",
            arguments=args, duration_ms=dur,
        )

    data = {
        "evidence_id": str(row["id"]),
        "tool_call_id": str(row["tool_call_id"]) if row.get("tool_call_id") else None,
        "evidence_type": row.get("evidence_type"),
        "evidence_key": row.get("evidence_key"),
        "evidence_value": row.get("evidence_value"),
        "retrieved_at": str(row["retrieved_at"]) if row.get("retrieved_at") else None,
        "used_in_decision": row.get("used_in_decision"),
        "cited_in_reason": row.get("cited_in_reason"),
    }
    return ToolResult.ok(
        tool_name=tool_name, data=data, arguments=args, duration_ms=dur,
    )


# ======================================================================
# Evaluation case lookup
# ======================================================================
async def get_evaluation_case(
    case_id: str,
    ctx: ToolContext,
) -> ToolResult:
    """Get an evaluation case by ID (case_number)."""
    start = time.perf_counter()
    args = {"case_id": case_id, "business_id": ctx.business_id}
    tool_name = "get_evaluation_case"

    row = await fetch_one(
        "SELECT * FROM evaluation_cases WHERE case_number = $1 LIMIT 1",
        (case_id,),
    )

    dur = int((time.perf_counter() - start) * 1000)
    if row is None:
        return ToolResult.fail(
            tool_name=tool_name, error="EVALUATION_CASE_NOT_FOUND",
            arguments=args, duration_ms=dur,
        )

    data = {
        "case_id": str(row["id"]),
        "case_number": row.get("case_number"),
        "title": row.get("title"),
        "category": row.get("category"),
        "difficulty": row.get("difficulty"),
        "request": row.get("request"),
        "context": row.get("context"),
        "expected_decision_type": row.get("expected_decision_type"),
        "expected_action": row.get("expected_action"),
        "expected_authorization_tier": row.get("expected_authorization_tier"),
        "expected_approval_required": row.get("expected_approval_required"),
        "expected_evidence_keys": row.get("expected_evidence_keys"),
        "expected_policy_codes": row.get("expected_policy_codes"),
        "ground_truth_reason": row.get("ground_truth_reason"),
        "adversarial": row.get("adversarial"),
    }
    return ToolResult.ok(
        tool_name=tool_name, data=data, arguments=args, duration_ms=dur,
    )
