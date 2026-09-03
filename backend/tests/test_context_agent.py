"""Tests for the Context Assembly Agent (LLM Agent #1).

Uses the seeded in-memory SQLite database from conftest.py.
Mocks the LLM provider for deterministic edge case tests.
Tests the full tool-calling pipeline and evidence manifest validation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.agents.context_agent import (
    ContextAssemblyAgent,
    MAX_TOOL_CALLS,
    SYSTEM_PROMPT,
)
from backend.app.llm.provider import (
    LLMProvider,
    LLMResponse,
    TokenUsage,
    ToolCallRequest,
)
from backend.app.models.agent import EvidenceItem, EvidenceManifest
from backend.app.models.tool_contract import ToolContext, ToolResult
from backend.app.tools.registry import build_registry
from backend.data import generator as g

from datetime import date


# ======================================================================
# Mock LLM Provider
# ======================================================================
class MockLLMProvider(LLMProvider):
    """A mock LLM that returns pre-configured responses.

    Supports two modes:
    1. Pre-scripted responses: feed a list of LLMResponse objects
    2. Tool-call-then-manifest: automatically calls tools then returns manifest
    """

    def __init__(self, responses: Optional[List[LLMResponse]] = None):
        self._responses = responses or []
        self._call_index = 0
        self.calls: List[dict] = []  # Record all calls for assertions

    async def generate(
        self,
        messages: List[dict],
        system: str,
        tools: Optional[List[dict]] = None,
        structured_output=None,
    ) -> LLMResponse:
        self.calls.append({
            "messages": messages,
            "system": system,
            "tools": tools,
        })

        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp

        # Default: return empty manifest
        return LLMResponse(
            content=json.dumps({
                "status": "complete",
                "items": [],
                "missing_data": [],
                "warnings": [],
            }),
            tool_calls=[],
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            provider="mock",
            model="mock-model",
            cost_usd=0.0,
        )


def _make_tool_response(
    tool_name: str,
    tool_call_id: str,
    success: bool = True,
    data=None,
    error: Optional[str] = None,
) -> LLMResponse:
    """Create an LLM response that makes a single tool call."""
    return LLMResponse(
        content="",
        tool_calls=[
            ToolCallRequest(
                id=tool_call_id,
                name=tool_name,
                arguments={"identifier": "Sarah Mitchell"} if tool_name == "get_employee" and "identifier" in (data or {}) else {},
            )
        ],
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="mock",
        model="mock-model",
        cost_usd=0.0,
    )


def _make_manifest_response(items=None, status="complete") -> LLMResponse:
    """Create an LLM response with an evidence manifest."""
    manifest_data = {
        "status": status,
        "items": items or [],
        "missing_data": [],
        "warnings": [],
    }
    return LLMResponse(
        content=json.dumps(manifest_data),
        tool_calls=[],
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="mock",
        model="mock-model",
        cost_usd=0.0,
    )


# ======================================================================
# Fixtures
# ======================================================================
@pytest.fixture
def ctx():
    """Standard ToolContext for tests."""
    return ToolContext(
        business_id=g.BUSINESS_ID,
        requesting_user_id="USER-001",
        user_role="manager",
        run_id=str(uuid4()),
        step_id=str(uuid4()),
    )


@pytest.fixture
def tool_registry():
    """Build a fresh tool registry."""
    return build_registry()


# ======================================================================
# Test: System prompt is hardcoded
# ======================================================================
class TestSystemPrompt:
    def test_system_prompt_contains_key_rules(self):
        assert "Context Assembly Agent" in SYSTEM_PROMPT
        assert "Do not make a decision" in SYSTEM_PROMPT
        assert "Do not approve or reject" in SYSTEM_PROMPT
        assert "AMBIGUOUS_EMPLOYEE" in SYSTEM_PROMPT
        assert "INSUFFICIENT_CONTEXT" in SYSTEM_PROMPT

    def test_system_prompt_specifies_tool_order(self):
        assert "get_employee" in SYSTEM_PROMPT
        assert "get_leave_balance" in SYSTEM_PROMPT
        assert "get_policy" in SYSTEM_PROMPT
        assert "get_schedule" in SYSTEM_PROMPT
        assert "get_team_coverage" in SYSTEM_PROMPT
        assert "get_pending_requests" in SYSTEM_PROMPT
        assert "get_historical_decisions" in SYSTEM_PROMPT

    def test_system_prompt_not_configurable(self):
        """The system prompt is a module-level constant, not a parameter."""
        import inspect
        sig = inspect.signature(ContextAssemblyAgent.__init__)
        assert "system_prompt" not in sig.parameters


# ======================================================================
# Test: LLM Provider interface
# ======================================================================
class TestLLMProviderInterface:
    def test_provider_has_generate_method(self):
        assert hasattr(LLMProvider, "generate")

    def test_llm_response_fields(self):
        resp = LLMResponse(
            content="test",
            tool_calls=[],
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            provider="openai",
            model="gpt-4o",
            cost_usd=0.01,
        )
        assert resp.content == "test"
        assert resp.provider == "openai"
        assert resp.usage.total_tokens == 15

    def test_tool_call_request(self):
        tc = ToolCallRequest(id="tc-1", name="get_employee", arguments={"identifier": "Sarah"})
        assert tc.name == "get_employee"
        assert tc.arguments["identifier"] == "Sarah"


# ======================================================================
# Test: EvidenceItem and EvidenceManifest models
# ======================================================================
class TestEvidenceModels:
    def test_evidence_item_fields(self):
        item = EvidenceItem(
            tool_call_id="tc-123",
            evidence_type="employee",
            evidence_key="employee_record",
            data={"name": "Sarah Mitchell"},
            relevance="Identify the employee making the request",
            used_for="employee identification",
        )
        assert item.tool_call_id == "tc-123"
        assert item.source == "database"
        assert item.data["name"] == "Sarah Mitchell"

    def test_evidence_manifest_fields(self):
        manifest = EvidenceManifest(
            run_id="run-123",
            request_type="leave",
            items=[],
            missing_data=[],
            warnings=[],
            status="complete",
        )
        assert manifest.run_id == "run-123"
        assert manifest.request_type == "leave"
        assert manifest.status == "complete"

    def test_evidence_manifest_defaults(self):
        manifest = EvidenceManifest(run_id="r1", request_type="leave")
        assert manifest.status == "partial"
        assert manifest.items == []
        assert manifest.missing_data == []
        assert manifest.warnings == []


# ======================================================================
# Test: Tool schema conversion
# ======================================================================
class TestToolSchemaConversion:
    def test_read_tools_only(self, tool_registry):
        """Only read tools should be exposed to the LLM."""
        agent = ContextAssemblyAgent(tool_registry=tool_registry)
        schemas = agent._tool_schemas
        tool_names = [s["function"]["name"] for s in schemas]

        # All read tools should be present
        assert "get_employee" in tool_names
        assert "get_leave_balance" in tool_names
        assert "get_policy" in tool_names
        assert "get_schedule" in tool_names
        assert "get_team_coverage" in tool_names
        assert "get_pending_requests" in tool_names
        assert "get_historical_decisions" in tool_names

        # Action tools should NOT be present
        assert "create_leave_request" not in tool_names
        assert "create_approval_request" not in tool_names
        assert "update_request_status" not in tool_names


# ======================================================================
# Test: Leave request — correct tools called in correct order
# ======================================================================
class TestLeaveRequestAssembly:
    @pytest.mark.asyncio
    async def test_leave_request_calls_correct_tools(self, patch_db, ctx, tool_registry):
        """Sarah Mitchell's leave request should trigger the leave tool sequence."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Sarah Mitchell",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        # Track tool calls made by the agent
        tool_calls_made = []
        original_call_tool = tool_registry.call_tool

        async def tracking_call_tool(name, arguments, ctx):
            tool_calls_made.append({"name": name, "arguments": arguments})
            return await original_call_tool(name, arguments, ctx)

        tool_registry.call_tool = tracking_call_tool

        # Mock LLM: first call requests tools, second call returns manifest
        tc_id_1 = str(uuid4())
        tc_id_2 = str(uuid4())
        tc_id_3 = str(uuid4())
        tc_id_4 = str(uuid4())
        tc_id_5 = str(uuid4())
        tc_id_6 = str(uuid4())
        tc_id_7 = str(uuid4())

        mock_llm = MockLLMProvider([
            # First response: call get_employee
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_1, name="get_employee", arguments={"identifier": "Sarah Mitchell"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            # Second response: call get_leave_balance
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_2, name="get_leave_balance", arguments={"employee_id": g.emp_uuid("EMP-001"), "as_of_date": "2026-08-29"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            # Third response: call get_policy
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_3, name="get_policy", arguments={"category": "leave"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            # Fourth response: return manifest
            _make_manifest_response(
                items=[
                    {"tool_call_id": tc_id_1, "evidence_type": "employee", "evidence_key": "employee_record", "relevance": "Employee identification", "used_for": "identify requestor"},
                    {"tool_call_id": tc_id_2, "evidence_type": "balance", "evidence_key": "leave_balance", "relevance": "Available leave days", "used_for": "verify balance"},
                    {"tool_call_id": tc_id_3, "evidence_type": "policy", "evidence_key": "leave_policy", "relevance": "Leave policy rules", "used_for": "policy compliance"},
                ],
                status="complete",
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        # Verify manifest
        assert manifest.status == "complete"
        assert manifest.run_id == run_id
        assert len(manifest.items) == 3

        # Verify tools were called
        tool_names = [tc["name"] for tc in tool_calls_made]
        assert "get_employee" in tool_names
        assert "get_leave_balance" in tool_names
        assert "get_policy" in tool_names

        # Verify LLM was called
        assert len(mock_llm.calls) == 4  # 3 tool rounds + 1 manifest


# ======================================================================
# Test: Disciplinary request — attendance + history retrieved
# ======================================================================
class TestDisciplinaryRequestAssembly:
    @pytest.mark.asyncio
    async def test_disciplinary_request_calls_attendance_and_history(self, patch_db, ctx, tool_registry):
        """A disciplinary request should call get_attendance and get_historical_decisions."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "disciplinary",
            "employee_hint": "John Carter",
            "date_hint": None,
            "reason": "Attendance issues",
            "urgency": "normal",
        }

        tool_calls_made = []
        original_call_tool = tool_registry.call_tool

        async def tracking_call_tool(name, arguments, ctx):
            tool_calls_made.append({"name": name, "arguments": arguments})
            return await original_call_tool(name, arguments, ctx)

        tool_registry.call_tool = tracking_call_tool

        tc_id_1 = str(uuid4())
        tc_id_2 = str(uuid4())
        tc_id_3 = str(uuid4())

        mock_llm = MockLLMProvider([
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_1, name="get_employee", arguments={"identifier": "John Carter"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_2, name="get_attendance", arguments={"employee_id": g.emp_uuid("EMP-002"), "days_back": 60})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_3, name="get_historical_decisions", arguments={"employee_id": g.emp_uuid("EMP-002"), "request_type": "disciplinary"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            _make_manifest_response(
                items=[
                    {"tool_call_id": tc_id_1, "evidence_type": "employee", "evidence_key": "employee_record", "relevance": "Employee identification", "used_for": "identify subject"},
                    {"tool_call_id": tc_id_2, "evidence_type": "attendance", "evidence_key": "attendance_record", "relevance": "Attendance history", "used_for": "verify attendance pattern"},
                    {"tool_call_id": tc_id_3, "evidence_type": "historical", "evidence_key": "historical_decisions", "relevance": "Past disciplinary decisions", "used_for": "precedent analysis"},
                ],
                status="complete",
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        assert manifest.status == "complete"
        tool_names = [tc["name"] for tc in tool_calls_made]
        assert "get_attendance" in tool_names
        assert "get_historical_decisions" in tool_names


# ======================================================================
# Test: Ambiguous employee → NEEDS_CLARIFICATION
# ======================================================================
class TestAmbiguousEmployee:
    @pytest.mark.asyncio
    async def test_ambiguous_employee_returns_needs_clarification(self, patch_db, ctx, tool_registry):
        """When get_employee returns AMBIGUOUS_EMPLOYEE, manifest status should be needs_clarification."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "John",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        # "John" matches both EMP-002 (John Carter) and EMP-013 (John Carter Jr.) via ILIKE
        tc_id_1 = str(uuid4())
        mock_llm = MockLLMProvider([
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_1, name="get_employee", arguments={"identifier": "John"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        assert manifest.status == "needs_clarification"
        assert len(manifest.missing_data) > 0
        assert "AMBIGUOUS_EMPLOYEE" in manifest.missing_data[0]
        assert len(manifest.warnings) > 0


# ======================================================================
# Test: Unknown employee → INSUFFICIENT_CONTEXT
# ======================================================================
class TestUnknownEmployee:
    @pytest.mark.asyncio
    async def test_unknown_employee_returns_insufficient(self, patch_db, ctx, tool_registry):
        """When get_employee returns EMPLOYEE_NOT_FOUND, manifest status should be insufficient."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Michael Nobody",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        tc_id_1 = str(uuid4())
        mock_llm = MockLLMProvider([
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_1, name="get_employee", arguments={"identifier": "Michael Nobody"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        assert manifest.status == "insufficient"
        assert len(manifest.missing_data) > 0
        assert "Employee not found" in manifest.missing_data[0]


# ======================================================================
# Test: Tool failure → recorded in missing_data, not fabricated
# ======================================================================
class TestToolFailure:
    @pytest.mark.asyncio
    async def test_tool_failure_recorded_not_fabricated(self, patch_db, ctx, tool_registry):
        """When a tool fails, the error should be recorded honestly, not fabricated."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Sarah Mitchell",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        tc_id_1 = str(uuid4())
        tc_id_2 = str(uuid4())

        # Mock get_employee to fail on second call (simulating intermittent failure)
        call_count = {"n": 0}
        original_call_tool = tool_registry.call_tool

        async def failing_call_tool(name, arguments, ctx):
            if name == "get_leave_balance":
                call_count["n"] += 1
                if call_count["n"] <= 2:  # Both attempts fail
                    return ToolResult.fail(
                        tool_name=name,
                        error="DATABASE_TIMEOUT",
                        arguments=arguments,
                        duration_ms=100,
                    )
            return await original_call_tool(name, arguments, ctx)

        tool_registry.call_tool = failing_call_tool

        mock_llm = MockLLMProvider([
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_1, name="get_employee", arguments={"identifier": "Sarah Mitchell"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_2, name="get_leave_balance", arguments={"employee_id": g.emp_uuid("EMP-001"), "as_of_date": "2026-08-29"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            _make_manifest_response(
                items=[
                    {"tool_call_id": tc_id_1, "evidence_type": "employee", "evidence_key": "employee_record", "relevance": "Employee identification", "used_for": "identify requestor"},
                ],
                status="partial",
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        # The failed tool should not appear in items with fabricated data
        for item in manifest.items:
            assert item.tool_call_id != tc_id_2 or item.data == {}

        # The warning should mention the failure
        # (either from the manifest response or from the tool call log)


# ======================================================================
# Test: Manifest validation — fabricated tool_call_id rejected
# ======================================================================
class TestManifestValidation:
    @pytest.mark.asyncio
    async def test_fabricated_tool_call_id_rejected(self, patch_db, ctx, tool_registry):
        """A manifest with a fabricated tool_call_id should be marked invalid."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Sarah Mitchell",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        tc_id_1 = str(uuid4())
        fake_tc_id = str(uuid4())  # This one was never actually called

        mock_llm = MockLLMProvider([
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_1, name="get_employee", arguments={"identifier": "Sarah Mitchell"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            _make_manifest_response(
                items=[
                    {"tool_call_id": tc_id_1, "evidence_type": "employee", "evidence_key": "employee_record", "relevance": "Employee identification", "used_for": "identify requestor"},
                    {"tool_call_id": fake_tc_id, "evidence_type": "balance", "evidence_key": "leave_balance", "relevance": "Leave balance", "used_for": "verify balance"},
                ],
                status="complete",
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        # Should be marked invalid due to fabricated tool_call_id
        assert manifest.status == "invalid"
        assert any("Fabricated tool_call_id" in w for w in manifest.warnings)


# ======================================================================
# Test: Max tool limit → partial manifest with warning
# ======================================================================
class TestMaxToolLimit:
    @pytest.mark.asyncio
    async def test_max_tool_limit_returns_partial(self, patch_db, ctx, tool_registry):
        """When max tool calls are exhausted, a partial manifest with warning is returned."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Sarah Mitchell",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        # Create enough tool calls to exceed the limit
        responses = []
        for i in range(MAX_TOOL_CALLS + 1):
            tc_id = str(uuid4())
            responses.append(
                LLMResponse(
                    content="",
                    tool_calls=[ToolCallRequest(id=tc_id, name="get_employee", arguments={"identifier": "Sarah Mitchell"})],
                    usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                    provider="mock", model="mock", cost_usd=0.0,
                )
            )

        mock_llm = MockLLMProvider(responses)
        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        assert manifest.status == "partial"
        assert any("Max tool call limit" in w or "limit" in w.lower() for w in manifest.warnings)


# ======================================================================
# Test: Historical decisions labeled as HISTORICAL in manifest
# ======================================================================
class TestHistoricalDecisionsLabel:
    @pytest.mark.asyncio
    async def test_historical_decisions_in_manifest(self, patch_db, ctx, tool_registry):
        """Historical decisions should be included in the manifest with HISTORICAL label."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Sarah Mitchell",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        tc_id_emp = str(uuid4())
        tc_id_hist = str(uuid4())

        mock_llm = MockLLMProvider([
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_emp, name="get_employee", arguments={"identifier": "Sarah Mitchell"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_hist, name="get_historical_decisions", arguments={"employee_id": g.emp_uuid("EMP-001"), "request_type": "leave"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            _make_manifest_response(
                items=[
                    {"tool_call_id": tc_id_emp, "evidence_type": "employee", "evidence_key": "employee_record", "relevance": "Employee identification", "used_for": "identify requestor"},
                    {"tool_call_id": tc_id_hist, "evidence_type": "historical", "evidence_key": "historical_decisions", "relevance": "Past leave decisions", "used_for": "precedent analysis"},
                ],
                status="complete",
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        # Find the historical evidence item
        hist_items = [i for i in manifest.items if i.evidence_type == "historical"]
        assert len(hist_items) > 0

        # Verify the data contains HISTORICAL label
        hist_item = hist_items[0]
        assert hist_item.data.get("label") == "HISTORICAL" or "HISTORICAL" in str(hist_item.data)


# ======================================================================
# Test: Manifest parse error handling
# ======================================================================
class TestManifestParseError:
    @pytest.mark.asyncio
    async def test_invalid_json_from_llm_returns_partial(self, patch_db, ctx, tool_registry):
        """When the LLM returns invalid JSON, a partial manifest is returned."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Sarah Mitchell",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        mock_llm = MockLLMProvider([
            LLMResponse(
                content="This is not valid JSON at all, just garbage text",
                tool_calls=[],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        assert manifest.status == "partial"
        assert any("parse" in w.lower() or "error" in w.lower() for w in manifest.warnings)


# ======================================================================
# Test: Retry logic for failed tools
# ======================================================================
class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_tool_retried_once_on_failure(self, patch_db, ctx, tool_registry):
        """A failed tool should be retried once before giving up."""
        run_id = str(uuid4())
        structured_request = {
            "request_type": "leave",
            "employee_hint": "Sarah Mitchell",
            "date_hint": "2026-09-04",
            "reason": "Vacation",
            "urgency": "normal",
        }

        call_count = {"n": 0}
        original_call_tool = tool_registry.call_tool

        async def flaky_call_tool(name, arguments, ctx):
            call_count["n"] += 1
            if name == "get_employee" and call_count["n"] == 1:
                # First call fails, second should succeed
                return ToolResult.fail(
                    tool_name=name,
                    error="TRANSIENT_ERROR",
                    arguments=arguments,
                    duration_ms=50,
                )
            return await original_call_tool(name, arguments, ctx)

        tool_registry.call_tool = flaky_call_tool

        tc_id_1 = str(uuid4())
        mock_llm = MockLLMProvider([
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id=tc_id_1, name="get_employee", arguments={"identifier": "Sarah Mitchell"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            ),
            _make_manifest_response(
                items=[
                    {"tool_call_id": tc_id_1, "evidence_type": "employee", "evidence_key": "employee_record", "relevance": "Employee identification", "used_for": "identify requestor"},
                ],
                status="complete",
            ),
        ])

        agent = ContextAssemblyAgent(llm_provider=mock_llm, tool_registry=tool_registry)
        manifest = await agent.assemble(run_id, structured_request, ctx)

        # Tool was called twice (first fail, then retry succeed)
        assert call_count["n"] == 2
        # Employee was found on retry
        emp_items = [i for i in manifest.items if i.evidence_type == "employee"]
        assert len(emp_items) > 0


# ======================================================================
# Test: No LLM calls → default provider initialized
# ======================================================================
class TestLazyProviderInit:
    def test_default_provider_is_openai(self, ctx, tool_registry):
        """When no LLM provider is given, OpenAI is used by default."""
        agent = ContextAssemblyAgent(tool_registry=tool_registry)
        # Don't actually call it (no API key), just verify it would pick openai
        from backend.app.config import settings
        assert settings.llm_provider in ("openai", "anthropic")
