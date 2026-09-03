"""Human Approval API tests for OpsPilot.

Run:  cd backend && PYTHONPATH=.. pytest tests/test_approval.py -v

Covers the four approval endpoints and the guarantee that the approval
record carries the full DecisionOutput, ConstitutionalCheckResult,
EvidenceManifest and trajectory link.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.models.agent import AgentRunState, AgentStep
from backend.app.routers.runs import _runs
from backend.data import generator as g

RUN_ID = "bbbbbbbb-0000-0000-0000-000000000010"
REQUEST_ID = "cccccccc-0000-0000-0000-000000000010"
APPROVAL_ID = "aaaaaaaa-0000-0000-0000-000000000010"


def _make_test_app():
    """TestClient app with the DB pool patched out."""
    from backend.app import database as db_mod
    from backend.app import main as main_mod

    async def _noop():
        pass

    db_mod._pool = None
    db_mod.init_pool = _noop
    db_mod.close_pool = _noop
    return main_mod.app


def _payload() -> str:
    return json.dumps({
        "decision": {
            "decision_type": "escalate",
            "confidence": 0.85,
            "reason": "Termination requires human review",
            "authorization_tier": 3,
            "requires_human_approval": True,
        },
        "constitutional_check": {"passed": True, "violations": []},
        "evidence_manifest": {
            "run_id": RUN_ID,
            "request_type": "termination",
            "items": [
                {
                    "tool_call_id": "tc-1",
                    "evidence_type": "employee",
                    "evidence_key": "employee_record",
                    "data": {"id": g.emp_uuid("EMP-002"), "status": "active"},
                }
            ],
        },
    })


async def _seed_approval(
    fake_db,
    *,
    status: str = "pending",
    with_payload: bool = True,
    approval_id: str = APPROVAL_ID,
    run_id: str = RUN_ID,
    request_id: str = REQUEST_ID,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await fake_db.execute(
        """INSERT INTO agent_requests
           (id, business_id, employee_id, raw_input, request_type, status, created_at)
           VALUES (?, ?, ?, 'Fire John Carter, he has been repeatedly late',
                   'termination', 'processing', ?)""",
        (request_id, g.BUSINESS_ID, g.emp_uuid("EMP-002"), now),
    )
    await fake_db.execute(
        """INSERT INTO agent_runs
           (id, request_id, business_id, status, authorization_tier)
           VALUES (?, ?, ?, 'WAITING_FOR_APPROVAL', 3)""",
        (run_id, request_id, g.BUSINESS_ID),
    )
    await fake_db.execute(
        """INSERT INTO agent_approvals
           (id, request_id, run_id, decision_id, approval_reason,
            authorization_tier, risk_level, status, created_at, decision_payload)
           VALUES (?, ?, ?, 'decision-1', 'Termination requires human review',
                   3, 'critical', ?, ?, ?)""",
        (
            approval_id,
            request_id,
            run_id,
            status,
            now,
            _payload() if with_payload else None,
        ),
    )


@pytest.fixture
def client(patch_db):
    _runs.clear()
    return TestClient(_make_test_app(), raise_server_exceptions=False)


# ======================================================================
# Listing + detail
# ======================================================================
class TestApprovalList:
    def test_list_pending_approvals(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db))

        resp = client.get("/api/approvals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["approvals"][0]["id"] == APPROVAL_ID
        assert data["approvals"][0]["status"] == "pending"
        assert data["approvals"][0]["authorization_tier"] == 3

    def test_list_filters_by_status(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db, status="approved"))
        asyncio.run(_seed_approval(
            patch_db,
            status="pending",
            approval_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
        ))

        resp = client.get("/api/approvals?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["approvals"][0]["status"] == "pending"

    def test_list_filters_default_pending_excludes_reviewed(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db, status="rejected"))

        resp = client.get("/api/approvals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_get_approval_not_found(self, client, patch_db):
        _ = patch_db
        resp = client.get("/api/approvals/nonexistent-id")
        assert resp.status_code == 404
        resp = client.post("/api/approvals/nonexistent-id/approve", json={})
        assert resp.status_code == 404

    def test_get_approval_detail_has_decision_and_trajectory(self, client, patch_db):
        _runs[RUN_ID] = AgentRunState(
            run_id=RUN_ID,
            request_id=REQUEST_ID,
            business_id=g.BUSINESS_ID,
            status="WAITING_FOR_APPROVAL",
            steps=[
                AgentStep(step_number=1, agent="request_parser", status="completed"),
                AgentStep(step_number=2, agent="context_assembly", status="completed"),
                AgentStep(step_number=3, agent="decision_agent", status="completed"),
            ],
        )
        asyncio.run(_seed_approval(patch_db))

        resp = client.get(f"/api/approvals/{APPROVAL_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"]["authorization_tier"] == 3
        assert data["constitutional_check"]["passed"] is True
        assert len(data["evidence_manifest"]["items"]) == 1
        assert data["employee_name"] is not None
        assert [s["agent"] for s in data["trajectory"]] == [
            "request_parser", "context_assembly", "decision_agent",
        ]
        assert data["run_id"] == RUN_ID


# ======================================================================
# Approve / reject
# ======================================================================
class TestApprovalReview:
    def test_approve_resumes_run_and_audits(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db))

        resp = client.post(
            f"/api/approvals/{APPROVAL_ID}/approve",
            json={"notes": "Approved by HR"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["run_id"] == RUN_ID
        assert data["run_status"] == "COMPLETED"
        assert data["final_outcome"] == "approved"

        row = patch_db.conn.execute(
            "SELECT status, review_notes FROM agent_approvals WHERE id = ?",
            (APPROVAL_ID,),
        ).fetchone()
        assert row[0] == "approved"
        assert row[1] == "Approved by HR"

        audit = patch_db.conn.execute(
            "SELECT action, result FROM audit_logs WHERE action = 'approval.approved'"
        ).fetchall()
        assert len(audit) == 1
        assert audit[0][1] == "approved"

    def test_reject_closes_run_and_audits(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db))

        resp = client.post(
            f"/api/approvals/{APPROVAL_ID}/reject",
            json={"notes": "Denied — succession risk"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["run_status"] == "COMPLETED"
        assert data["final_outcome"] == "rejected"

        row = patch_db.conn.execute(
            "SELECT status FROM agent_approvals WHERE id = ?", (APPROVAL_ID,),
        ).fetchone()
        assert row[0] == "rejected"

        audit = patch_db.conn.execute(
            "SELECT action FROM audit_logs WHERE action = 'approval.rejected'"
        ).fetchall()
        assert len(audit) == 1

    def test_cannot_review_an_already_reviewed_approval(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db, status="approved"))

        resp = client.post(f"/api/approvals/{APPROVAL_ID}/approve", json={"notes": "again"})
        assert resp.status_code == 409

    def test_approve_then_reject_is_conflict(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db))

        first = client.post(f"/api/approvals/{APPROVAL_ID}/approve", json={})
        assert first.status_code == 200
        second = client.post(f"/api/approvals/{APPROVAL_ID}/reject", json={})
        assert second.status_code == 409

    def test_approve_updates_shared_run_store(self, client, patch_db):
        _runs[RUN_ID] = AgentRunState(
            run_id=RUN_ID,
            request_id=REQUEST_ID,
            business_id=g.BUSINESS_ID,
            status="WAITING_FOR_APPROVAL",
        )
        asyncio.run(_seed_approval(patch_db))

        resp = client.post(f"/api/approvals/{APPROVAL_ID}/approve", json={})
        assert resp.status_code == 200

        updated = _runs[RUN_ID]
        assert updated.status == "COMPLETED"
        assert updated.final_outcome == "approved"


class TestAuditAPI:
    def test_audit_route_returns_rows(self, client, patch_db):
        asyncio.run(_seed_approval(patch_db))
        client.post(f"/api/approvals/{APPROVAL_ID}/approve", json={"notes": "ok"})

        resp = client.get("/api/audit?business_id=" + g.BUSINESS_ID)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        actions = {row["action"] for row in data["audit"]}
        assert "approval.approved" in actions

    def test_audit_route_empty_without_matches(self, client, patch_db):
        _ = patch_db
        resp = client.get("/api/audit?business_id=does-not-exist")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0