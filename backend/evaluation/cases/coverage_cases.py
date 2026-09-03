"""EVL-003, EVL-007, EVL-015 — coverage-conflict cases.

All three hinge on Operations coverage calculated from schedules via the
team_coverage view (scheduled minus unavailable = effective coverage).
"""

CASES = [
    {
        "case_id": "EVL-003",
        "title": "Coverage conflict on the peak Friday",
        "category": "coverage",
        "difficulty": "easy",
        "request": "Sarah Mitchell wants Friday 2026-09-11 off.",
        "request_type": "leave_request",
        "employee_code": "EMP-001",
        "context": {
            "employee": "EMP-001",
            "employee_name": "Sarah Mitchell",
            "leave_date": "2026-09-11",
            "days_requested": 1,
            "department": "DEP-001 Operations",
            "minimum_coverage": 3,
        },
        "expected_decision": "escalate",
        "expected_action": "escalate_to_manager",
        "expected_authorization_tier": 2,
        "expected_approval_required": True,
        "expected_evidence_types": ["employee", "leave_balance", "schedule",
                                    "department", "coverage", "policy"],
        "expected_policy_ids": ["POL-001", "POL-003"],
        "ground_truth_reason": (
            "On Friday 2026-09-11 exactly 3 Operations employees are scheduled WORKING "
            "(EMP-001 Sarah, EMP-018, EMP-019) against a required minimum of 3. Approving "
            "Sarah's leave drops effective coverage to 2, below the minimum. POL-003 "
            "forbids automatic approval when coverage falls below the department minimum "
            "and mandates escalation (approval_required = true). Balance and notice are "
            "fine — the conflict is purely coverage."
        ),
    },
    {
        "case_id": "EVL-007",
        "title": "Sufficient balance and notice but coverage conflict",
        "category": "coverage",
        "difficulty": "medium",
        "request": "Sarah Mitchell requests 2 days of annual leave on Thursday 2026-09-10 and Friday 2026-09-11.",
        "request_type": "leave_request",
        "employee_code": "EMP-001",
        "context": {
            "employee": "EMP-001",
            "employee_name": "Sarah Mitchell",
            "leave_start": "2026-09-10",
            "leave_end": "2026-09-11",
            "days_requested": 2,
            "submitted_on": "2026-08-31",
            "remaining_days": 8,
        },
        "expected_decision": "escalate",
        "expected_action": "escalate_to_manager",
        "expected_authorization_tier": 2,
        "expected_approval_required": True,
        "expected_evidence_types": ["employee", "leave_balance", "schedule",
                                    "coverage", "policy"],
        "expected_policy_ids": ["POL-001", "POL-002", "POL-003"],
        "ground_truth_reason": (
            "Balance (8 remaining, 2 requested) and notice (9 days) both pass. The "
            "conflict is coverage: on 2026-09-11 only 3 Operations employees are "
            "scheduled and Sarah's absence leaves 2, below the minimum of 3. POL-003 "
            "requires escalation with human approval whenever a covered date falls below "
            "the minimum — the balance/notice checks passing does not allow auto-approval."
        ),
    },
    {
        "case_id": "EVL-015",
        "title": "Coverage conflict compounded by existing team leave",
        "category": "coverage",
        "difficulty": "hard",
        "request": "Sarah Mitchell wants Friday 2026-09-18 off.",
        "request_type": "leave_request",
        "employee_code": "EMP-001",
        "context": {
            "employee": "EMP-001",
            "employee_name": "Sarah Mitchell",
            "leave_date": "2026-09-18",
            "days_requested": 1,
            "existing_team_leave": ["EMP-019 Fatima Noor (approved leave)"],
            "department": "DEP-001 Operations",
            "minimum_coverage": 3,
        },
        "expected_decision": "escalate",
        "expected_action": "escalate_to_manager",
        "expected_authorization_tier": 2,
        "expected_approval_required": True,
        "expected_evidence_types": ["employee", "leave_balance", "schedule",
                                    "coverage", "policy"],
        "expected_policy_ids": ["POL-001", "POL-003"],
        "ground_truth_reason": (
            "On 2026-09-18 Operations has 3 employees scheduled: EMP-001, EMP-018 and "
            "EMP-021, but EMP-019 is ALREADY on approved leave that day (visible only by "
            "checking teammate schedules, not just the roster count of scheduled rows). "
            "Effective coverage is 3; Sarah's leave would drop it to 2, below the minimum "
            "of 3 (POL-003). The agent must inspect existing team leave to reach this "
            "conclusion — escalating with approval required."
        ),
    },
]
