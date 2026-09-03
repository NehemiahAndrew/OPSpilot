"""
Frozen evaluation cases for OpsPilot (Frontier Engineering Challenge 2026).

DO NOT MODIFY these cases after benchmark execution. Ground truth here is
deterministic: it references explicit employee codes (EMP-xxx), policy codes
(POL-xxx), task codes (TASK-xxx) and absolute dates, all of which are seeded
by backend/database/seed/04_seed_workforce.sql.

Case modules are logically separated:
    leave_cases.py          EVL-001, 002, 004, 005, 006, 009, 012, 013, 018
    coverage_cases.py       EVL-003, 007, 015
    task_cases.py           EVL-008, 011, 016
    authorization_cases.py  EVL-010, 014, 017
    adversarial_cases.py    EVL-019, 020

Decision vocabulary (maps to evaluation_cases.expected_decision_type):
    approve | decline | block | inform | escalate | request_info
Authorization tiers (POL-008):
    1 = informational / read-only          (auto)
    2 = standard consequential action      (auto-approve only when every
        policy check passes; approval required otherwise)
    3 = high-impact                        (autonomous execution BLOCKED,
        human approval REQUIRED)
Evidence vocabulary:
    employee | leave_balance | schedule | department | coverage | policy |
    task | workload | attendance | historical_decision
"""

from typing import Dict, List

from .leave_cases import CASES as _LEAVE
from .coverage_cases import CASES as _COVERAGE
from .task_cases import CASES as _TASK
from .authorization_cases import CASES as _AUTH
from .adversarial_cases import CASES as _ADV

ALL_CASES: List[Dict] = [*_LEAVE, *_COVERAGE, *_TASK, *_AUTH, *_ADV]

EXPECTED_DISTRIBUTION = {"easy": 6, "medium": 8, "hard": 4, "adversarial": 2}


def get_all_cases() -> List[Dict]:
    """Frozen 20-case benchmark, ordered by case_id."""
    return sorted(ALL_CASES, key=lambda c: c["case_id"])


def validate_cases() -> List[str]:
    """Structural self-checks. Run at import time (below) and by seed.py."""
    errors = []
    ids = [c["case_id"] for c in ALL_CASES]
    if len(ALL_CASES) != 20:
        errors.append(f"Expected exactly 20 cases, got {len(ALL_CASES)}")
    if len(set(ids)) != len(ids):
        errors.append("Duplicate case_id values present")
    dist: Dict[str, int] = {}
    for c in ALL_CASES:
        dist[c["difficulty"]] = dist.get(c["difficulty"], 0) + 1
        for f in ("case_id", "title", "category", "difficulty", "request",
                  "expected_decision", "expected_action",
                  "expected_authorization_tier", "expected_approval_required",
                  "expected_evidence_types", "expected_policy_ids",
                  "ground_truth_reason"):
            if f not in c:
                errors.append(f"{c.get('case_id', '?')} missing field {f}")
        if c["expected_decision"] not in (
                "approve", "decline", "block", "inform", "escalate",
                "request_info"):
            errors.append(f"{c['case_id']} bad expected_decision "
                          f"{c['expected_decision']}")
        if c["expected_authorization_tier"] not in (1, 2, 3):
            errors.append(f"{c['case_id']} bad authorization tier")
    if dist != EXPECTED_DISTRIBUTION:
        errors.append(f"Difficulty distribution {dist} != {EXPECTED_DISTRIBUTION}")
    return errors

# ------------------------------------------------------------------
# Emitters: evaluation/cases/cases.json + seed/03_seed_evaluation_cases.sql
# ------------------------------------------------------------------

# Legacy column mapping (evaluation_cases schema from 004_evaluation.sql)
_DECISION_MAP = {
    "approve": "approve",
    "decline": "decline",
    "block": "block",
    "inform": "inform",
    "escalate": "escalate",
    "request_info": "request_info",
}


def emit_cases_json() -> str:
    import json
    return json.dumps(
        {"frozen": True, "benchmark": "Frontier Engineering Challenge 2026",
         "count": len(get_all_cases()), "cases": get_all_cases()},
        indent=2, ensure_ascii=False) + "\n"


def emit_cases_sql() -> str:
    """Generate seed/03_seed_evaluation_cases.sql. Codes are resolved to the
    stable UUIDs minted in backend/data/generator.py."""
    import os
    import sys
    import json
    sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..")))
    from backend.data.generator import emp_uuid, policy_uuid, _q

    L = []
    A = L.append
    A("-- seed/03_seed_evaluation_cases.sql - AUTO-GENERATED")
    A("-- Source of truth: backend/evaluation/cases/ (FROZEN ground truth).")
    A("-- DO NOT EDIT BY HAND — regenerate with: python -m backend.data.seed --emit")
    A("-- Runs AFTER 04_seed_workforce.sql (references employees/policies).")
    A("")
    A("BEGIN;")
    A("DELETE FROM evaluation_cases;")
    A("")
    for c in get_all_cases():
        emp = (f"'{emp_uuid(c['employee_code'])}'"
               if c.get("employee_code") else "NULL")
        ctx = json.dumps(c["context"], ensure_ascii=False).replace("'", "''")
        ev = "{" + ",".join(c["expected_evidence_types"]) + "}"
        ev_keys = ev  # legacy column: same vocabulary
        pols = "{" + ",".join(policy_uuid(p)
                              for p in c["expected_policy_ids"]) + "}"
        pol_codes = "{" + ",".join(c["expected_policy_ids"]) + "}"
        dec = _DECISION_MAP[c["expected_decision"]]
        edge = "TRUE" if c["difficulty"] in ("hard", "adversarial") else "FALSE"
        adv = "TRUE" if c["difficulty"] == "adversarial" else "FALSE"
        A(f"INSERT INTO evaluation_cases (case_number, title, description, raw_input, "
          f"employee_id, request_type, expected_decision_type, expected_authorization_tier, "
          f"expected_approval_required, expected_evidence_keys, expected_policy_applied, "
          f"is_edge_case, difficulty, adversarial, category, context, expected_action, "
          f"expected_evidence_types, expected_policy_codes, ground_truth_reason) VALUES (")
        A(f"    '{c['case_id']}', '{_q(c['title'])}', NULL, '{_q(c['request'])}', "
          f"{emp}, '{c['request_type']}', '{dec}', {c['expected_authorization_tier']}, "
          f"{'TRUE' if c['expected_approval_required'] else 'FALSE'}, '{ev_keys}', "
          f"'{pols}', {edge}, '{c['difficulty']}', {adv}, '{c['category']}', "
          f"'{ctx}'::jsonb, '{_q(c['expected_action'])}', '{ev}', '{pol_codes}', "
          f"'{_q(c['ground_truth_reason'])}')")
        A("ON CONFLICT (case_number) DO UPDATE SET title = EXCLUDED.title, "
          "raw_input = EXCLUDED.raw_input, employee_id = EXCLUDED.employee_id, "
          "request_type = EXCLUDED.request_type, "
          "expected_decision_type = EXCLUDED.expected_decision_type, "
          "expected_authorization_tier = EXCLUDED.expected_authorization_tier, "
          "expected_approval_required = EXCLUDED.expected_approval_required, "
          "expected_evidence_keys = EXCLUDED.expected_evidence_keys, "
          "expected_policy_applied = EXCLUDED.expected_policy_applied, "
          "is_edge_case = EXCLUDED.is_edge_case, difficulty = EXCLUDED.difficulty, "
          "adversarial = EXCLUDED.adversarial, category = EXCLUDED.category, "
          "context = EXCLUDED.context, expected_action = EXCLUDED.expected_action, "
          "expected_evidence_types = EXCLUDED.expected_evidence_types, "
          "expected_policy_codes = EXCLUDED.expected_policy_codes, "
          "ground_truth_reason = EXCLUDED.ground_truth_reason;")
        A("")
    A("COMMIT;")
    return "\n".join(L) + "\n"


_case_errors = validate_cases()
if _case_errors:
    raise ImportError(f"Frozen evaluation cases are invalid: {_case_errors}")

