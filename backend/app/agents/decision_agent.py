"""OpsPilot — Decision Agent (LLM Agent #2).

This agent receives the validated EvidenceManifest from the Context Assembly
Agent and produces a final decision: approve, reject, or escalate.

The agent MUST ground its decision in the evidence provided. It must NOT
fabricate evidence, ignore missing data, or bypass validation rules.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from backend.app.config import settings
from backend.app.llm.provider import LLMProvider, LLMResponse
from backend.app.models.agent import EvidenceManifest

logger = logging.getLogger(__name__)

# ======================================================================
# System prompt — hardcoded, not configurable at runtime
# ======================================================================
SYSTEM_PROMPT = """\
You are the Decision Agent for OpsPilot.

Your job is to make a safe, policy-compliant decision about a request
based on the evidence provided by the Context Assembly Agent.

Rules you must never break:
1. Every claim you make MUST be grounded in the evidence provided.
   Do not invent facts, policies, or data not in the evidence.
2. If evidence is missing or incomplete, say so. Do not guess.
3. If any evidence item has status "invalid", "partial", or
   "insufficient", you must escalate (do not approve or reject).
4. Never approve a request if the evidence does not fully support it.
5. Never reject a request without clear evidence of a policy violation.
6. When uncertain, escalate to a human. It is always better to escalate
   than to make an incorrect decision.

Decision types:
- approve: Evidence clearly supports the request and it is policy-compliant
- reject: Evidence clearly shows a policy violation or impossibility
- escalate: Evidence is ambiguous, incomplete, or the request requires
  human judgment

Confidence scoring:
- 0.9-1.0: All evidence present, clear policy match, no ambiguity
- 0.7-0.89: Most evidence present, minor gaps that don't affect outcome
- 0.5-0.69: Evidence is partial or ambiguous, human review recommended
- Below 0.5: Must escalate — insufficient evidence for any decision

Return your decision as a JSON object with these fields:
{
  "decision_type": "approve" | "reject" | "escalate",
  "confidence": 0.0 to 1.0,
  "reason": "Clear explanation grounded in evidence",
  "evidence_refs": ["tool_call_id or evidence_id references used"],
  "authorization_tier": 1 | 2 | 3,
  "escalation_reason": "Required if decision_type is escalate"
}
"""


# ======================================================================
# Confidence Inputs — structured inputs for confidence calculation
# ======================================================================
class ConfidenceInputs(BaseModel):
    """Inputs for computing the confidence score of a decision."""

    evidence_completeness: float = Field(
        ..., ge=0.0, le=1.0,
        description="Fraction of expected evidence items actually present"
    )
    policy_match_strength: float = Field(
        ..., ge=0.0, le=1.0,
        description="How well the request matches policy rules (1.0 = exact match)"
    )
    historical_consistency: float = Field(
        ..., ge=0.0, le=1.0,
        description="How consistent this decision is with past decisions for similar requests"
    )
    risk_level: float = Field(
        ..., ge=0.0, le=1.0,
        description="Risk of the request (0.0 = no risk, 1.0 = highest risk)"
    )
    missing_evidence_count: int = Field(
        default=0, ge=0,
        description="Number of evidence items that could not be retrieved"
    )


# ======================================================================
# Decision Output — the LLM's structured response
# ======================================================================
class DecisionOutput(BaseModel):
    """Structured decision output from the LLM."""

    decision_type: Literal["approve", "reject", "escalate"] = Field(
        ..., description="The decision: approve, reject, or escalate"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence score from 0.0 to 1.0"
    )
    reason: str = Field(
        ..., min_length=1,
        description="Clear explanation grounded in evidence"
    )
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="Tool call IDs or evidence IDs used to support the decision"
    )
    authorization_tier: int = Field(
        default=1, ge=1, le=3,
        description="Authorization tier: 1=auto, 2=manager, 3=executive"
    )
    requires_human_approval: bool = Field(
        default=False,
        description="Whether human approval is required",
    )
    escalation_reason: Optional[str] = Field(
        default=None,
        description="Required if decision_type is escalate"
    )

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason must not be empty")
        return v


# ======================================================================
# Confidence calculation
# ======================================================================
def compute_confidence(inputs: ConfidenceInputs) -> float:
    """Compute a weighted confidence score from structured inputs.

    Weights:
    - evidence_completeness: 30%
    - policy_match_strength: 30%
    - historical_consistency: 20%
    - risk_level: 20% (inverted — higher risk = lower confidence)

    Missing evidence penalizes the score further.
    """
    base_score = (
        inputs.evidence_completeness * 0.30
        + inputs.policy_match_strength * 0.30
        + inputs.historical_consistency * 0.20
        + (1.0 - inputs.risk_level) * 0.20
    )

    # Penalty for missing evidence: -0.05 per missing item, max -0.30
    missing_penalty = min(inputs.missing_evidence_count * 0.05, 0.30)

    score = max(0.0, min(1.0, base_score - missing_penalty))
    return round(score, 2)


# ======================================================================
# Decision Agent
# ======================================================================
class DecisionAgent:
    """LLM Agent #2 — makes a policy-compliant decision based on evidence.

    Receives the validated EvidenceManifest and produces a DecisionOutput.
    Validates the LLM response against the evidence before returning.
    """

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self._llm = llm_provider

    def _get_llm(self) -> LLMProvider:
        """Get the LLM provider, lazy-initializing from config."""
        if self._llm is None:
            from backend.app.llm.openai_provider import OpenAIProvider
            from backend.app.llm.anthropic_provider import AnthropicProvider

            if settings.llm_provider == "anthropic":
                self._llm = AnthropicProvider()
            else:
                self._llm = OpenAIProvider()
        return self._llm

    def _build_user_message(
        self,
        manifest: EvidenceManifest,
        structured_request: dict,
    ) -> str:
        """Build the user message for the LLM."""
        evidence_summary = []
        for item in manifest.items:
            evidence_summary.append(
                f"- [{item.evidence_type}] {item.evidence_key}: "
                f"{json.dumps(item.data, default=str)[:200]}"
            )

        msg = (
            f"Request type: {structured_request.get('request_type', 'unknown')}\n"
            f"Employee: {structured_request.get('employee_hint', 'not specified')}\n"
            f"Date: {structured_request.get('date_hint', 'not specified')}\n"
            f"Reason: {structured_request.get('reason', 'not specified')}\n"
            f"Urgency: {structured_request.get('urgency', 'normal')}\n"
            f"\nEvidence manifest status: {manifest.status}\n"
            f"Evidence items ({len(manifest.items)}):\n"
        )

        if evidence_summary:
            msg += "\n".join(evidence_summary)
        else:
            msg += "  (no evidence items)"

        if manifest.missing_data:
            msg += f"\n\nMissing data:\n"
            for md in manifest.missing_data:
                msg += f"  - {md}\n"

        if manifest.warnings:
            msg += f"\nWarnings:\n"
            for w in manifest.warnings:
                msg += f"  - {w}\n"

        msg += (
            "\n\nBased on this evidence, produce your decision. "
            "Return a JSON object with: decision_type, confidence, reason, "
            "evidence_refs, authorization_tier, and escalation_reason if applicable."
        )
        return msg

    def _parse_decision_from_content(self, content: str) -> Optional[DecisionOutput]:
        """Parse the decision JSON from the LLM's text response."""
        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")

            return DecisionOutput(**data)

        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Failed to parse decision from LLM content: %s", exc)
            return None

    def _validate_decision(
        self,
        decision: DecisionOutput,
        manifest: EvidenceManifest,
    ) -> DecisionOutput:
        """Validate the decision against the evidence manifest.

        Checks:
        1. All evidence_refs must reference real evidence items.
        2. Cannot approve if manifest status is not "complete".
        3. Cannot approve or reject without evidence.
        4. Tier 3 auto-approval is overridden to escalate.
        5. Escalate must include escalation_reason.
        """
        valid_evidence_ids = {item.tool_call_id for item in manifest.items}
        valid_evidence_ids.update({item.evidence_id for item in manifest.items})

        # Check for fabricated evidence refs
        for ref in decision.evidence_refs:
            if ref not in valid_evidence_ids:
                logger.warning(
                    "Fabricated evidence_ref detected: %s — overriding to escalate",
                    ref,
                )
                decision.decision_type = "escalate"
                decision.confidence = min(decision.confidence, 0.5)
                decision.escalation_reason = (
                    f"Fabricated evidence reference detected: {ref}"
                )
                return decision

        # Cannot approve if manifest is not complete
        if decision.decision_type == "approve" and manifest.status != "complete":
            logger.warning(
                "Cannot approve with manifest status '%s' — overriding to escalate",
                manifest.status,
            )
            decision.decision_type = "escalate"
            decision.confidence = min(decision.confidence, 0.5)
            decision.escalation_reason = (
                f"Cannot approve: manifest status is '{manifest.status}', "
                f"not 'complete'"
            )
            return decision

        # Cannot approve or reject with zero evidence
        if decision.decision_type in ("approve", "reject") and len(manifest.items) == 0:
            logger.warning(
                "Cannot %s with zero evidence — overriding to escalate",
                decision.decision_type,
            )
            decision.decision_type = "escalate"
            decision.confidence = min(decision.confidence, 0.5)
            decision.escalation_reason = (
                f"Cannot {decision.decision_type}: no evidence items provided"
            )
            return decision

        # Tier 3 auto-approval override
        if decision.decision_type == "approve" and decision.authorization_tier >= 3:
            logger.info(
                "Tier %d auto-approval override — must escalate to human",
                decision.authorization_tier,
            )
            decision.decision_type = "escalate"
            decision.confidence = min(decision.confidence, 0.7)
            decision.escalation_reason = (
                f"Tier {decision.authorization_tier} decisions require "
                f"human approval"
            )
            return decision

        # Escalate must include reason
        if decision.decision_type == "escalate" and not decision.escalation_reason:
            decision.escalation_reason = "Escalated per agent judgment"

        return decision

    async def decide(
        self,
        run_id: str,
        manifest: EvidenceManifest,
        structured_request: dict,
    ) -> DecisionOutput:
        """Run the full decision pipeline.

        1. Send evidence manifest + request to LLM
        2. Parse the decision from the response
        3. Validate against the evidence
        4. Return the validated decision
        """
        llm = self._get_llm()

        user_msg = self._build_user_message(manifest, structured_request)

        # Call LLM
        response: LLMResponse = await llm.generate(
            messages=[{"role": "user", "content": user_msg}],
            system=SYSTEM_PROMPT,
        )

        # Parse decision
        decision = self._parse_decision_from_content(response.content)

        if decision is None:
            # LLM returned unparseable content — escalate
            logger.warning(
                "Decision Agent returned unparseable content — escalating"
            )
            return DecisionOutput(
                decision_type="escalate",
                confidence=0.0,
                reason="Decision Agent returned unparseable response",
                evidence_refs=[],
                authorization_tier=3,
                escalation_reason="LLM response could not be parsed as a valid decision",
            )

        # Validate against evidence
        decision = self._validate_decision(decision, manifest)

        logger.info(
            "Decision Agent produced: %s (confidence=%.2f, tier=%d)",
            decision.decision_type,
            decision.confidence,
            decision.authorization_tier,
        )

        return decision
