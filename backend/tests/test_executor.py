"""Action Executor tests for OpsPilot.

Run:  cd backend && PYTHONPATH=.. pytest tests/test_executor.py -v

Covers the four controlled-execution paths plus the idempotency rule
(identical action for the same run is never executed twice) and the
approval-request payload (DecisionOutput + ConstitutionalCheckResult +
EvidenceManifest + trajectory).
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

from backend.app.models.agent import EvidenceItem, EvidenceManifest
from backend.app.models.tool_contract import ToolContext
from backend.app.orchestrator.executor import ActionExecutor
from backend.data import generator as g

RUN_ID = "bbbbbbbb-0000-0000-0000-000000000002"
REQUEST_ID = "cccccccc-0000-0000-0000-000000000001"


def make_ctx(run_id: str = RUN_ID) -> ToolContext:
    return ToolContext(
        business_id=g.BUSINESS_ID,
        requesting_user_id="USER-001",
        user_role="manager",
        run_id=run_id,
        step_id="dddddddd-0000-0000-0000-000000000001",
    )


async def seed_run(patch_db, run_id: str = RUN_ID, request_id: str = REQUEST_ID):
    """Create the agent_request + agent_runs rows the executor links to."""
    await patch_db.execute(
        """INSERT INTO agent_requests
           (id, business_id, raw_input, request_type, status)
           VALUES (?, ?, 'test request', 'request', 'pending')""",
        (request_id, g.BUSINESS_ID),
    )
    await patch_db.execute(
        """INSERT INTO agent_runs
           (id, request_id, business_id, status)
           VALUES (?, ?, ?, 'running')""",
        (run_id, request_id, g.BUSINESS_ID),
    )


# ======================================================================
# Leave request execution
# ======================================================================
class TestExecuteLeaveRequest:
    @pytest.mark.asyncio
    async def test_leave_request_executed_and_audited(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()

        result = await executor.execute_leave_request(
            run_id=RUN_ID,
            employee_id=g.emp_uuid("EMP-001"),
            dates=[date(2026, 10, 1)],
            policy_id=g.policy_uuid("POL-001"),
            ctx=ctx,
        )

        assert result.success is True
        assert result.data["status"] == "completed"

        # The leave request row now exists and is marked completed.
        rows = await patch_db.fetch_many(
            "SELECT * FROM agent_requests WHERE request_type = 'leave'", None,
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"

        # An audit row was appended.
        audit = await patch_db.fetch_many(
            "SELECT * FROM audit_logs WHERE action = 'leave_request_executed'",
            None,
        )
        assert len(audit) == 1
        assert audit[0]["run_id"] == RUN_ID

    @pytest.mark.asyncio
    async def test_leave_request_idempotent(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()
        args = (RUN_ID, g.emp_uuid("EMP-001"), [date(2026, 10, 1)], "policy-x", ctx)

        first = await executor.execute_leave_request(*args)
        second = await executor.execute_leave_request(*args)

        assert first.success is True
        assert second.success is True
        assert second.data["idempotent"] is True

        # Only one leave request ever created.
        rows = await patch_db.fetch_many(
            "SELECT * FROM agent_requests WHERE request_type = 'leave'", None,
        )
        assert len(rows) == 1


# ======================================================================
# Task reassignment
# ======================================================================
class TestExecuteTaskReassignment:
    @pytest.mark.asyncio
    async def test_task_reassigned_and_audited(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()
        task_id = "10000000-0000-0000-0000-000000000001"
        new_employee = g.emp_uuid("EMP-001")

        result = await executor.execute_task_reassignment(
            RUN_ID, task_id, new_employee, ctx,
        )

        assert result.success is True
        assert result.data["assigned_to"] == new_employee

        rows = await patch_db.fetch_many(
            "SELECT assigned_to FROM tasks WHERE id = ?", (task_id,),
        )
        assert rows[0]["assigned_to"] == new_employee

        audit = await patch_db.fetch_many(
            "SELECT * FROM audit_logs WHERE action = 'task_reassignment_executed'",
            None,
        )
        assert len(audit) == 1

    @pytest.mark.asyncio
    async def test_task_reassignment_rejects_unavailable_employee(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()

        # EMP-044 is on_leave in the seeded world.
        result = await executor.execute_task_reassignment(
            RUN_ID,
            "10000000-0000-0000-0000-000000000001",
            g.emp_uuid("EMP-044"),
            ctx,
        )
        assert result.success is False
        assert result.error == "EMPLOYEE_NOT_AVAILABLE"

    @pytest.mark.asyncio
    async def test_task_reassignment_missing_task(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()

        result = await executor.execute_task_reassignment(
            RUN_ID,
            "ffffffff-0000-0000-0000-000000000001",
            g.emp_uuid("EMP-001"),
            ctx,
        )
        assert result.success is False
        assert result.error == "TASK_NOT_FOUND"


# ======================================================================
# Information response (tier 1, no DB mutation)
# ======================================================================
class TestExecuteInformationResponse:
    @pytest.mark.asyncio
    async def test_information_response_audited_no_db_changes(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()

        result = await executor.execute_information_response(
            RUN_ID, "He has 14 days of annual leave remaining.", ctx,
        )

        assert result.success is True
        assert result.data["no_db_changes"] is True

        audit = await patch_db.fetch_many(
            "SELECT * FROM audit_logs WHERE action = 'information_response'",
            None,
        )
        assert len(audit) == 1
        assert "14 days" in audit[0]["metadata"]

        # No new requests or approvals were created.
        requests = await patch_db.fetch_many(
            "SELECT * FROM agent_requests", None,
        )
        assert len(requests) == 1  # only the seeded one

    @pytest.mark.asyncio
    async def test_information_response_emits_action_completed(self, patch_db):
        from backend.app.orchestrator.events import event_bus

        event_bus._history.clear()
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()
        await executor.execute_information_response(RUN_ID, "yes", ctx)

        types = [e.event_type for e in event_bus.get_history(RUN_ID)]
        assert "action.completed" in types


# ======================================================================
# Approval request creation
# ======================================================================
class TestCreateApprovalRequest:
    @pytest.mark.asyncio
    async def test_approval_request_stores_full_payload(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()

        decision = {
            "decision_type": "escalate",
            "confidence": 0.85,
            "reason": "Termination requires human review",
            "authorization_tier": 3,
            "requires_human_approval": True,
        }
        constitutional = {"passed": True, "violations": []}
        manifest = EvidenceManifest(
            run_id=RUN_ID,
            request_type="termination",
            items=[
                EvidenceItem(
                    tool_call_id="tc-1",
                    evidence_type="employee",
                    evidence_key="employee_record",
                    data={"id": g.emp_uuid("EMP-002"), "status": "active"},
                )
            ],
        )

        result = await executor.create_approval_request(
            run_id=RUN_ID,
            decision_id="decision-1",
            reason="Termination requires human review",
            tier=3,
            ctx=ctx,
            decision=decision,
            constitutional_result=constitutional,
            evidence_manifest=manifest,
        )

        assert result.success is True
        assert result.data["status"] == "pending"
        approval_id = result.data["approval_id"]

        rows = await patch_db.fetch_many(
            "SELECT * FROM agent_approvals WHERE id = ?", (approval_id,),
        )
        assert len(rows) == 1
        payload = json.loads(rows[0]["decision_payload"])
        assert payload["decision"]["authorization_tier"] == 3
        assert payload["constitutional_check"]["passed"] is True
        assert len(payload["evidence_manifest"]["items"]) == 1
        assert payload["trajectory"] == {"run_id": RUN_ID}

    @pytest.mark.asyncio
    async def test_approval_request_emits_approval_required(self, patch_db):
        from backend.app.orchestrator.events import event_bus

        event_bus._history.clear()
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()
        await executor.create_approval_request(
            run_id=RUN_ID,
            decision_id="decision-1",
            reason="Tier 3",
            tier=3,
            ctx=ctx,
        )
        events = event_bus.get_history(RUN_ID)
        approval_events = [e for e in events if e.event_type == "approval.required"]
        assert len(approval_events) == 1

    @pytest.mark.asyncio
    async def test_approval_request_idempotent(self, patch_db):
        ctx = make_ctx()
        await seed_run(patch_db)
        executor = ActionExecutor()
        args = (RUN_ID, "decision-1", "Tier 3", 3, ctx)

        first = await executor.create_approval_request(*args)
        second = await executor.create_approval_request(*args)

        assert first.success is True
        assert second.success is True
        assert second.data["idempotent"] is True
        rows = await patch_db.fetch_many("SELECT * FROM agent_approvals", None)
        assert len(rows) == 1