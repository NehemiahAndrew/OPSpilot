"""Tool-layer tests for OpsPilot.

Every read/action tool is exercised against the deterministic synthetic
workforce world (Acme Retail Group) through the SQLite-backed fake DB that
the conftest seeds from backend/data/generator.py — the exact data the real
PostgreSQL seed produces.

Run:  cd backend && PYTHONPATH=.. pytest tests/test_tools.py -v
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.data import generator as g
from backend.app.tools import read_tools, action_tools


def _dept(dept_code: str) -> str:
    return g.DEPT_ID_BY_CODE[dept_code]


# ======================================================================
# get_employee / get_employee_by_id
# ======================================================================
class TestGetEmployee:
    @pytest.mark.asyncio
    async def test_valid_name(self, patch_db, ctx):
        r = await read_tools.get_employee("Sarah Mitchell", ctx)
        assert r.success is True
        assert r.source == "database"
        assert r.data["emp_code"] == "EMP-001"
        assert r.data["first_name"] == "Sarah"
        assert r.data["last_name"] == "Mitchell"

    @pytest.mark.asyncio
    async def test_valid_emp_code(self, patch_db, ctx):
        r = await read_tools.get_employee("EMP-005", ctx)
        assert r.success is True
        assert r.data["name"] == "Daniel Okafor"

    @pytest.mark.asyncio
    async def test_ambiguous_name(self, patch_db, ctx):
        r = await read_tools.get_employee("John", ctx)
        assert r.success is False
        assert r.error == "AMBIGUOUS_EMPLOYEE"
        assert r.data is not None and len(r.data) >= 2
        codes = {m["emp_code"] for m in r.data}
        assert "EMP-002" in codes and "EMP-013" in codes

    @pytest.mark.asyncio
    async def test_unknown_name(self, patch_db, ctx):
        r = await read_tools.get_employee("Michael", ctx)
        assert r.success is False
        assert r.error == "EMPLOYEE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_by_id(self, patch_db, ctx):
        r = await read_tools.get_employee_by_id("EMP-001", ctx)
        assert r.success is True
        assert r.data["emp_code"] == "EMP-001"

    @pytest.mark.asyncio
    async def test_by_id_unknown(self, patch_db, ctx):
        r = await read_tools.get_employee_by_id("EMP-999", ctx)
        assert r.success is False
        assert r.error == "EMPLOYEE_NOT_FOUND"


# ======================================================================
# get_leave_balance
# ======================================================================
class TestLeaveBalance:
    @pytest.mark.asyncio
    async def test_valid(self, patch_db, ctx):
        r = await read_tools.get_leave_balance("EMP-001", date(2026, 9, 1), ctx)
        assert r.success is True
        # Sarah Mitchell: annual 20 / used 12 / remaining 8 (EVL-001)
        assert r.data["annual_entitlement"] == 20
        assert r.data["used_days"] == 12
        assert r.data["remaining_days"] == 8

    @pytest.mark.asyncio
    async def test_zero_balance(self, patch_db, ctx):
        r = await read_tools.get_leave_balance("EMP-014", date(2026, 9, 1), ctx)
        assert r.success is True
        assert r.data["remaining_days"] == 0

    @pytest.mark.asyncio
    async def test_wrong_employee(self, patch_db, ctx):
        r = await read_tools.get_leave_balance("EMP-999", date(2026, 9, 1), ctx)
        assert r.success is False
        assert r.error == "LEAVE_BALANCE_NOT_FOUND"


# ======================================================================
# get_policy
# ======================================================================
class TestPolicy:
    @pytest.mark.asyncio
    async def test_valid_category(self, patch_db, ctx):
        r = await read_tools.get_policy("annual_leave_policy", ctx)
        assert r.success is True
        codes = {p["policy_code"] for p in r.data}
        assert "POL-001" in codes

    @pytest.mark.asyncio
    async def test_nonexistent_category(self, patch_db, ctx):
        r = await read_tools.get_policy("nonexistent_policy", ctx)
        assert r.success is False
        assert r.error == "POLICY_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_department_override_wins(self, patch_db, ctx):
        # Add a department-specific leave policy for Operations; it must be
        # returned ahead of the company-wide policy for that category.
        dept_policy_id = "d9999999-0000-0000-0000-000000000099"
        await patch_db.execute(
            """INSERT INTO company_policies
               (id, business_id, category, title, content, rules, version,
                is_active, department_id, policy_code, risk_level,
                effective_from, effective_until, approval_requirements)
               VALUES (?, ?, 'annual_leave_policy', 'Ops Leave (stricter)',
                       'Tighter notice window for Operations.',
                       ?, 1, TRUE, ?, 'POL-901', 'medium',
                       '2026-01-01', NULL, ?)""",
            (
                dept_policy_id, g.BUSINESS_ID,
                json.dumps({"description": "Ops-specific leave rule"}),
                _dept("DEP-001"),
                json.dumps({"approval_required": True}),
            ),
        )
        r = await read_tools.get_policy(
            "annual_leave_policy", ctx, department_id=_dept("DEP-001"),
        )
        assert r.success is True
        assert r.data[0]["policy_code"] == "POL-901"
        assert r.data[0]["department_id"] == _dept("DEP-001")


# ======================================================================
# get_schedule
# ======================================================================
class TestSchedule:
    @pytest.mark.asyncio
    async def test_valid_range(self, patch_db, ctx):
        r = await read_tools.get_schedule(
            "EMP-001", date(2026, 9, 1), date(2026, 9, 7), ctx,
        )
        assert r.success is True
        # Operations is a 7-day retail department -> 7 shifts that week.
        assert len(r.data) == 7
        for d in r.data:
            assert d["status"] in ("WORKING", "OFF", "LEAVE", "SICK", "HOLIDAY")

    @pytest.mark.asyncio
    async def test_friday_working(self, patch_db, ctx):
        # Sarah is scheduled to WORK on the demo Friday 2026-09-04.
        r = await read_tools.get_schedule(
            "EMP-001", g.FRIDAY_NORMAL, g.FRIDAY_NORMAL, ctx,
        )
        assert r.success is True
        assert len(r.data) == 1
        assert r.data[0]["status"] == "WORKING"

    @pytest.mark.asyncio
    async def test_no_shifts(self, patch_db, ctx):
        r = await read_tools.get_schedule(
            "EMP-001", date(2030, 1, 1), date(2030, 1, 5), ctx,
        )
        assert r.success is True
        assert r.data == []


# ======================================================================
# get_team_coverage
# ======================================================================
class TestCoverage:
    @pytest.mark.asyncio
    async def test_sufficient(self, patch_db, ctx):
        # Operations 2026-09-04: Sarah + 3 colleagues scheduled -> 4 >= 3.
        r = await read_tools.get_team_coverage(_dept("DEP-001"), g.FRIDAY_NORMAL, ctx)
        assert r.success is True
        assert r.data["employees_available"] == 4
        assert r.data["minimum_required"] == 3
        assert r.data["is_coverage_sufficient"] is True
        codes = {e["emp_code"] for e in r.data["available_employees"]}
        assert "EMP-001" in codes

    @pytest.mark.asyncio
    async def test_insufficient(self, patch_db, ctx):
        # Engineering 2026-09-10: David sick, no replacement -> 0 < 2.
        r = await read_tools.get_team_coverage(_dept("DEP-004"), g.ENG_NO_REPLACE, ctx)
        assert r.success is True
        assert r.data["employees_available"] == 0
        assert r.data["minimum_required"] == 2
        assert r.data["is_coverage_sufficient"] is False

    @pytest.mark.asyncio
    async def test_zero_available(self, patch_db, ctx):
        # Engineering is an office dept: Saturday 2026-09-12 -> nobody works.
        r = await read_tools.get_team_coverage(_dept("DEP-004"), date(2026, 9, 12), ctx)
        assert r.success is True
        assert r.data["employees_available"] == 0
        assert r.data["is_coverage_sufficient"] is False

    @pytest.mark.asyncio
    async def test_unknown_department(self, patch_db, ctx):
        r = await read_tools.get_team_coverage("no-such-dept", g.FRIDAY_NORMAL, ctx)
        assert r.success is False
        assert r.error == "DEPARTMENT_NOT_FOUND"


# ======================================================================
# get_pending_requests
# ======================================================================
class TestPendingRequests:
    @pytest.mark.asyncio
    async def test_has_pending(self, patch_db, ctx):
        await patch_db.execute(
            """INSERT INTO agent_requests
               (id, business_id, submitted_by_user_id, raw_input,
                structured_request, request_type, employee_id, status)
               VALUES (?, ?, 'USER-001', 'Friday off',
                       ?, 'leave', ?, 'pending')""",
            (
                "aaaaaaaa-0000-0000-0000-000000000001",
                g.BUSINESS_ID,
                json.dumps({"dates": ["2026-09-04"]}),
                g.emp_uuid("EMP-001"),
            ),
        )
        r = await read_tools.get_pending_requests("EMP-001", ctx)
        assert r.success is True
        assert len(r.data) == 1
        assert r.data[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_none_pending(self, patch_db, ctx):
        r = await read_tools.get_pending_requests("EMP-005", ctx)
        assert r.success is True
        assert r.data == []


# ======================================================================
# get_task_assignments
# ======================================================================
class TestTaskAssignments:
    @pytest.mark.asyncio
    async def test_david_chen_has_high_priority(self, patch_db, ctx):
        r = await read_tools.get_task_assignments("EMP-003", ctx)
        assert r.success is True
        titles = {t["title"] for t in r.data}
        assert "API Gateway Migration" in titles           # TASK-001 (EVL-008)
        assert "Payment Gateway Hotfix" in titles          # TASK-002 (EVL-011)

    @pytest.mark.asyncio
    async def test_daniel_oktafor_support_task(self, patch_db, ctx):
        r = await read_tools.get_task_assignments("EMP-005", ctx)
        assert r.success is True
        titles = {t["title"] for t in r.data}
        assert "Escalation Backlog Review" in titles       # TASK-003 (EVL-016)


# ======================================================================
# get_attendance
# ======================================================================
class TestAttendance:
    @pytest.mark.asyncio
    async def test_normal(self, patch_db, ctx):
        r = await read_tools.get_attendance("EMP-001", 90, ctx)
        assert r.success is True
        assert r.data["total_records"] > 0
        assert isinstance(r.data["records"], list)

    @pytest.mark.asyncio
    async def test_john_carter_four_lates(self, patch_db, ctx):
        r = await read_tools.get_attendance("EMP-002", 365, ctx)
        assert r.success is True
        assert r.data["late_count"] == 4        # 4 lates in the 60-day window
        assert r.data["warning_count"] == 2     # 2 formal warnings


# ======================================================================
# get_historical_decisions
# ======================================================================
class TestHistoricalDecisions:
    @pytest.mark.asyncio
    async def test_has_history(self, patch_db, ctx):
        r = await read_tools.get_historical_decisions("EMP-001", "leave_request", ctx)
        assert r.success is True
        assert r.data["total_count"] >= 2
        assert r.data["label"] == "HISTORICAL"
        # Explicit warning that precedent is not policy.
        assert "NOT current policy" in r.data["warning"]

    @pytest.mark.asyncio
    async def test_no_history(self, patch_db, ctx):
        r = await read_tools.get_historical_decisions("EMP-004", "leave_request", ctx)
        assert r.success is True
        assert r.data["total_count"] == 0


# ======================================================================
# Action tools
# ======================================================================
class TestActionTools:
    @pytest.mark.asyncio
    async def test_create_leave_request_then_idempotent(self, patch_db, ctx):
        policy = g.policy_uuid("POL-001")
        run_id = "bbbbbbbb-0000-0000-0000-000000000001"
        r = await action_tools.create_leave_request(
            g.emp_uuid("EMP-001"), [date(2026, 10, 1)],
            "Annual leave", policy, run_id, ctx,
        )
        assert r.success is True
        assert r.data["request_id"] is not None

        # Second identical call must be rejected as a duplicate.
        r2 = await action_tools.create_leave_request(
            g.emp_uuid("EMP-001"), [date(2026, 10, 1)],
            "Annual leave", policy, run_id, ctx,
        )
        assert r2.success is False
        assert r2.error == "DUPLICATE_REQUEST"

    @pytest.mark.asyncio
    async def test_create_approval_request(self, patch_db, ctx):
        run_id = "bbbbbbbb-0000-0000-0000-000000000002"
        # A run + request must exist so the approval can be linked.
        await patch_db.execute(
            """INSERT INTO agent_requests
               (id, business_id, raw_input, request_type, status)
               VALUES (?, ?, 'termination request', 'termination', 'pending')""",
            ("cccccccc-0000-0000-0000-000000000001", g.BUSINESS_ID),
        )
        await patch_db.execute(
            """INSERT INTO agent_runs
               (id, request_id, business_id, status)
               VALUES (?, 'cccccccc-0000-0000-0000-000000000001', ?, 'running')""",
            (run_id, g.BUSINESS_ID),
        )
        r = await action_tools.create_approval_request(
            run_id, "decision-1", "Tier 3 review", 3, "critical", ctx,
        )
        assert r.success is True
        assert r.data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_update_status_legal(self, patch_db, ctx):
        await patch_db.execute(
            """INSERT INTO agent_requests
               (id, business_id, raw_input, request_type, status)
               VALUES (?, ?, 'leave', 'leave', 'pending')""",
            ("dddddddd-0000-0000-0000-000000000001", g.BUSINESS_ID),
        )
        r = await action_tools.update_request_status(
            "dddddddd-0000-0000-0000-000000000001", "processing", ctx,
        )
        assert r.success is True
        assert r.data["new_status"] == "processing"

    @pytest.mark.asyncio
    async def test_update_status_illegal(self, patch_db, ctx):
        await patch_db.execute(
            """INSERT INTO agent_requests
               (id, business_id, raw_input, request_type, status)
               VALUES (?, ?, 'leave', 'leave', 'pending')""",
            ("eeeeeeee-0000-0000-0000-000000000001", g.BUSINESS_ID),
        )
        r = await action_tools.update_request_status(
            "eeeeeeee-0000-0000-0000-000000000001", "approved", ctx,
        )
        assert r.success is False
        assert r.error == "ILLEGAL_TRANSITION"


# ======================================================================
# Tool registry
# ======================================================================
class TestRegistry:
    def test_tool_is_registered(self):
        from backend.app.tools.registry import registry

        names = ("get_employee", "get_leave_balance", "get_policy",
                 "get_schedule", "get_team_coverage", "get_pending_requests",
                 "get_task_assignments", "get_attendance",
                 "get_historical_decisions", "create_leave_request",
                 "create_approval_request", "update_request_status")
        for name in names:
            meta = registry.get(name)
            assert meta is not None, f"{name} not registered"
            assert meta.risk_classification in ("read", "reversible", "consequential")

    @pytest.mark.asyncio
    async def test_registry_call_records_tool_call(self, patch_db, ctx):
        from backend.app.tools.registry import registry

        r = await registry.call_tool("get_employee", {"identifier": "Sarah Mitchell"}, ctx)
        assert r.success is True
        rows = await patch_db.fetch_many(
            "SELECT * FROM agent_tool_calls WHERE tool_name = 'get_employee'",
            None,
        )
        assert len(rows) == 1
        assert rows[0]["success"] == 1
