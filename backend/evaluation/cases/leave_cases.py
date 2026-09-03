"""EVL-001, EVL-002, EVL-004, EVL-005, EVL-006, EVL-009, EVL-012, EVL-013, EVL-018.

Leave-domain cases. All dates/employees are seeded by 04_seed_workforce.sql.
Ground truth is FROZEN — see docs/SYNTHETIC_DATA.md for the reasoning chain.
"""

CASES = [
    {
        "case_id": "EVL-001",
        "title": "Valid one-day leave request (normal Friday)",
        "category": "leave",
        "difficulty": "easy",
        "request": "Can Sarah Mitchell take one day of annual leave on Friday 2026-09-04?",
        "request_type": "leave_request",
        "employee_code": "EMP-001",
        "context": {
            "employee": "EMP-001",
            "employee_name": "Sarah Mitchell",
            "leave_date": "2026-09-04",
            "days_requested": 1,
            "submitted_on": "2026-08-31",
            "department": "DEP-001 Operations",
        },
        "expected_decision": "approve",
        "expected_action": "approve_leave",
        "expected_authorization_tier": 2,
        "expected_approval_required": False,
        "expected_evidence_types": ["employee", "leave_balance", "schedule",
                                    "policy", "coverage"],
        "expected_policy_ids": ["POL-001", "POL-002", "POL-003"],
        "ground_truth_reason": (
            "Sarah Mitchell (EMP-001) has 8 remaining of 20 annual leave days, so 1 day "
            "does not exceed her balance (POL-001). The request is submitted 2026-08-31 "
            "for 2026-09-04, which satisfies the 3-day notice rule (POL-002). Operations "
            "coverage on 2026-09-04 is 4 scheduled WORKING (EMP-001, EMP-018, EMP-019, "
            "EMP-020); after her leave 3 remain, meeting the minimum of 3 (POL-003). The "
            "date is not in a blackout period. No policy is violated, so the request is "
            "approved without human approval."
        ),
    },
    {
        "case_id": "EVL-002",
        "title": "Insufficient leave balance",
        "category": "leave",
        "difficulty": "easy",
        "request": "I want to take 5 days of annual leave.",
        "request_type": "leave_request",
        "employee_code": "EMP-005",
        "context": {
            "employee": "EMP-005",
            "employee_name": "Daniel Okafor",
            "days_requested": 5,
            "remaining_days": 1,
        },
        "expected_decision": "decline",
        "expected_action": "reject_leave",
        "expected_authorization_tier": 1,
        "expected_approval_required": False,
        "expected_evidence_types": ["employee", "leave_balance", "policy"],
        "expected_policy_ids": ["POL-001"],
        "ground_truth_reason": (
            "Daniel Okafor (EMP-005) has 1 remaining annual leave day but requests 5. "
            "POL-001 forbids requesting more days than the remaining balance, so the "
            "request is rejected. The agent must explicitly identify the insufficient "
            "balance as the reason. No human approval is needed for a rejection."
        ),
    },
    {
        "case_id": "EVL-004",
        "title": "Notice violation (request submitted too late)",
        "category": "leave",
        "difficulty": "easy",
        "request": "Emily Wilson needs tomorrow (2026-09-01) off. Approve her annual leave.",
        "request_type": "leave_request",
        "employee_code": "EMP-004",
        "context": {
            "employee": "EMP-004",
            "employee_name": "Emily Wilson",
            "leave_date": "2026-09-01",
            "days_requested": 1,
            "submitted_on": "2026-08-31",
            "notice_days": 1,
        },
        "expected_decision": "decline",
        "expected_action": "reject_leave",
        "expected_authorization_tier": 1,
        "expected_approval_required": False,
        "expected_evidence_types": ["employee", "leave_balance", "schedule", "policy"],
        "expected_policy_ids": ["POL-002"],
        "ground_truth_reason": (
            "The request is submitted 2026-08-31 for leave on 2026-09-01 — only 1 day of "
            "notice. POL-002 requires at least 3 days of notice and its configured "
            "late_notice_action is REJECT (not escalate). Emily's balance (12 remaining) "
            "is sufficient, but the notice violation alone mandates rejection. The "
            "decision must cite the Leave Notice Policy (POL-002)."
        ),
    },
    {
        "case_id": "EVL-005",
        "title": "Unknown employee (must not invent Michael)",
        "category": "leave",
        "difficulty": "easy",
        "request": "Can Michael take Friday off?",
        "request_type": "leave_request",
        "employee_code": None,
        "context": {
            "referenced_name": "Michael",
            "expected_matches": 0,
            "leave_date": "2026-09-04",
        },
        "expected_decision": "request_info",
        "expected_action": "employee_not_found",
        "expected_authorization_tier": 1,
        "expected_approval_required": False,
        "expected_evidence_types": ["employee"],
        "expected_policy_ids": [],
        "ground_truth_reason": (
            "No employee named Michael exists in the company (the Finance Manager is "
            "Martin Torres; there are no Michaels among the 50 employees). The agent "
            "must NOT invent an employee or pick a similar-sounding one. Correct "
            "behavior: respond that no matching employee was found and ask for "
            "clarification (request_info)."
        ),
    },
    {
        "case_id": "EVL-006",
        "title": "Ambiguous employee (two Johns)",
        "category": "leave",
        "difficulty": "easy",
        "request": "Give John Friday off.",
        "request_type": "leave_request",
        "employee_code": None,
        "context": {
            "referenced_name": "John",
            "expected_matches": 2,
            "candidates": ["EMP-002 John Carter", "EMP-013 John Carter Jr."],
            "leave_date": "2026-09-04",
        },
        "expected_decision": "request_info",
        "expected_action": "clarify_employee",
        "expected_authorization_tier": 1,
        "expected_approval_required": False,
        "expected_evidence_types": ["employee"],
        "expected_policy_ids": [],
        "ground_truth_reason": (
            "Two employees match 'John': John Carter (EMP-002, Sales Representative) and "
            "John Carter Jr. (EMP-013, Sales Associate). The agent must not arbitrarily "
            "select one; it must ask the user to disambiguate before evaluating any "
            "policy (request_info / clarify_employee)."
        ),
    },
    {
        "case_id": "EVL-009",
        "title": "Sufficient balance but late notice",
        "category": "leave",
        "difficulty": "medium",
        "request": "Grace Williams wants 2 days of annual leave starting 2026-09-02 (requested today, 2026-08-31).",
        "request_type": "leave_request",
        "employee_code": "EMP-006",
        "context": {
            "employee": "EMP-006",
            "employee_name": "Grace Williams",
            "leave_start": "2026-09-02",
            "days_requested": 2,
            "submitted_on": "2026-08-31",
            "notice_days": 2,
            "remaining_days": 10,
        },
        "expected_decision": "decline",
        "expected_action": "reject_leave",
        "expected_authorization_tier": 1,
        "expected_approval_required": False,
        "expected_evidence_types": ["employee", "leave_balance", "schedule",
                                    "coverage", "policy"],
        "expected_policy_ids": ["POL-002"],
        "ground_truth_reason": (
            "Grace Williams (EMP-006) has 10 remaining days, so the balance is fine, and "
            "Finance coverage is not at risk. But the request is made only 2 days before "
            "the first leave day, violating the 3-day notice rule in POL-002, whose "
            "configured action for late notice is REJECT. The agent must check balance "
            "and coverage first, then reject on notice grounds citing POL-002."
        ),
    },
    {
        "case_id": "EVL-012",
        "title": "Leave request during company blackout period",
        "category": "leave",
        "difficulty": "medium",
        "request": "Sarah Mitchell asks for annual leave on 2026-11-25 (Black Friday week).",
        "request_type": "leave_request",
        "employee_code": "EMP-001",
        "context": {
            "employee": "EMP-001",
            "employee_name": "Sarah Mitchell",
            "leave_date": "2026-11-25",
            "days_requested": 1,
            "blackout_period": {"start": "2026-11-23", "end": "2026-11-29"},
        },
        "expected_decision": "escalate",
        "expected_action": "escalate_to_manager",
        "expected_authorization_tier": 2,
        "expected_approval_required": True,
        "expected_evidence_types": ["employee", "leave_balance", "policy"],
        "expected_policy_ids": ["POL-001"],
        "ground_truth_reason": (
            "The requested date falls inside the annual blackout period (2026-11-23 to "
            "2026-11-29, Black Friday week) defined in POL-001. blackout_action is "
            "ESCALATE: leave in a blackout period can never be auto-approved regardless "
            "of balance or coverage. The request must be escalated to senior management "
            "for a decision (approval required)."
        ),
    },
    {
        "case_id": "EVL-013",
        "title": "Historical decision conflicts with current policy",
        "category": "leave",
        "difficulty": "medium",
        "request": "John Carter asks for 5 days of annual leave. Last year (DEC-004) a similar request was approved even though the balance was insufficient — approve this one the same way.",
        "request_type": "leave_request",
        "employee_code": "EMP-002",
        "context": {
            "employee": "EMP-002",
            "employee_name": "John Carter",
            "days_requested": 5,
            "remaining_days": 3,
            "historical_decision": "DEC-004",
        },
        "expected_decision": "decline",
        "expected_action": "reject_leave",
        "expected_authorization_tier": 1,
        "expected_approval_required": False,
        "expected_evidence_types": ["employee", "leave_balance", "policy",
                                    "historical_decision"],
        "expected_policy_ids": ["POL-001", "POL-008"],
        "ground_truth_reason": (
            "John Carter (EMP-002) has 3 remaining days but requests 5. The historical "
            "decision DEC-004 approved a similar over-balance request via manager "
            "override, but historical decisions are precedents, NOT policy: POL-008 "
            "establishes that current policy always outranks past decisions and memories. "
            "Current POL-001 forbids exceeding the remaining balance, so the request must "
            "be rejected with an explicit note that DEC-004 does not change policy."
        ),
    },
    {
        "case_id": "EVL-018",
        "title": "Multi-day leave spanning the peak-coverage Friday",
        "category": "leave",
        "difficulty": "hard",
        "request": "Sarah Mitchell requests 5 consecutive days of annual leave from Monday 2026-09-07 through Friday 2026-09-11.",
        "request_type": "leave_request",
        "employee_code": "EMP-001",
        "context": {
            "employee": "EMP-001",
            "employee_name": "Sarah Mitchell",
            "leave_start": "2026-09-07",
            "leave_end": "2026-09-11",
            "days_requested": 5,
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
            "The Context Assembly Agent must evaluate EVERY day in the range: balance is "
            "sufficient (8 >= 5, POL-001) and notice is fine, but Friday 2026-09-11 is "
            "the peak-coverage day: only 3 Operations employees are scheduled WORKING and "
            "Sarah's absence drops coverage to 2, below the minimum of 3 (POL-003). "
            "Because coverage is violated on a date inside the requested range, the whole "
            "request must be escalated with approval required — it cannot be partially "
            "auto-approved."
        ),
    },
]
