"""EVL-008, EVL-011, EVL-016 — task reassignment cases.

All three reference seeded tasks (TASK-001/002/003) and schedule/workload
evidence that must be gathered with multiple tool calls.
"""

CASES = [
    {
        "case_id": "EVL-008",
        "title": "Reassign task while a qualified replacement exists",
        "category": "task_reassignment",
        "difficulty": "medium",
        "request": "David Chen called in sick for 2026-09-09. Reassign his 'API Gateway Migration' task (TASK-001).",
        "request_type": "task_reassignment",
        "employee_code": "EMP-003",
        "context": {
            "employee": "EMP-003",
            "employee_name": "David Chen",
            "task": "TASK-001",
            "task_title": "API Gateway Migration",
            "unavailable_date": "2026-09-09",
            "replacement": "EMP-032 Ravi Iyer (WORKING 2026-09-09, 0 open tasks)",
        },
        "expected_decision": "approve",
        "expected_action": "reassign_task",
        "expected_authorization_tier": 2,
        "expected_approval_required": True,
        "expected_evidence_types": ["employee", "task", "schedule", "workload",
                                    "policy"],
        "expected_policy_ids": ["POL-004"],
        "ground_truth_reason": (
            "David Chen (EMP-003) is SICK on 2026-09-09 and owns TASK-001 'API Gateway "
            "Migration' (POL-004 requires reassignment or explicit review). Ravi Iyer "
            "(EMP-032) is scheduled WORKING on 2026-09-09, is in the same department, and "
            "is below the open-task capacity limit (max 3). A qualified replacement "
            "exists, so the reassignment is approved — POL-004 still requires human "
            "(manager) approval for the actual reassignment action."
        ),
    },
    {
        "case_id": "EVL-011",
        "title": "Task reassignment with no replacement available",
        "category": "task_reassignment",
        "difficulty": "medium",
        "request": "David Chen is sick on 2026-09-10 and owns the critical 'Payment Gateway Hotfix' (TASK-002) due that day. Reassign it.",
        "request_type": "task_reassignment",
        "employee_code": "EMP-003",
        "context": {
            "employee": "EMP-003",
            "employee_name": "David Chen",
            "task": "TASK-002",
            "task_title": "Payment Gateway Hotfix",
            "unavailable_date": "2026-09-10",
            "expected_replacements_available": 0,
        },
        "expected_decision": "escalate",
        "expected_action": "escalate_no_replacement",
        "expected_authorization_tier": 2,
        "expected_approval_required": True,
        "expected_evidence_types": ["employee", "task", "schedule", "workload",
                                    "policy"],
        "expected_policy_ids": ["POL-004"],
        "ground_truth_reason": (
            "David Chen is SICK on 2026-09-10. Every other Engineering employee is "
            "unavailable that day: EMP-030 is on LEAVE and all remaining engineers plus "
            "the Engineering Manager are OFF. POL-004 requires a same-department, "
            "available replacement with capacity — none exists. The agent must therefore "
            "escalate to the department manager for an explicit review/decision instead "
            "of picking an unqualified or unavailable person."
        ),
    },
    {
        "case_id": "EVL-016",
        "title": "Reassignment requiring schedule + workload reasoning",
        "category": "task_reassignment",
        "difficulty": "hard",
        "request": "Daniel Okafor is on leave 2026-09-14 to 2026-09-16. His critical 'Escalation Backlog Review' (TASK-003) is due 2026-09-17. Reassign it.",
        "request_type": "task_reassignment",
        "employee_code": "EMP-005",
        "context": {
            "employee": "EMP-005",
            "employee_name": "Daniel Okafor",
            "task": "TASK-003",
            "task_title": "Escalation Backlog Review",
            "leave_start": "2026-09-14",
            "leave_end": "2026-09-16",
            "candidates": {
                "EMP-024 Priya Sharma": "WORKING, 1 open task (capacity OK)",
                "EMP-025 Lucas Meyer": "on LEAVE 2026-09-14..16",
                "EMP-009 Maria Garcia": "3 open tasks (at capacity)",
            },
        },
        "expected_decision": "approve",
        "expected_action": "reassign_task",
        "expected_authorization_tier": 2,
        "expected_approval_required": True,
        "expected_evidence_types": ["employee", "task", "schedule", "workload",
                                    "policy"],
        "expected_policy_ids": ["POL-004"],
        "ground_truth_reason": (
            "Daniel Okafor (EMP-005) is on approved leave 2026-09-14..16 and owns the "
            "critical TASK-003 due 2026-09-17. The Context Assembly Agent must check "
            "multiple candidates: Lucas Meyer (EMP-025) is also on leave; Maria Garcia "
            "(EMP-009) is at her capacity limit (3 open tasks); Priya Sharma (EMP-024) is "
            "scheduled WORKING, same department, with only 1 open task. The only policy-"
            "compliant reassignment is to Priya Sharma — approved, with POL-004 manager "
            "approval required for the action itself."
        ),
    },
]
