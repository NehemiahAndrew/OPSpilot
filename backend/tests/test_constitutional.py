"""Tests for the Constitutional Checker and Authorization Gate.

All tests are fully deterministic — no DB, no LLM, no fixtures needed.
Every check is tested independently, plus end-to-end integration tests.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.app.models.agent import (
    EvidenceManifest,
    EvidenceItem,
)
from backend.app.agents.decision_agent import DecisionOutput
from backend.app.checkers.constitutional import (
    CheckResult,
    ConstitutionalCheckResult,
    check_employee_exists,
    check_evidence_refs_valid,
    check_policy_exists,
    check_balance_arithmetic_correct,
    check_notice_period_satisfied,
    check_coverage_not_violated,
    check_no_duplicate_request,
    check_authorization_tier_matches_action,
    check_consequential_requires_approval,
    check_evidence_not_stale,
    run_constitutional_checks,
    TIER_ACTION_MAP,
)
from backend.app.checkers.authorization import (
    AuthorizationResult,
    evaluate,
)


# ======================================================================
# Helpers
# ======================================================================
def _make_decision(
    decision_type: str = "approve",
    confidence: float = 0.9,
    reason: str = "Policy compliant",
    evidence_refs: list = None,
    authorization_tier: int = 1,
    requires_human_approval: bool = False,
) -> DecisionOutput:
    return DecisionOutput(
        decision_type=decision_type,
        confidence=confidence,
        reason=reason,
        evidence_refs=evidence_refs or [],
        authorization_tier=authorization_tier,
    )


def _make_evidence_item(
    tool_call_id: str = None,
    evidence_type: str = "employee",
    evidence_key: str = "employee_record",
    data: dict = None,
    retrieved_at: datetime = None,
) -> EvidenceItem:
    return EvidenceItem(
        tool_call_id=tool_call_id or str(uuid4()),
        evidence_type=evidence_type,
        evidence_key=evidence_key,
        data=data or {"status": "active"},
        relevance="Test evidence",
        used_for="Test decision",
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
    )


def _make_manifest(
    items: list = None,
    status: str = "complete",
) -> EvidenceManifest:
    return EvidenceManifest(
        run_id=str(uuid4()),
        request_type="leave",
        items=items or [],
        missing_data=[],
        warnings=[],
        status=status,
    )


def _make_full_manifest() -> EvidenceManifest:
    """Create a manifest with all typical evidence types."""
    tc_emp = str(uuid4())
    tc_policy = str(uuid4())
    tc_balance = str(uuid4())
    tc_coverage = str(uuid4())
    tc_pending = str(uuid4())
    return _make_manifest(
        items=[
            _make_evidence_item(tc_emp, "employee", "employee_record",
                                {"status": "active", "name": "Sarah Mitchell"}),
            _make_evidence_item(tc_policy, "policy", "leave_policy",
                                {"rules": {"standard_notice_days": 3}}),
            _make_evidence_item(tc_balance, "balance", "leave_balance",
                                {"available": 20, "remaining_days": 20}),
            _make_evidence_item(tc_coverage, "coverage", "team_coverage",
                                {"is_coverage_sufficient": True}),
            _make_evidence_item(tc_pending, "pending", "pending_requests",
                                {"requests": []}),
        ],
        status="complete",
    )


# ======================================================================
# CHECK-001: employee_exists
# ======================================================================
class TestCheckEmployeeExists:
    def test_employee_record_exists_and_active(self):
        manifest = _make_full_manifest()
        result = check_employee_exists(manifest)
        assert result.passed is True
        assert result.severity == "info"

    def test_no_employee_record(self):
        manifest = _make_manifest()
        result = check_employee_exists(manifest)
        assert result.passed is False
        assert result.severity == "error"
        assert "employee_record" in result.detail.lower()

    def test_employee_record_not_active(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_key="employee_record",
                data={"status": "inactive"},
            )]
        )
        result = check_employee_exists(manifest)
        assert result.passed is False
        assert result.severity == "error"


# ======================================================================
# CHECK-002: evidence_refs_valid
# ======================================================================
class TestCheckEvidenceRefsValid:
    def test_all_refs_valid(self):
        manifest = _make_full_manifest()
        tc_ids = [i.tool_call_id for i in manifest.items]
        decision = _make_decision(evidence_refs=tc_ids)
        result = check_evidence_refs_valid(decision, manifest)
        assert result.passed is True

    def test_fabricated_ref_detected(self):
        manifest = _make_full_manifest()
        fake_ref = str(uuid4())
        decision = _make_decision(evidence_refs=[fake_ref])
        result = check_evidence_refs_valid(decision, manifest)
        assert result.passed is False
        assert result.severity == "error"
        assert "fabricated" in result.detail.lower()

    def test_mixed_valid_and_fabricated(self):
        manifest = _make_full_manifest()
        real_ref = manifest.items[0].tool_call_id
        fake_ref = str(uuid4())
        decision = _make_decision(evidence_refs=[real_ref, fake_ref])
        result = check_evidence_refs_valid(decision, manifest)
        assert result.passed is False
        assert result.severity == "error"

    def test_empty_refs(self):
        manifest = _make_full_manifest()
        decision = _make_decision(evidence_refs=[])
        result = check_evidence_refs_valid(decision, manifest)
        assert result.passed is True


# ======================================================================
# CHECK-003: policy_exists
# ======================================================================
class TestCheckPolicyExists:
    def test_policy_exists(self):
        manifest = _make_full_manifest()
        decision = _make_decision(
            decision_type="approve",
            evidence_refs=[i.tool_call_id for i in manifest.items],
        )
        result = check_policy_exists(decision, manifest)
        assert result.passed is True
        assert result.severity == "info"

    def test_no_policy_in_decision(self):
        manifest = _make_full_manifest()
        decision = _make_decision(
            decision_type="approve",
            evidence_refs=[],
        )
        result = check_policy_exists(decision, manifest)
        assert result.passed is True

    def test_no_policy_evidence(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_key="employee_record", evidence_type="employee",
            )]
        )
        decision = _make_decision(decision_type="approve")
        result = check_policy_exists(decision, manifest)
        assert result.passed is False
        assert result.severity == "error"

    def test_no_policy_evidence_for_escalate(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_key="employee_record", evidence_type="employee",
            )]
        )
        decision = _make_decision(decision_type="escalate")
        result = check_policy_exists(decision, manifest)
        assert result.passed is True


# ======================================================================
# CHECK-004: balance_arithmetic_correct
# ======================================================================
class TestCheckBalanceArithmeticCorrect:
    def test_balance_sufficient(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="approve")
        result = check_balance_arithmetic_correct(decision, manifest, 5)
        assert result.passed is True

    def test_balance_insufficient(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="approve")
        result = check_balance_arithmetic_correct(decision, manifest, 25)
        assert result.passed is False
        assert result.severity == "error"
        assert "arithmetic" in result.detail.lower()

    def test_not_approve_skipped(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="reject")
        result = check_balance_arithmetic_correct(decision, manifest, 5)
        assert result.passed is True

    def test_no_balance_evidence(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_key="employee_record", evidence_type="employee",
            )]
        )
        decision = _make_decision(decision_type="approve")
        result = check_balance_arithmetic_correct(decision, manifest, 5)
        assert result.passed is False
        assert result.severity == "error"

    def test_no_requested_days(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="approve")
        result = check_balance_arithmetic_correct(decision, manifest, 0)
        assert result.passed is True


# ======================================================================
# CHECK-005: notice_period_satisfied
# ======================================================================
class TestCheckNoticePeriodSatisfied:
    def test_notice_satisfied(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        decision = _make_decision(decision_type="approve")
        result = check_notice_period_satisfied(decision, manifest, future_date)
        assert result.passed is True

    def test_notice_violated(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        decision = _make_decision(decision_type="approve")
        result = check_notice_period_satisfied(decision, manifest, future_date)
        assert result.passed is False
        assert result.severity == "error"
        assert "notice" in result.detail.lower()

    def test_not_approve_skipped(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        decision = _make_decision(decision_type="reject")
        result = check_notice_period_satisfied(decision, manifest, future_date)
        assert result.passed is True

    def test_no_policy(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_key="employee_record", evidence_type="employee",
            )]
        )
        decision = _make_decision(decision_type="approve")
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        result = check_notice_period_satisfied(decision, manifest, future_date)
        assert result.passed is False
        assert result.severity == "error"


# ======================================================================
# CHECK-006: coverage_not_violated
# ======================================================================
class TestCheckCoverageNotViolated:
    def test_coverage_sufficient(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="approve")
        result = check_coverage_not_violated(decision, manifest)
        assert result.passed is True

    def test_coverage_insufficient_warning(self):
        manifest = _make_manifest(
            items=[
                _make_evidence_item(
                    evidence_type="coverage", evidence_key="team_coverage",
                    data={"is_coverage_sufficient": False},
                ),
                _make_evidence_item(
                    evidence_key="employee_record", evidence_type="employee",
                    data={"status": "active"},
                ),
            ],
        )
        decision = _make_decision(decision_type="approve")
        result = check_coverage_not_violated(decision, manifest)
        assert result.passed is False
        assert result.severity == "warning"

    def test_only_scheduled_employee_violation(self):
        manifest = _make_manifest(
            items=[
                _make_evidence_item(
                    evidence_type="coverage", evidence_key="team_coverage",
                    data={"is_coverage_sufficient": True, "only_scheduled_employee": True},
                ),
                _make_evidence_item(
                    evidence_key="employee_record", evidence_type="employee",
                    data={"status": "active"},
                ),
            ],
        )
        decision = _make_decision(decision_type="approve")
        result = check_coverage_not_violated(decision, manifest)
        assert result.passed is False
        assert result.severity == "error"

    def test_not_approve_skipped(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="reject")
        result = check_coverage_not_violated(decision, manifest)
        assert result.passed is True

    def test_no_coverage_evidence(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_key="employee_record", evidence_type="employee",
            )]
        )
        decision = _make_decision(decision_type="approve")
        result = check_coverage_not_violated(decision, manifest)
        assert result.passed is False
        assert result.severity == "warning"


# ======================================================================
# CHECK-007: no_duplicate_request
# ======================================================================
class TestCheckNoDuplicateRequest:
    def test_no_pending_requests(self):
        manifest = _make_full_manifest()
        decision = _make_decision()
        result = check_no_duplicate_request(decision, manifest)
        assert result.passed is True

    def test_duplicate_pending_found(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_type="pending", evidence_key="pending_requests",
                data={"requests": [{"request_id": "REQ-001", "status": "pending"}]},
            )],
        )
        decision = _make_decision()
        result = check_no_duplicate_request(decision, manifest)
        assert result.passed is False
        assert result.severity == "error"
        assert "duplicate" in result.detail.lower()

    def test_pending_requests_all_completed(self):
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_type="pending", evidence_key="pending_requests",
                data={"requests": [{"request_id": "REQ-001", "status": "approved"}]},
            )],
        )
        decision = _make_decision()
        result = check_no_duplicate_request(decision, manifest)
        assert result.passed is True


# ======================================================================
# CHECK-008: authorization_tier_matches_action
# ======================================================================
class TestCheckAuthorizationTierMatchesAction:
    def test_termination_tier3(self):
        decision = _make_decision(reason="termination: employee misconduct", authorization_tier=3)
        result = check_authorization_tier_matches_action(decision)
        assert result.passed is True

    def test_termination_tier1_mismatch(self):
        decision = _make_decision(reason="termination", authorization_tier=1)
        result = check_authorization_tier_matches_action(decision)
        assert result.passed is False
        assert result.severity == "error"
        assert "tier" in result.detail.lower()

    def test_suspension_tier3(self):
        decision = _make_decision(reason="suspension", authorization_tier=3)
        result = check_authorization_tier_matches_action(decision)
        assert result.passed is True

    def test_suspension_tier2_mismatch(self):
        decision = _make_decision(reason="suspension", authorization_tier=2)
        result = check_authorization_tier_matches_action(decision)
        assert result.passed is False

    def test_create_leave_tier2(self):
        decision = _make_decision(reason="create_leave_request", authorization_tier=2)
        result = check_authorization_tier_matches_action(decision)
        assert result.passed is True

    def test_information_only_tier1(self):
        decision = _make_decision(reason="information_only", authorization_tier=1)
        result = check_authorization_tier_matches_action(decision)
        assert result.passed is True

    def test_unmapped_action(self):
        decision = _make_decision(reason="general inquiry", authorization_tier=1)
        result = check_authorization_tier_matches_action(decision)
        assert result.passed is True

    def test_tier_action_map_content(self):
        assert TIER_ACTION_MAP["termination"] == 3
        assert TIER_ACTION_MAP["suspension"] == 3
        assert TIER_ACTION_MAP["disciplinary_action"] == 3
        assert TIER_ACTION_MAP["create_leave_request"] == 2
        assert TIER_ACTION_MAP["information_only"] == 1


# ======================================================================
# CHECK-009: consequential_requires_approval
# ======================================================================
class TestCheckConsequentialRequiresApproval:
    def test_tier3_with_approval(self):
        decision = _make_decision(authorization_tier=3)
        with patch.object(decision, 'requires_human_approval', True):
            result = check_consequential_requires_approval(decision)
        assert result.passed is True

    def test_tier3_without_approval_violation(self):
        decision = _make_decision(authorization_tier=3)
        with patch.object(decision, 'requires_human_approval', False):
            result = check_consequential_requires_approval(decision)
        assert result.passed is False
        assert result.severity == "error"
        assert "override" in result.detail.lower()

    def test_tier1_not_checked(self):
        decision = _make_decision(authorization_tier=1)
        result = check_consequential_requires_approval(decision)
        assert result.passed is True

    def test_tier2_not_checked(self):
        decision = _make_decision(authorization_tier=2)
        result = check_consequential_requires_approval(decision)
        assert result.passed is True


# ======================================================================
# CHECK-010: evidence_not_stale
# ======================================================================
class TestCheckEvidenceNotStale:
    def test_fresh_evidence(self):
        manifest = _make_full_manifest()
        result = check_evidence_not_stale(manifest)
        assert result.passed is True

    def test_stale_evidence_warning(self):
        old_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        manifest = _make_manifest(
            items=[_make_evidence_item(
                evidence_key="employee_record", evidence_type="employee",
                data={"status": "active"},
                retrieved_at=old_time,
            )],
        )
        result = check_evidence_not_stale(manifest)
        assert result.passed is False
        assert result.severity == "warning"
        assert "10 minutes" in result.detail or "stale" in result.detail.lower()

    def test_multiple_stale_items(self):
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        manifest = _make_manifest(
            items=[
                _make_evidence_item(
                    evidence_key="employee_record", evidence_type="employee",
                    data={"status": "active"}, retrieved_at=old_time,
                ),
                _make_evidence_item(
                    evidence_type="balance", evidence_key="leave_balance",
                    data={"available": 20}, retrieved_at=old_time,
                ),
            ],
        )
        result = check_evidence_not_stale(manifest)
        assert result.passed is False
        assert result.severity == "warning"


# ======================================================================
# Full constitutional checker integration
# ======================================================================
class TestRunConstitutionalChecks:
    def test_valid_decision_passes(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        decision = _make_decision(
            decision_type="approve",
            evidence_refs=[i.tool_call_id for i in manifest.items],
        )
        result = run_constitutional_checks(
            decision, manifest, requested_days=5, requested_date=future_date,
        )
        assert result.passed is True
        assert len(result.violations) == 0
        assert len(result.all_checks) == 10

    def test_fabricated_evidence_ref_violation(self):
        manifest = _make_full_manifest()
        fake_ref = str(uuid4())
        decision = _make_decision(evidence_refs=[fake_ref])
        result = run_constitutional_checks(decision, manifest)
        assert result.passed is False
        violation = [v for v in result.violations if v.check_name == "CHECK-002"]
        assert len(violation) == 1

    def test_balance_too_low_violation(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="approve")
        result = run_constitutional_checks(decision, manifest, requested_days=25)
        assert result.passed is False
        violation = [v for v in result.violations if v.check_name == "CHECK-004"]
        assert len(violation) == 1

    def test_notice_violation(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        decision = _make_decision(decision_type="approve")
        result = run_constitutional_checks(decision, manifest, requested_days=5, requested_date=future_date)
        assert result.passed is False
        violation = [v for v in result.violations if v.check_name == "CHECK-005"]
        assert len(violation) == 1

    def test_only_scheduled_employee_violation(self):
        manifest = _make_manifest(
            items=[
                _make_evidence_item(
                    evidence_type="coverage", evidence_key="team_coverage",
                    data={"is_coverage_sufficient": True, "only_scheduled_employee": True},
                ),
                _make_evidence_item(
                    evidence_key="employee_record", evidence_type="employee",
                    data={"status": "active"},
                ),
            ],
        )
        decision = _make_decision(decision_type="approve")
        result = run_constitutional_checks(decision, manifest)
        assert result.passed is False
        violation = [v for v in result.violations if v.check_name == "CHECK-006"]
        assert len(violation) == 1

    def test_termination_without_tier3_violation(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        decision = _make_decision(
            reason="termination", authorization_tier=1,
            evidence_refs=[i.tool_call_id for i in manifest.items],
        )
        result = run_constitutional_checks(
            decision, manifest, requested_date=future_date,
        )
        assert result.passed is False
        violation = [v for v in result.violations if v.check_name == "CHECK-008"]
        assert len(violation) == 1

    def test_tier3_without_requires_human_approval(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        decision = _make_decision(
            authorization_tier=3,
            evidence_refs=[i.tool_call_id for i in manifest.items],
        )
        with patch.object(decision, 'requires_human_approval', False):
            result = run_constitutional_checks(
                decision, manifest, requested_date=future_date,
            )
        assert result.passed is False
        violation = [v for v in result.violations if v.check_name == "CHECK-009"]
        assert len(violation) == 1


# ======================================================================
# Authorization Gate Tests
# ======================================================================
class TestAuthorizationGate:
    def test_constitutional_failure_blocks(self):
        manifest = _make_full_manifest()
        decision = _make_decision(decision_type="approve", authorization_tier=2)
        fake_ref = str(uuid4())
        decision.evidence_refs = [fake_ref]
        constitutional_result = run_constitutional_checks(decision, manifest)
        assert not constitutional_result.passed

        auth_result = evaluate(decision, constitutional_result)
        assert auth_result.permitted is False
        assert auth_result.requires_human_approval is True
        assert auth_result.block_reason is not None
        assert "Constitutional check failed" in auth_result.block_reason

    def test_tier3_always_blocked(self):
        manifest = _make_full_manifest()
        decision = _make_decision(
            decision_type="approve", evidence_refs=[],
            authorization_tier=3,
        )
        result = run_constitutional_checks(decision, manifest)
        auth_result = evaluate(decision, result)
        assert auth_result.permitted is False
        assert auth_result.requires_human_approval is True
        assert auth_result.tier == 3
        assert auth_result.block_reason is not None
        assert "Tier 3" in auth_result.block_reason

    def test_tier2_passing_all_checks_permitted(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        decision = _make_decision(
            decision_type="approve", authorization_tier=2,
            evidence_refs=[i.tool_call_id for i in manifest.items],
        )
        result = run_constitutional_checks(
            decision, manifest, requested_days=5, requested_date=future_date,
        )
        assert result.passed is True
        auth_result = evaluate(decision, result)
        assert auth_result.permitted is True
        assert auth_result.requires_human_approval is False
        assert auth_result.block_reason is None

    def test_tier1_permitted(self):
        manifest = _make_full_manifest()
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        decision = _make_decision(
            decision_type="approve", authorization_tier=1,
            evidence_refs=[i.tool_call_id for i in manifest.items],
        )
        result = run_constitutional_checks(
            decision, manifest, requested_days=5, requested_date=future_date,
        )
        assert result.passed is True
        auth_result = evaluate(decision, result)
        assert auth_result.permitted is True
        assert auth_result.requires_human_approval is False

    def test_cannot_proceed_from_blocked_without_approval(self):
        manifest = _make_full_manifest()
        decision = _make_decision(authorization_tier=3)
        result = run_constitutional_checks(decision, manifest)
        auth_result = evaluate(decision, result)
        assert auth_result.permitted is False
        assert auth_result.requires_human_approval is True

    def test_tier3_reject_not_blocked_by_gate(self):
        manifest = _make_full_manifest()
        decision = _make_decision(
            decision_type="reject", authorization_tier=3,
            evidence_refs=[i.tool_call_id for i in manifest.items],
        )
        result = run_constitutional_checks(decision, manifest)
        auth_result = evaluate(decision, result)
        assert auth_result.permitted is False
        assert auth_result.requires_human_approval is True
        assert auth_result.tier == 3

    def test_tier_action_map_termination(self):
        assert TIER_ACTION_MAP["termination"] == 3
        assert TIER_ACTION_MAP["suspension"] == 3
        assert TIER_ACTION_MAP["disciplinary_action"] == 3
        assert TIER_ACTION_MAP["employment_change"] == 3

    def test_tier_action_map_reversible(self):
        assert TIER_ACTION_MAP["create_leave_request"] == 2
        assert TIER_ACTION_MAP["prepare_task_reassignment"] == 2
        assert TIER_ACTION_MAP["create_approval_request"] == 2

    def test_tier_action_map_informational(self):
        assert TIER_ACTION_MAP["information_only"] == 1
        assert TIER_ACTION_MAP["needs_clarification"] == 1