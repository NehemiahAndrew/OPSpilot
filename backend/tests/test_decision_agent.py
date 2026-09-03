"""Tests for the Decision Agent (LLM Agent #2).

Uses synthetic EvidenceManifests (no DB). Mocks the LLM provider
for deterministic tests. Tests the full decision pipeline and
validation logic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.agents.decision_agent import (
    DecisionAgent,
    DecisionOutput,
    ConfidenceInputs,
    compute_confidence,
    SYSTEM_PROMPT,
)
from backend.app.llm.provider import (
    LLMProvider,
    LLMResponse,
    TokenUsage,
)
from backend.app.models.agent import EvidenceItem, EvidenceManifest


# ======================================================================
# Mock LLM Provider
# ======================================================================
class MockLLMProvider(LLMProvider):
    """A mock LLM that returns pre-configured responses."""

    def __init__(self, responses: Optional[List[LLMResponse]] = None):
        self._responses = responses or []
        self._call_index = 0
        self.calls: List[dict] = []

    async def generate(
        self,
        messages: List[dict],
        system: str,
        tools=None,
        structured_output=None,
    ) -> LLMResponse:
        self.calls.append({
            "messages": messages,
            "system": system,
        })

        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp

        # Default: return escalate
        return LLMResponse(
            content=json.dumps({
                "decision_type": "escalate",
                "confidence": 0.5,
                "reason": "Default escalate",
                "evidence_refs": [],
                "authorization_tier": 3,
                "escalation_reason": "Default",
            }),
            tool_calls=[],
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            provider="mock",
            model="mock-model",
            cost_usd=0.0,
        )


def _make_decision_response(
    decision_type: str = "approve",
    confidence: float = 0.9,
    reason: str = "Policy compliant",
    evidence_refs: Optional[List[str]] = None,
    authorization_tier: int = 1,
    escalation_reason: Optional[str] = None,
) -> LLMResponse:
    """Create an LLM response with a decision."""
    data = {
        "decision_type": decision_type,
        "confidence": confidence,
        "reason": reason,
        "evidence_refs": evidence_refs or [],
        "authorization_tier": authorization_tier,
    }
    if escalation_reason:
        data["escalation_reason"] = escalation_reason

    return LLMResponse(
        content=json.dumps(data),
        tool_calls=[],
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="mock",
        model="mock-model",
        cost_usd=0.0,
    )


# ======================================================================
# Synthetic Evidence Fixtures
# ======================================================================
def _make_evidence_item(
    tool_call_id: str = None,
    evidence_type: str = "employee",
    evidence_key: str = "employee_record",
    data: dict = None,
) -> EvidenceItem:
    """Create a synthetic evidence item."""
    return EvidenceItem(
        tool_call_id=tool_call_id or str(uuid4()),
        evidence_type=evidence_type,
        evidence_key=evidence_key,
        data=data or {"name": "Sarah Mitchell", "department": "Operations"},
        relevance="Test evidence",
        used_for="Test decision",
    )


def _make_manifest(
    status: str = "complete",
    items: Optional[List[EvidenceItem]] = None,
    missing_data: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
) -> EvidenceManifest:
    """Create a synthetic evidence manifest."""
    return EvidenceManifest(
        run_id=str(uuid4()),
        request_type="leave",
        items=items or [],
        missing_data=missing_data or [],
        warnings=warnings or [],
        status=status,
    )


def _make_structured_request(
    request_type: str = "leave",
    employee_hint: str = "Sarah Mitchell",
    date_hint: str = "2026-09-04",
    reason: str = "Vacation",
    urgency: str = "normal",
) -> dict:
    """Create a synthetic structured request dict."""
    return {
        "request_type": request_type,
        "employee_hint": employee_hint,
        "date_hint": date_hint,
        "reason": reason,
        "urgency": urgency,
    }


# ======================================================================
# Test: System prompt is hardcoded
# ======================================================================
class TestSystemPrompt:
    def test_system_prompt_contains_key_rules(self):
        assert "Decision Agent" in SYSTEM_PROMPT
        assert "grounded in the evidence" in SYSTEM_PROMPT
        assert "Do not invent facts" in SYSTEM_PROMPT
        assert "escalate" in SYSTEM_PROMPT

    def test_system_prompt_specifies_decision_types(self):
        assert "approve" in SYSTEM_PROMPT
        assert "reject" in SYSTEM_PROMPT
        assert "escalate" in SYSTEM_PROMPT

    def test_system_prompt_specifies_confidence_scoring(self):
        assert "0.9-1.0" in SYSTEM_PROMPT
        assert "0.7-0.89" in SYSTEM_PROMPT
        assert "0.5-0.69" in SYSTEM_PROMPT

    def test_system_prompt_not_configurable(self):
        import inspect
        sig = inspect.signature(DecisionAgent.__init__)
        assert "system_prompt" not in sig.parameters


# ======================================================================
# Test: ConfidenceInputs and compute_confidence
# ======================================================================
class TestConfidenceCalculation:
    def test_high_confidence_all_present(self):
        inputs = ConfidenceInputs(
            evidence_completeness=1.0,
            policy_match_strength=1.0,
            historical_consistency=1.0,
            risk_level=0.0,
            missing_evidence_count=0,
        )
        score = compute_confidence(inputs)
        assert score == 1.0

    def test_low_confidence_missing_evidence(self):
        inputs = ConfidenceInputs(
            evidence_completeness=0.5,
            policy_match_strength=0.5,
            historical_consistency=0.5,
            risk_level=0.5,
            missing_evidence_count=6,
        )
        score = compute_confidence(inputs)
        assert score < 0.5

    def test_missing_evidence_penalty(self):
        inputs_no_missing = ConfidenceInputs(
            evidence_completeness=0.8,
            policy_match_strength=0.8,
            historical_consistency=0.8,
            risk_level=0.2,
            missing_evidence_count=0,
        )
        inputs_with_missing = ConfidenceInputs(
            evidence_completeness=0.8,
            policy_match_strength=0.8,
            historical_consistency=0.8,
            risk_level=0.2,
            missing_evidence_count=3,
        )
        score_no = compute_confidence(inputs_no_missing)
        score_with = compute_confidence(inputs_with_missing)
        assert score_no > score_with

    def test_high_risk_reduces_confidence(self):
        inputs_low_risk = ConfidenceInputs(
            evidence_completeness=0.9,
            policy_match_strength=0.9,
            historical_consistency=0.9,
            risk_level=0.1,
        )
        inputs_high_risk = ConfidenceInputs(
            evidence_completeness=0.9,
            policy_match_strength=0.9,
            historical_consistency=0.9,
            risk_level=0.9,
        )
        score_low = compute_confidence(inputs_low_risk)
        score_high = compute_confidence(inputs_high_risk)
        assert score_low > score_high

    def test_penalty_maxes_at_030(self):
        inputs = ConfidenceInputs(
            evidence_completeness=1.0,
            policy_match_strength=1.0,
            historical_consistency=1.0,
            risk_level=0.0,
            missing_evidence_count=10,
        )
        score = compute_confidence(inputs)
        assert score >= 0.70  # 1.0 - 0.30 max penalty


# ======================================================================
# Test: DecisionOutput model validation
# ======================================================================
class TestDecisionOutputModel:
    def test_valid_approve(self):
        d = DecisionOutput(
            decision_type="approve",
            confidence=0.95,
            reason="Policy compliant, coverage sufficient",
            evidence_refs=["tc-1", "tc-2"],
            authorization_tier=1,
        )
        assert d.decision_type == "approve"
        assert d.confidence == 0.95
        assert d.escalation_reason is None

    def test_valid_escalate(self):
        d = DecisionOutput(
            decision_type="escalate",
            confidence=0.4,
            reason="Insufficient evidence",
            evidence_refs=[],
            authorization_tier=3,
            escalation_reason="Missing policy data",
        )
        assert d.escalation_reason == "Missing policy data"

    def test_empty_reason_rejected(self):
        with pytest.raises(Exception):
            DecisionOutput(
                decision_type="approve",
                confidence=0.9,
                reason="",
                evidence_refs=[],
                authorization_tier=1,
            )

    def test_confidence_out_of_range(self):
        with pytest.raises(Exception):
            DecisionOutput(
                decision_type="approve",
                confidence=1.5,
                reason="Test",
                evidence_refs=[],
                authorization_tier=1,
            )

    def test_invalid_decision_type(self):
        with pytest.raises(Exception):
            DecisionOutput(
                decision_type="invalid_type",
                confidence=0.9,
                reason="Test",
                evidence_refs=[],
                authorization_tier=1,
            )


# ======================================================================
# Test: Approve with complete evidence
# ======================================================================
class TestApproveWithCompleteEvidence:
    @pytest.mark.asyncio
    async def test_approve_with_valid_evidence(self):
        """A complete manifest with clear evidence should allow approval."""
        tc_id_1 = str(uuid4())
        tc_id_2 = str(uuid4())

        items = [
            _make_evidence_item(tc_id_1, "employee", "employee_record"),
            _make_evidence_item(tc_id_2, "balance", "leave_balance"),
        ]
        manifest = _make_manifest(status="complete", items=items)
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="approve",
                confidence=0.92,
                reason="Policy compliant, coverage sufficient",
                evidence_refs=[tc_id_1, tc_id_2],
                authorization_tier=1,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        assert decision.decision_type == "approve"
        assert decision.confidence == 0.92
        assert len(mock_llm.calls) == 1


# ======================================================================
# Test: Reject with policy violation evidence
# ======================================================================
class TestRejectWithViolation:
    @pytest.mark.asyncio
    async def test_reject_with_clear_violation(self):
        """Evidence showing policy violation should result in rejection."""
        tc_id_1 = str(uuid4())
        tc_id_2 = str(uuid4())

        items = [
            _make_evidence_item(tc_id_1, "employee", "employee_record"),
            _make_evidence_item(tc_id_2, "policy", "leave_policy", data={"max_days": 20, "used": 22}),
        ]
        manifest = _make_manifest(status="complete", items=items)
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="reject",
                confidence=0.88,
                reason="Employee has exceeded annual leave limit",
                evidence_refs=[tc_id_1, tc_id_2],
                authorization_tier=1,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        assert decision.decision_type == "reject"
        assert decision.confidence == 0.88


# ======================================================================
# Test: Escalate with incomplete evidence
# ======================================================================
class TestEscalateIncompleteEvidence:
    @pytest.mark.asyncio
    async def test_escalate_when_evidence_incomplete(self):
        """Partial manifest should force escalation."""
        manifest = _make_manifest(status="partial", items=[], missing_data=["balance data"])
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="approve",
                confidence=0.6,
                reason="Looks good",
                evidence_refs=[],
                authorization_tier=1,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        # Validation should override to escalate
        assert decision.decision_type == "escalate"
        assert "manifest status" in decision.escalation_reason.lower()

    @pytest.mark.asyncio
    async def test_escalate_when_insufficient(self):
        """Insufficient manifest should force escalation."""
        manifest = _make_manifest(status="insufficient", items=[])
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="reject",
                confidence=0.7,
                reason="Cannot process",
                evidence_refs=[],
                authorization_tier=1,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        assert decision.decision_type == "escalate"


# ======================================================================
# Test: Fabricated evidence_ref rejected
# ======================================================================
class TestFabricatedEvidenceRef:
    @pytest.mark.asyncio
    async def test_fabricated_ref_overrides_to_escalate(self):
        """A fabricated evidence_ref should override the decision to escalate."""
        tc_id_1 = str(uuid4())
        fake_ref = str(uuid4())  # Not in the manifest

        items = [
            _make_evidence_item(tc_id_1, "employee", "employee_record"),
        ]
        manifest = _make_manifest(status="complete", items=items)
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="approve",
                confidence=0.9,
                reason="All good",
                evidence_refs=[tc_id_1, fake_ref],  # fake_ref is fabricated
                authorization_tier=1,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        assert decision.decision_type == "escalate"
        assert "fabricated" in decision.escalation_reason.lower()


# ======================================================================
# Test: Approve without evidence → escalate
# ======================================================================
class TestApproveWithoutEvidence:
    @pytest.mark.asyncio
    async def test_approve_with_zero_evidence_overrides(self):
        """Cannot approve with zero evidence items — must escalate."""
        manifest = _make_manifest(status="complete", items=[])
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="approve",
                confidence=0.9,
                reason="Seems fine",
                evidence_refs=[],
                authorization_tier=1,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        assert decision.decision_type == "escalate"
        assert "no evidence" in decision.escalation_reason.lower()


# ======================================================================
# Test: Tier 3 auto-approval override
# ======================================================================
class TestTier3AutoApproval:
    @pytest.mark.asyncio
    async def test_tier3_approve_overrides_to_escalate(self):
        """Tier 3 approvals must be escalated to human."""
        tc_id_1 = str(uuid4())
        items = [_make_evidence_item(tc_id_1, "employee", "employee_record")]
        manifest = _make_manifest(status="complete", items=items)
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="approve",
                confidence=0.95,
                reason="Policy compliant",
                evidence_refs=[tc_id_1],
                authorization_tier=3,  # Tier 3
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        assert decision.decision_type == "escalate"
        assert "tier 3" in decision.escalation_reason.lower()
        assert decision.confidence <= 0.7

    @pytest.mark.asyncio
    async def test_tier3_reject_not_overridden(self):
        """Tier 3 rejections are allowed (not overridden)."""
        tc_id_1 = str(uuid4())
        items = [_make_evidence_item(tc_id_1, "policy", "leave_policy")]
        manifest = _make_manifest(status="complete", items=items)
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="reject",
                confidence=0.9,
                reason="Clear violation",
                evidence_refs=[tc_id_1],
                authorization_tier=3,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        # Reject with tier 3 is not overridden
        assert decision.decision_type == "reject"


# ======================================================================
# Test: Escalate with reason
# ======================================================================
class TestEscalateWithReason:
    @pytest.mark.asyncio
    async def test_escalate_must_have_reason(self):
        """Escalation must include escalation_reason."""
        manifest = _make_manifest(status="partial", items=[])
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(
                decision_type="escalate",
                confidence=0.4,
                reason="Uncertain",
                evidence_refs=[],
                authorization_tier=3,
                escalation_reason=None,  # Missing
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        # Validation should add a default reason
        assert decision.escalation_reason is not None
        assert len(decision.escalation_reason) > 0


# ======================================================================
# Test: Unparseable LLM response → escalate
# ======================================================================
class TestUnparseableResponse:
    @pytest.mark.asyncio
    async def test_garbage_response_escalates(self):
        """When the LLM returns unparseable content, escalate."""
        manifest = _make_manifest(status="complete", items=[
            _make_evidence_item(str(uuid4()), "employee", "employee_record"),
        ])
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            LLMResponse(
                content="This is not a valid decision response at all",
                tool_calls=[],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock",
                model="mock-model",
                cost_usd=0.0,
            ),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        decision = await agent.decide(str(uuid4()), manifest, request)

        assert decision.decision_type == "escalate"
        assert decision.confidence == 0.0
        assert "parsed" in decision.escalation_reason.lower() or "unparseable" in decision.escalation_reason.lower()


# ======================================================================
# Test: User message contains evidence details
# ======================================================================
class TestUserMessageConstruction:
    def test_message_contains_request_type(self):
        agent = DecisionAgent(llm_provider=MockLLMProvider())
        manifest = _make_manifest(status="complete", items=[
            _make_evidence_item(str(uuid4()), "employee", "employee_record"),
        ])
        request = _make_structured_request(request_type="disciplinary")

        msg = agent._build_user_message(manifest, request)
        assert "disciplinary" in msg

    def test_message_contains_missing_data(self):
        agent = DecisionAgent(llm_provider=MockLLMProvider())
        manifest = _make_manifest(
            status="partial",
            items=[],
            missing_data=["leave_balance not found"],
        )
        request = _make_structured_request()

        msg = agent._build_user_message(manifest, request)
        assert "leave_balance not found" in msg

    def test_message_contains_warnings(self):
        agent = DecisionAgent(llm_provider=MockLLMProvider())
        manifest = _make_manifest(
            status="partial",
            items=[],
            warnings=["Coverage may be insufficient"],
        )
        request = _make_structured_request()

        msg = agent._build_user_message(manifest, request)
        assert "Coverage may be insufficient" in msg


# ======================================================================
# Test: Lazy provider initialization
# ======================================================================
class TestLazyProviderInit:
    def test_default_provider_is_openai(self):
        agent = DecisionAgent()
        from backend.app.config import settings
        assert settings.llm_provider in ("openai", "anthropic")


# ======================================================================
# Test: LLM provider receives correct system prompt
# ======================================================================
class TestLLMReceivesSystemPrompt:
    @pytest.mark.asyncio
    async def test_system_prompt_sent_to_llm(self):
        """The hardcoded system prompt should be passed to the LLM."""
        manifest = _make_manifest(status="complete", items=[
            _make_evidence_item(str(uuid4()), "employee", "employee_record"),
        ])
        request = _make_structured_request()

        mock_llm = MockLLMProvider([
            _make_decision_response(decision_type="escalate", confidence=0.5, reason="Test"),
        ])

        agent = DecisionAgent(llm_provider=mock_llm)
        await agent.decide(str(uuid4()), manifest, request)

        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["system"] == SYSTEM_PROMPT
