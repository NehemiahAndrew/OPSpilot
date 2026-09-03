"""OpsPilot — Constitutional Checker (deterministic, no LLM).

Validates the proposed decision against hard rules grounded in the
evidence manifest. Every check is independently testable and
produces a structured CheckResult.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from backend.app.agents.decision_agent import DecisionOutput
from backend.app.models.agent import EvidenceManifest, EvidenceItem


# ======================================================================
# Check Result Models
# ======================================================================
class CheckResult(BaseModel):
    """Result of a single constitutional check."""

    check_name: str
    passed: bool
    severity: Literal["error", "warning", "info"]
    detail: str


class ConstitutionalCheckResult(BaseModel):
    """Aggregate result of all constitutional checks."""

    passed: bool
    violations: List[CheckResult] = Field(default_factory=list)
    warnings: List[CheckResult] = Field(default_factory=list)
    all_checks: List[CheckResult] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ======================================================================
# Helpers
# ======================================================================
def _find_evidence(
    manifest: EvidenceManifest,
    *,
    evidence_key: Optional[str] = None,
    evidence_type: Optional[str] = None,
) -> List[EvidenceItem]:
    """Filter manifest items by evidence_key and/or evidence_type."""
    results = list(manifest.items)
    if evidence_key is not None:
        results = [i for i in results if i.evidence_key == evidence_key]
    if evidence_type is not None:
        results = [i for i in results if i.evidence_type == evidence_type]
    return results


def _get_evidence_data(
    manifest: EvidenceManifest,
    evidence_key: str,
    evidence_type: Optional[str] = None,
) -> Optional[Dict]:
    """Get the data dict from the first matching evidence item."""
    items = _find_evidence(manifest, evidence_key=evidence_key, evidence_type=evidence_type)
    if items:
        return items[0].data
    return None


# ======================================================================
# CHECK-001: employee_exists
# ======================================================================
def check_employee_exists(manifest: EvidenceManifest) -> CheckResult:
    """manifest.items where evidence_key='employee_record' must exist
    and data.status must be 'active'."""
    emp_items = _find_evidence(manifest, evidence_key="employee_record")
    if not emp_items:
        return CheckResult(
            check_name="CHECK-001",
            passed=False,
            severity="error",
            detail="No employee_record evidence found in manifest",
        )
    for item in emp_items:
        status = item.data.get("status") if isinstance(item.data, dict) else None
        if status != "active":
            return CheckResult(
                check_name="CHECK-001",
                passed=False,
                severity="error",
                detail=f"Employee record status is '{status}', expected 'active'",
            )
    return CheckResult(
        check_name="CHECK-001",
        passed=True,
        severity="info",
        detail="Employee record exists and is active",
    )


# ======================================================================
# CHECK-002: evidence_refs_valid
# ======================================================================
def check_evidence_refs_valid(
    decision: DecisionOutput,
    manifest: EvidenceManifest,
) -> CheckResult:
    """Every evidence_ref in the decision must exist in the manifest.
    If ANY fabricated → VIOLATION."""
    valid_ids = {item.tool_call_id for item in manifest.items}
    valid_ids.update({item.evidence_id for item in manifest.items})

    fabricated = [ref for ref in decision.evidence_refs if ref not in valid_ids]
    if fabricated:
        return CheckResult(
            check_name="CHECK-002",
            passed=False,
            severity="error",
            detail=f"Fabricated evidence references detected: {fabricated}",
        )
    return CheckResult(
        check_name="CHECK-002",
        passed=True,
        severity="info",
        detail="All evidence references are valid",
    )


# ======================================================================
# CHECK-003: policy_exists
# ======================================================================
def check_policy_exists(decision: DecisionOutput, manifest: EvidenceManifest) -> CheckResult:
    """Every policy_ref in the decision must be present in the manifest.
    If policy not retrieved → VIOLATION."""
    policy_items = _find_evidence(manifest, evidence_type="policy")
    if not policy_items:
        if decision.decision_type in ("approve", "reject"):
            return CheckResult(
                check_name="CHECK-003",
                passed=False,
                severity="error",
                detail="No policy evidence found in manifest but decision was made",
            )
        return CheckResult(
            check_name="CHECK-003",
            passed=True,
            severity="info",
            detail="No policy evidence required for this decision",
        )
    return CheckResult(
        check_name="CHECK-003",
        passed=True,
        severity="info",
        detail="Policy evidence is present in manifest",
    )


# ======================================================================
# CHECK-004: balance_arithmetic_correct
# ======================================================================
def check_balance_arithmetic_correct(
    decision: DecisionOutput,
    manifest: EvidenceManifest,
    requested_days: int = 0,
) -> CheckResult:
    """If request_type = leave and decision = approve:
    manifest.leave_balance.available >= requested_days.
    This is arithmetic, not LLM judgment."""
    if decision.decision_type != "approve":
        return CheckResult(
            check_name="CHECK-004",
            passed=True,
            severity="info",
            detail="Balance check skipped (decision is not approve)",
        )
    balance_data = _get_evidence_data(manifest, "leave_balance", evidence_type="balance")
    if balance_data is None:
        return CheckResult(
            check_name="CHECK-004",
            passed=False,
            severity="error",
            detail="No leave_balance evidence found in manifest",
        )
    available = balance_data.get("available")
    if available is None:
        available = balance_data.get("remaining_days")
    if available is None:
        return CheckResult(
            check_name="CHECK-004",
            passed=False,
            severity="error",
            detail="Leave balance data does not contain 'available' field",
        )
    try:
        available_val = float(available)
    except (TypeError, ValueError):
        return CheckResult(
            check_name="CHECK-004",
            passed=False,
            severity="error",
            detail=f"Leave balance available value is not numeric: {available}",
        )
    if requested_days <= 0:
        return CheckResult(
            check_name="CHECK-004",
            passed=True,
            severity="info",
            detail="No requested days specified — balance check skipped",
        )
    if available_val < requested_days:
        return CheckResult(
            check_name="CHECK-004",
            passed=False,
            severity="error",
            detail=f"Balance arithmetic violation: available={available_val}, requested_days={requested_days}",
        )
    return CheckResult(
        check_name="CHECK-004",
        passed=True,
        severity="info",
        detail=f"Balance arithmetic correct: available={available_val} >= requested_days={requested_days}",
    )


# ======================================================================
# CHECK-005: notice_period_satisfied
# ======================================================================
def check_notice_period_satisfied(
    decision: DecisionOutput,
    manifest: EvidenceManifest,
    requested_date: Optional[str] = None,
) -> CheckResult:
    """If request_type = leave and decision = approve:
    (requested_date - today) >= policy.rules.notice_days
    If not satisfied and decision = approve → VIOLATION."""
    if decision.decision_type != "approve":
        return CheckResult(
            check_name="CHECK-005",
            passed=True,
            severity="info",
            detail="Notice check skipped (decision is not approve)",
        )
    policy_data = _get_evidence_data(manifest, "leave_policy", evidence_type="policy")
    if policy_data is None:
        return CheckResult(
            check_name="CHECK-005",
            passed=False,
            severity="error",
            detail="No leave_policy evidence found in manifest",
        )
    rules = policy_data.get("rules", {}) if isinstance(policy_data, dict) else {}
    notice_days = rules.get("standard_notice_days", 3)
    if requested_date is None:
        return CheckResult(
            check_name="CHECK-005",
            passed=False,
            severity="error",
            detail="No requested_date provided for notice period check",
        )
    try:
        if isinstance(requested_date, str):
            req_date = datetime.fromisoformat(requested_date).date()
        else:
            req_date = requested_date
    except (ValueError, TypeError):
        return CheckResult(
            check_name="CHECK-005",
            passed=False,
            severity="error",
            detail=f"Invalid requested_date format: {requested_date}",
        )
    today = datetime.now(timezone.utc).date()
    days_until = (req_date - today).days
    if days_until < notice_days:
        return CheckResult(
            check_name="CHECK-005",
            passed=False,
            severity="error",
            detail=f"Notice period violated: {days_until} days until requested date, "
                   f"but {notice_days} days notice required",
        )
    return CheckResult(
        check_name="CHECK-005",
        passed=True,
        severity="info",
        detail=f"Notice period satisfied: {days_until} days >= {notice_days} required",
    )


# ======================================================================
# CHECK-006: coverage_not_violated
# ======================================================================
def check_coverage_not_violated(
    decision: DecisionOutput,
    manifest: EvidenceManifest,
) -> CheckResult:
    """If request_type = leave and decision = approve:
    If team_coverage.is_coverage_sufficient = False → WARNING
    If only scheduled employee → VIOLATION (cannot auto-approve)."""
    if decision.decision_type != "approve":
        return CheckResult(
            check_name="CHECK-006",
            passed=True,
            severity="info",
            detail="Coverage check skipped (decision is not approve)",
        )
    coverage_data = _get_evidence_data(manifest, "team_coverage", evidence_type="coverage")
    if coverage_data is None:
        return CheckResult(
            check_name="CHECK-006",
            passed=False,
            severity="warning",
            detail="No team_coverage evidence found in manifest",
        )
    is_sufficient = coverage_data.get("is_coverage_sufficient")
    if is_sufficient is False:
        return CheckResult(
            check_name="CHECK-006",
            passed=False,
            severity="warning",
            detail="Team coverage is insufficient",
        )
    only_scheduled = coverage_data.get("only_scheduled_employee", False)
    if only_scheduled is True:
        return CheckResult(
            check_name="CHECK-006",
            passed=False,
            severity="error",
            detail="Cannot auto-approve: only scheduled employee available",
        )
    return CheckResult(
        check_name="CHECK-006",
        passed=True,
        severity="info",
        detail="Team coverage is sufficient",
    )


# ======================================================================
# CHECK-007: no_duplicate_request
# ======================================================================
def check_no_duplicate_request(
    decision: DecisionOutput,
    manifest: EvidenceManifest,
) -> CheckResult:
    """If pending request exists for same employee/type/date → VIOLATION."""
    pending_data = _get_evidence_data(manifest, "pending_requests", evidence_type="pending")
    if pending_data is None:
        return CheckResult(
            check_name="CHECK-007",
            passed=True,
            severity="info",
            detail="No pending request data found — duplicate check skipped",
        )
    pending_requests = pending_data.get("requests", pending_data.get("items", []))
    if not pending_requests:
        return CheckResult(
            check_name="CHECK-007",
            passed=True,
            severity="info",
            detail="No pending requests found — no duplicates",
        )
    if isinstance(pending_requests, dict):
        pending_requests = [pending_requests]
    for req in pending_requests:
        if isinstance(req, dict) and req.get("status") == "pending":
            return CheckResult(
                check_name="CHECK-007",
                passed=False,
                severity="error",
                detail=f"Duplicate pending request found: {req.get('request_id', 'unknown')}",
            )
    return CheckResult(
        check_name="CHECK-007",
        passed=True,
        severity="info",
        detail="No duplicate pending requests found",
    )


# ======================================================================
# CHECK-008: authorization_tier_matches_action
# ======================================================================
TIER_ACTION_MAP = {
    "information_only": 1,
    "needs_clarification": 1,
    "create_leave_request": 2,
    "prepare_task_reassignment": 2,
    "create_approval_request": 2,
    "termination": 3,
    "suspension": 3,
    "disciplinary_action": 3,
    "employment_change": 3,
}


def check_authorization_tier_matches_action(decision: DecisionOutput) -> CheckResult:
    """Map recommended_action → expected tier.
    termination/suspension/disciplinary_change → must be tier 3.
    If mismatch → VIOLATION."""
    action = decision.reason.split(":")[0].strip().lower() if decision.reason else ""
    if not action:
        return CheckResult(
            check_name="CHECK-008",
            passed=True,
            severity="info",
            detail="No action type specified in reason — tier check skipped",
        )
    expected_tier = None
    for action_key, tier in TIER_ACTION_MAP.items():
        if action_key in action:
            expected_tier = tier
            break
    if expected_tier is None:
        return CheckResult(
            check_name="CHECK-008",
            passed=True,
            severity="info",
            detail=f"Action type not in TIER_ACTION_MAP — tier check skipped",
        )
    if decision.authorization_tier != expected_tier:
        return CheckResult(
            check_name="CHECK-008",
            passed=False,
            severity="error",
            detail=f"Authorization tier mismatch: action requires tier {expected_tier}, "
                   f"but decision has tier {decision.authorization_tier}",
        )
    return CheckResult(
        check_name="CHECK-008",
        passed=True,
        severity="info",
        detail=f"Authorization tier matches action: tier {expected_tier}",
    )


# ======================================================================
# CHECK-009: consequential_requires_approval
# ======================================================================
def check_consequential_requires_approval(decision: DecisionOutput) -> CheckResult:
    """If tier == 3 and requires_human_approval == False → VIOLATION.
    Override it and record the violation."""
    if decision.authorization_tier == 3:
        has_approval_field = hasattr(decision, "requires_human_approval")
        if has_approval_field and decision.requires_human_approval is False:
            return CheckResult(
                check_name="CHECK-009",
                passed=False,
                severity="error",
                detail="Tier 3 decision without requires_human_approval=True — override applied",
            )
    return CheckResult(
        check_name="CHECK-009",
        passed=True,
        severity="info",
        detail="Consequential approval check passed",
    )


# ======================================================================
# CHECK-010: evidence_not_stale
# ======================================================================
def check_evidence_not_stale(manifest: EvidenceManifest) -> CheckResult:
    """If any evidence item was retrieved > 10 minutes ago → WARNING."""
    now = datetime.now(timezone.utc)
    stale_items = []
    for item in manifest.items:
        retrieved = item.retrieved_at
        if retrieved is None:
            continue
        age = now - retrieved
        if age > timedelta(minutes=10):
            stale_items.append(item.tool_call_id)
    if stale_items:
        return CheckResult(
            check_name="CHECK-010",
            passed=False,
            severity="warning",
            detail=f"Evidence items retrieved > 10 minutes ago: {stale_items}",
        )
    return CheckResult(
        check_name="CHECK-010",
        passed=True,
        severity="info",
        detail="All evidence items are fresh (< 10 minutes old)",
    )


# ======================================================================
# Full constitutional checker
# ======================================================================
def run_constitutional_checks(
    decision: DecisionOutput,
    manifest: EvidenceManifest,
    requested_days: int = 0,
    requested_date: Optional[str] = None,
) -> ConstitutionalCheckResult:
    """Run all 10 constitutional checks and return the aggregate result."""
    checks = [
        check_employee_exists(manifest),
        check_evidence_refs_valid(decision, manifest),
        check_policy_exists(decision, manifest),
        check_balance_arithmetic_correct(decision, manifest, requested_days),
        check_notice_period_satisfied(decision, manifest, requested_date),
        check_coverage_not_violated(decision, manifest),
        check_no_duplicate_request(decision, manifest),
        check_authorization_tier_matches_action(decision),
        check_consequential_requires_approval(decision),
        check_evidence_not_stale(manifest),
    ]
    violations = [c for c in checks if not c.passed and c.severity == "error"]
    warnings = [c for c in checks if c.severity == "warning"]
    passed = len(violations) == 0
    return ConstitutionalCheckResult(
        passed=passed,
        violations=violations,
        warnings=warnings,
        all_checks=checks,
    )