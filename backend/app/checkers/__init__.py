"""OpsPilot — Checkers package.

Contains deterministic safety components:
- Constitutional Checker: validates decisions against hard rules
- Authorization Gate: enforces tier-based execution permission
"""

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
    TIER_ACTION_MAP as AUTHORIZATION_TIER_ACTION_MAP,
)

__all__ = [
    "CheckResult",
    "ConstitutionalCheckResult",
    "AuthorizationResult",
    "check_employee_exists",
    "check_evidence_refs_valid",
    "check_policy_exists",
    "check_balance_arithmetic_correct",
    "check_notice_period_satisfied",
    "check_coverage_not_violated",
    "check_no_duplicate_request",
    "check_authorization_tier_matches_action",
    "check_consequential_requires_approval",
    "check_evidence_not_stale",
    "run_constitutional_checks",
    "TIER_ACTION_MAP",
    "evaluate",
    "AUTHORIZATION_TIER_ACTION_MAP",
]