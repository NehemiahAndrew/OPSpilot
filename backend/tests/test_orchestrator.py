"""Orchestrator tests for OpsPilot.

Tests the state machine, orchestrator flows, and API endpoints.
Run:  cd backend && PYTHONPATH=.. pytest tests/test_orchestrator.py -v
"""

from __future__ import annotations

import asyncio
import pytest

from backend.app.orchestrator.state import (
    WorkflowStatus,
    IllegalTransitionError,
    LEGAL_TRANSITIONS,
    validate_transition,
)
from backend.app.orchestrator.events import EventBus, OrchestratorEvent
from backend.app.orchestrator.workflow import (
    RequestParser,
    AgentOrchestrator,
)
from backend.app.models.agent import AgentRunState, StructuredRequest
from backend.app.models.tool_contract import ToolContext


# ======================================================================
# State Machine Tests
# ======================================================================
class TestWorkflowStatus:
    def test_all_statuses_exist(self):
        statuses = [s.value for s in WorkflowStatus]
        expected = [
            "INIT", "RECEIVED", "PARSING", "CONTEXT_GATHERING", "EVIDENCE_ASSEMBLY",
            "DECISION", "VERIFICATION", "AUTHORIZATION", "WAITING_FOR_APPROVAL",
            "EXECUTING", "COMPLETED", "FAILED", "BLOCKED", "NEEDS_CLARIFICATION",
        ]
        assert sorted(statuses) == sorted(expected)

    def test_status_is_string_enum(self):
        assert WorkflowStatus.RECEIVED == "RECEIVED"
        assert isinstance(WorkflowStatus.RECEIVED, str)


class TestLegalTransitions:
    def test_init_to_received(self):
        validate_transition("INIT", "RECEIVED")

    def test_received_to_parsing(self):
        validate_transition("RECEIVED", "PARSING")

    def test_received_to_failed(self):
        validate_transition("RECEIVED", "FAILED")

    def test_parsing_to_context_gathering(self):
        validate_transition("PARSING", "CONTEXT_GATHERING")

    def test_parsing_to_needs_clarification(self):
        validate_transition("PARSING", "NEEDS_CLARIFICATION")

    def test_verification_to_authorization(self):
        validate_transition("VERIFICATION", "AUTHORIZATION")

    def test_verification_to_blocked(self):
        validate_transition("VERIFICATION", "BLOCKED")

    def test_authorization_to_executing(self):
        validate_transition("AUTHORIZATION", "EXECUTING")

    def test_authorization_to_waiting_for_approval(self):
        validate_transition("AUTHORIZATION", "WAITING_FOR_APPROVAL")

    def test_waiting_to_executing(self):
        validate_transition("WAITING_FOR_APPROVAL", "EXECUTING")

    def test_waiting_to_completed(self):
        validate_transition("WAITING_FOR_APPROVAL", "COMPLETED")

    def test_executing_to_completed(self):
        validate_transition("EXECUTING", "COMPLETED")

    def test_executing_to_failed(self):
        validate_transition("EXECUTING", "FAILED")

    def test_blocked_to_waiting(self):
        validate_transition("BLOCKED", "WAITING_FOR_APPROVAL")

    def test_blocked_to_failed(self):
        validate_transition("BLOCKED", "FAILED")

    def test_all_transitions_defined(self):
        for status in WorkflowStatus:
            assert status in LEGAL_TRANSITIONS, f"Missing transitions for {status}"


class TestIllegalTransitions:
    def test_received_to_completed(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("RECEIVED", "COMPLETED")

    def test_completed_is_terminal(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("COMPLETED", "EXECUTING")

    def test_completed_to_anything_fails(self):
        for status in WorkflowStatus:
            if status == WorkflowStatus.COMPLETED:
                continue
            with pytest.raises(IllegalTransitionError):
                validate_transition("COMPLETED", status.value)

    def test_failed_is_terminal(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("FAILED", "RECEIVED")

    def test_failed_to_anything_fails(self):
        for status in WorkflowStatus:
            if status == WorkflowStatus.FAILED:
                continue
            with pytest.raises(IllegalTransitionError):
                validate_transition("FAILED", status.value)

    def test_blocked_cannot_auto_proceed(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("BLOCKED", "EXECUTING")

    def test_blocked_cannot_go_to_completed(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("BLOCKED", "COMPLETED")

    def test_authorization_cannot_skip_to_completed(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("AUTHORIZATION", "COMPLETED")

    def test_needs_clarification_is_terminal(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("NEEDS_CLARIFICATION", "PARSING")

    def test_context_gathering_cannot_skip_to_decision(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("CONTEXT_GATHERING", "DECISION")

    def test_invalid_status_string(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("RECEIVED", "NONEXISTENT")

    def test_invalid_from_status(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition("NONEXISTENT", "PARSING")


# ======================================================================
# Event Bus Tests
# ======================================================================
class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self):
        bus = EventBus()
        queue = bus.subscribe("run-1")

        event = OrchestratorEvent(
            run_id="run-1",
            event_type="run.started",
            message="Test event",
        )
        await bus.publish(event)

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.event_type == "run.started"
        assert received.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = EventBus()
        q1 = bus.subscribe("run-1")
        q2 = bus.subscribe("run-1")

        event = OrchestratorEvent(run_id="run-1", event_type="test.event")
        await bus.publish(event)

        r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert r1.event_type == r2.event_type == "test.event"

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = EventBus()
        q = bus.subscribe("run-1")
        bus.unsubscribe("run-1", q)
        assert "run-1" not in bus._subscribers

    @pytest.mark.asyncio
    async def test_history_replay(self):
        bus = EventBus()
        e1 = OrchestratorEvent(run_id="run-1", event_type="first")
        e2 = OrchestratorEvent(run_id="run-1", event_type="second")
        await bus.publish(e1)
        await bus.publish(e2)

        # Subscribe with last_event_id = e1's id — should replay e2
        q = bus.subscribe("run-1", last_event_id=e1.event_id)
        received = await asyncio.wait_for(q.get(), timeout=1.0)
        assert received.event_type == "second"

    @pytest.mark.asyncio
    async def test_event_to_sse(self):
        event = OrchestratorEvent(
            run_id="run-1",
            event_type="test",
            metadata={"key": "value"},
        )
        sse = event.to_sse()
        assert "run-1" in sse
        assert "test" in sse

    @pytest.mark.asyncio
    async def test_history_trimmed(self):
        bus = EventBus(max_history=3)
        for i in range(5):
            await bus.publish(OrchestratorEvent(run_id="r1", event_type=f"e{i}"))
        assert len(bus.get_history("r1")) == 3


# ======================================================================
# Request Parser Tests
# ======================================================================
class TestRequestParser:
    def test_leave_request(self):
        parser = RequestParser()
        result = parser.parse("I need to take a day off tomorrow for a doctor appointment")
        assert result.request_type == "leave"
        assert result.date_hint is not None
        assert result.confidence >= 0.5

    def test_ambiguous_input(self):
        parser = RequestParser()
        result = parser.parse("hello")
        assert result.confidence < 0.5
        assert "request_type" in result.missing_fields

    def test_employee_extraction(self):
        parser = RequestParser()
        result = parser.parse("Schedule leave for John Smith on 2026-09-15")
        assert result.employee_hint == "John Smith"
        assert result.request_type == "leave"

    def test_urgency_detection(self):
        parser = RequestParser()
        result = parser.parse("URGENT: need emergency leave for Sarah Connor tomorrow")
        assert result.urgency == "high"

    def test_low_urgency(self):
        parser = RequestParser()
        result = parser.parse("Whenever convenient, take a day off for David Lee")
        assert result.urgency == "low"


# ======================================================================
# Orchestrator Flow Tests
# ======================================================================
@pytest.fixture
def ctx():
    """Standard ToolContext for tests."""
    return ToolContext(
        business_id="a0000000-0000-0000-0000-000000000001",
        requesting_user_id="USER-001",
        user_role="manager",
        run_id="",
        step_id="",
    )


class TestOrchestratorNormalFlow:
    @pytest.mark.asyncio
    async def test_normal_flow_reaches_completed(self, ctx):
        orch = AgentOrchestrator()
        state = await orch.run(
            request_id="req-001",
            raw_input="I need to take a day off on 2026-09-15 for vacation",
            ctx=ctx,
        )
        assert state.status == WorkflowStatus.COMPLETED
        assert state.final_outcome == "approve"
        assert state.structured_request is not None
        assert state.structured_request.request_type == "leave"
        assert len(state.steps) >= 3
        assert state.completed_at is not None

    @pytest.mark.asyncio
    async def test_events_emitted(self, ctx):
        from backend.app.orchestrator.events import event_bus

        orch = AgentOrchestrator()
        state = await orch.run(
            request_id="req-002",
            raw_input="Take leave on 2026-10-01 for David Lee because of family event",
            ctx=ctx,
        )
        history = event_bus.get_history(state.run_id)
        event_types = [e.event_type for e in history]
        assert "run.started" in event_types
        assert "parsing.started" in event_types
        assert "parsing.completed" in event_types
        assert "tool.calling" in event_types
        assert "tool.completed" in event_types
        assert "evidence.assembled" in event_types
        assert "decision.completed" in event_types
        assert "verification.passed" in event_types
        assert "authorization.evaluated" in event_types
        assert "run.completed" in event_types
        assert len(state.tool_calls) >= 3

    @pytest.mark.asyncio
    async def test_structured_request_populated(self, ctx):
        orch = AgentOrchestrator()
        state = await orch.run(
            request_id="req-003",
            raw_input="Schedule leave for Emily Clark on 2026-11-20 because of wedding",
            ctx=ctx,
        )
        sr = state.structured_request
        assert sr is not None
        assert sr.request_type == "leave"
        assert sr.employee_hint == "Emily Clark"
        assert sr.date_hint == "2026-11-20"
        assert sr.reason is not None


class TestOrchestratorClarification:
    @pytest.mark.asyncio
    async def test_needs_clarification_stops_at_parsing(self, ctx):
        orch = AgentOrchestrator()
        state = await orch.run(
            request_id="req-clarify",
            raw_input="hello",
            ctx=ctx,
        )
        assert state.status == WorkflowStatus.NEEDS_CLARIFICATION
        assert state.completed_at is not None
        # Should NOT have gone past parsing
        step_agents = [s.agent for s in state.steps]
        assert "request_parser" in step_agents
        assert "context_assembly" not in step_agents


class TestOrchestratorFailedTool:
    @pytest.mark.asyncio
    async def test_illegal_transition_goes_to_failed(self, ctx):
        orch = AgentOrchestrator()
        # Patch the _transition to raise an error at a specific point
        original_transition = orch._transition

        call_count = 0

        def failing_transition(run_state, new_status):
            nonlocal call_count
            call_count += 1
            # Fail on the 5th transition (VERIFICATION -> AUTHORIZATION)
            if call_count == 5:
                raise IllegalTransitionError("BLOCKED", "EXECUTING")
            return original_transition(run_state, new_status)

        orch._transition = failing_transition
        state = await orch.run(
            request_id="req-fail",
            raw_input="Take leave on 2026-09-15 for vacation",
            ctx=ctx,
        )
        assert state.status == WorkflowStatus.FAILED
        assert len(state.errors) > 0


class TestOrchestratorTier3Approval:
    @pytest.mark.asyncio
    async def test_tier3_goes_to_waiting_for_approval(self, ctx):
        orch = AgentOrchestrator()

        # Override the decision step to return tier 3
        original_add_step = orch._add_step

        def tier3_add_step(run_state, agent):
            step = original_add_step(run_state, agent)
            if agent == "decision_agent":
                run_state.decision = {
                    "decision_type": "terminate",
                    "confidence": 0.85,
                    "reason": "Policy violation",
                    "authorization_tier": 3,
                }
                run_state.authorization_tier = 3
            return step

        orch._add_step = tier3_add_step
        state = await orch.run(
            request_id="req-tier3",
            raw_input="Initiate termination for employee on 2026-09-15 because of policy violation",
            ctx=ctx,
        )
        assert state.status == WorkflowStatus.WAITING_FOR_APPROVAL
        assert state.authorization_tier == 3
        assert state.approval_id is not None


class TestOrchestratorResume:
    @pytest.mark.asyncio
    async def test_resume_after_approval(self, ctx):
        orch = AgentOrchestrator()
        state = await orch.resume_after_approval(
            run_id="run-approve",
            approval_decision="approved",
            reviewer_notes="Approved by admin",
            ctx=ctx,
        )
        assert state.status == WorkflowStatus.COMPLETED
        assert state.final_outcome == "approved"

    @pytest.mark.asyncio
    async def test_resume_after_rejection(self, ctx):
        orch = AgentOrchestrator()
        state = await orch.resume_after_approval(
            run_id="run-reject",
            approval_decision="rejected",
            reviewer_notes="Denied due to coverage",
            ctx=ctx,
        )
        assert state.status == WorkflowStatus.COMPLETED
        assert state.final_outcome == "rejected"

    @pytest.mark.asyncio
    async def test_resume_emits_events(self, ctx):
        from backend.app.orchestrator.events import event_bus

        orch = AgentOrchestrator()
        state = await orch.resume_after_approval(
            run_id="run-events",
            approval_decision="approved",
            reviewer_notes="OK",
            ctx=ctx,
        )
        history = event_bus.get_history(state.run_id)
        event_types = [e.event_type for e in history]
        assert "action.executing" in event_types
        assert "run.completed" in event_types


# ======================================================================
# API Route Tests (with mocked DB)
# ======================================================================
def _make_test_app():
    """Create a TestClient with lifespan DB patched out."""
    from backend.app import database as db_mod
    from backend.app import main as main_mod

    async def _noop(): pass

    db_mod._pool = None
    db_mod.init_pool = _noop
    db_mod.close_pool = _noop
    return main_mod.app


class TestRequestAPI:
    def test_create_request_returns_ids(self, patch_db):
        from fastapi.testclient import TestClient
        from backend.app.routers.runs import _runs

        _runs.clear()
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/requests",
            json={"raw_input": "Take leave tomorrow for vacation"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "request_id" in data
        assert "run_id" in data


class TestRunsAPI:
    def test_list_runs_empty(self, patch_db):
        from fastapi.testclient import TestClient
        from backend.app.routers.runs import _runs

        _runs.clear()
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_get_run_not_found(self, patch_db):
        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/runs/nonexistent")
        assert resp.status_code == 404

    def test_get_run_found(self, patch_db):
        from fastapi.testclient import TestClient
        from backend.app.models.agent import AgentRunState
        from backend.app.routers.runs import _runs

        run = AgentRunState(
            run_id="test-run-123",
            request_id="req-123",
            business_id="biz-123",
            status="COMPLETED",
        )
        _runs["test-run-123"] = run

        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/runs/test-run-123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "test-run-123"
        assert data["status"] == "COMPLETED"

    async def test_stream_endpoint_returns_200(self, patch_db):
        from backend.app.models.agent import AgentRunState
        from backend.app.routers.runs import _runs
        from backend.app.orchestrator.events import event_bus, OrchestratorEvent

        run = AgentRunState(
            run_id="stream-run-1",
            request_id="req-stream",
            business_id="biz-123",
            status="COMPLETED",
        )
        _runs["stream-run-1"] = run

        from backend.app.routers.runs import stream_events

        # Call the endpoint handler directly to get the StreamingResponse
        response = await stream_events("stream-run-1")

        # Now publish an event so the generator yields it
        event = OrchestratorEvent(
            run_id="stream-run-1",
            event_type="run.completed",
            step_number=1,
            agent="orchestrator",
            status="completed",
        )
        await event_bus.publish(event)

        # Read the first chunk from the body iterator
        body = ""
        async for chunk in response.body_iterator:
            body += chunk
            if len(body) > 10:
                break
        assert response.status_code == 200
        assert response.media_type == "text/event-stream"
        assert "data:" in body

    @pytest.mark.asyncio
    async def test_stream_accepts_pending_run_via_history(self, patch_db):
        from backend.app.routers.runs import stream_events
        from backend.app.routers.runs import _runs
        from backend.app.orchestrator.events import event_bus, OrchestratorEvent

        _runs.clear()
        run_id = "pending-stream-run-1"

        # Run not stored yet, but the requests API seeded history
        await event_bus.publish(
            OrchestratorEvent(run_id=run_id, event_type="run.created")
        )
        response = await stream_events(run_id)
        assert response.status_code == 200
        event_bus._history.pop(run_id, None)

    def test_trajectory_not_found(self, patch_db):
        from fastapi.testclient import TestClient
        from backend.app.routers.runs import _runs

        _runs.clear()
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/runs/nonexistent/trajectory")
        assert resp.status_code == 404

    def test_trajectory_returns_full_payload(self, patch_db):
        from fastapi.testclient import TestClient
        from backend.app.models.agent import AgentRunState, AgentStep, ToolCall
        from backend.app.routers.runs import _runs

        _runs.clear()
        run = AgentRunState(
            run_id="traj-run-1",
            request_id="req-traj",
            business_id="a0000000-0000-0000-0000-000000000001",
            status="COMPLETED",
            authorization_tier=2,
        )
        run.steps.append(
            AgentStep(step_number=1, agent="request_parser", status="completed")
        )
        run.tool_calls.append(
            ToolCall(
                run_id="traj-run-1",
                step_id="s1",
                tool_name="get_leave_balance",
                arguments={"employee_id": "emp_1"},
                result={"available_days": 6},
                success=True,
                duration_ms=8,
            )
        )
        run.decision = {"decision_type": "approve", "confidence": 0.92}
        run.structured_request = None
        _runs["traj-run-1"] = run

        import asyncio as _asyncio

        async def _seed():
            await patch_db.execute(
                """INSERT INTO agent_approvals
                   (id, request_id, run_id, decision_id, approval_reason,
                    authorization_tier, risk_level, status, created_at,
                    decision_payload)
                   VALUES (?, 'req-traj', 'traj-run-1', 'd-1',
                           'Tier 3 requires human approval', 3,
                           'high', 'pending', '2024-01-01T00:00:00Z', NULL)""",
                ("appr-1",),
            )
            await patch_db.execute(
                """INSERT INTO audit_logs
                   (id, business_id, run_id, actor, action, target_type,
                    target_id, risk_level, authorization_tier, result,
                    metadata, timestamp)
                   VALUES (?, 'a0000000-0000-0000-0000-000000000001',
                           'traj-run-1', 'REVIEWER-001', 'approval.approved',
                           'approval', 'appr-1', 'high', 3, 'approved',
                           '{}', '2024-01-01T00:10:00Z')""",
                ("aud-1",),
            )

        _asyncio.run(_seed())

        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/runs/traj-run-1/trajectory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "traj-run-1"
        assert data["request_id"] == "req-traj"
        assert data["status"] == "COMPLETED"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["agent"] == "request_parser"
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["tool_name"] == "get_leave_balance"
        assert data["authorization_result"]["tier"] == 2
        assert data["approval"] is not None
        assert data["approval"]["status"] == "pending"
        assert data["audit_record"] is not None
        assert data["audit_record"]["action"] == "approval.approved"


class TestOrchestratorRunId:
    @pytest.mark.asyncio
    async def test_injected_run_id_is_honored(self, ctx):
        orch = AgentOrchestrator()
        state = await orch.run(
            request_id="req-fixed",
            raw_input="Take leave tomorrow for vacation",
            ctx=ctx,
            run_id="fixed-run-123",
        )
        assert state.run_id == "fixed-run-123"

        from backend.app.orchestrator.events import event_bus

        types = [e.event_type for e in event_bus.get_history(state.run_id)]
        assert "run.started" in types
        assert "tool.calling" in types
        assert "evidence.assembled" in types


class TestFullRunLifecycle:
    """End-to-end: POST /api/requests → real background orchestrator run
    → live SSE stream consumption → trajectory export (all via the app)."""

    @pytest.mark.asyncio
    async def test_post_stream_trajectory_lifecycle(self, patch_db):
        import json as _json

        from httpx import ASGITransport, AsyncClient

        from backend.app.routers.runs import _runs

        _runs.clear()
        app = _make_test_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # Create the request; the background task runs the orchestrator
            # and stores the finished run in the shared store.
            create = await client.post(
                "/api/requests",
                json={"raw_input": "Sarah wants next Friday off for a family event"},
            )
            assert create.status_code == 200
            payload = create.json()
            run_id = payload["run_id"]

            # Consume the full SSE stream (fresh subscribe replays history
            # since the run already finished; a live subscriber receives the
            # same events in real-time).
            events: list[dict] = []
            expected = ["run.created", "run.completed"]
            async with client.stream(
                "GET", f"/api/runs/{run_id}/stream"
            ) as stream:
                assert stream.status_code == 200
                assert stream.headers.get("content-type", "").startswith(
                    "text/event-stream"
                )
                async for line in stream.aiter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        evt = _json.loads(raw)
                    except ValueError:
                        continue
                    events.append(evt)

            types = [e["event_type"] for e in events]
            assert types[0] == "run.created"
            assert "parsing.completed" in types
            assert "tool.calling" in types
            assert "tool.completed" in types
            assert "evidence.assembled" in types
            assert "decision.completed" in types
            assert "verification.passed" in types
            assert "authorization.evaluated" in types
            # The stream closes right after the terminal event.
            assert types[-1] == "run.completed"
            assert all(t in types for t in expected)

            tool_names = [
                e.get("metadata", {}).get("tool_name")
                for e in events
                if e["event_type"] == "tool.calling"
            ]
            assert tool_names, "expected real tool calls from the stream"
            for name in tool_names:
                assert not name.startswith("mock_"), (
                    f"mock tool leaked into live stream: {name}"
                )
            # Sarah's Friday-off run resolved real context assembly tools.
            assert "get_employee" in tool_names
            assert "get_policy" in tool_names

            evidence_count = 0
            for e in events:
                if e["event_type"] == "evidence.assembled":
                    evidence_count = e.get("metadata", {}).get(
                        "evidence_count", evidence_count
                    )
            assert evidence_count > 0

            # Trajectory export resolves against the finished run.
            traj = await client.get(f"/api/runs/{run_id}/trajectory")
            assert traj.status_code == 200
            body = traj.json()
            assert body["run_id"] == run_id
            assert body["status"] == "COMPLETED"
            assert body["request_id"] == payload["request_id"]
            assert len(body["steps"]) >= 1
            assert len(body["tool_calls"]) >= 1
            assert body["decision"] is not None
            assert body["authorization_result"]["tier"] is not None
            assert body["started_at"] is not None
            assert body["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_pending_run_stream_not_404(self, patch_db):
        """A run that only has a run.created seed still streams (no 404)."""
        from httpx import ASGITransport, AsyncClient

        from backend.app.routers.runs import _runs

        _runs.clear()
        app = _make_test_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            create = await client.post(
                "/api/requests",
                json={"raw_input": "Take leave tomorrow for vacation"},
            )
            run_id = create.json()["run_id"]
            async with client.stream(
                "GET", f"/api/runs/{run_id}/stream"
            ) as stream:
                assert stream.status_code == 200

    @pytest.mark.asyncio
    async def test_approval_gated_run_persists_row(self, ctx, patch_db):
        """Tier-3 sensitive runs wait on human approval: the stream carries
        approval.required (no run.completed) and the backend persists an
        agent_approvals row the trajectory can export."""
        from backend.app.orchestrator.workflow import AgentOrchestrator
        from backend.app.orchestrator.events import event_bus

        orch = AgentOrchestrator()
        state = await orch.run(
            request_id="req-gated",
            raw_input="Theft is suspected. Put Sarah on suspension pending investigation",
            ctx=ctx,
            run_id="gated-run-1",
        )

        assert state.status.value == "WAITING_FOR_APPROVAL"
        assert state.authorization_tier == 3
        assert state.approval_id is not None

        types = [e.event_type for e in event_bus.get_history(state.run_id)]
        assert "approval.required" in types
        assert "run.completed" not in types

        tool_names = [
            e.metadata.get("tool_name")
            for e in event_bus.get_history(state.run_id)
            if e.event_type == "tool.calling"
        ]
        assert "get_attendance" in tool_names
        assert "get_historical_decisions" in tool_names

        rows = patch_db.conn.execute(
            """SELECT id, run_id, status, decision_payload
               FROM agent_approvals"""
        ).fetchall()
        assert len(rows) == 1
        r = rows[0]
        assert r["run_id"] == "gated-run-1"
        assert r["status"] == "pending"
        assert r["decision_payload"] is not None

    @pytest.mark.asyncio
    async def test_stream_replays_history_and_closes(self, ctx, patch_db):
        """A subscriber that connects after the run finished still receives
        the full event history, then the stream closes at run.completed."""
        from backend.app.orchestrator.events import event_bus, OrchestratorEvent
        from backend.app.orchestrator.workflow import AgentOrchestrator
        from backend.app.routers.runs import _runs

        _runs.clear()
        orch = AgentOrchestrator()
        state = await orch.run(
            request_id="req-replay",
            raw_input="Sarah wants next Friday off for a family event",
            ctx=ctx,
            run_id="replay-run-1",
        )
        assert state.status.value == "COMPLETED"

        events = []
        queue = event_bus.subscribe("replay-run-1", last_event_id=None)
        try:
            while True:
                evt = queue.get_nowait()
                events.append(evt.to_dict())
        except asyncio.QueueEmpty:
            pass
        finally:
            event_bus.unsubscribe("replay-run-1", queue)

        types = [e["event_type"] for e in events]
        assert types[0] == "run.started"
        assert "approval.required" not in types
        assert types[-1] == "run.completed"
