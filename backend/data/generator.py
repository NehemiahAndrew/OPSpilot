"""
generator.py — Synthetic Workforce Simulation generator for OpsPilot
(Frontier Engineering Challenge 2026).

Single source of truth for the Acme Retail Group simulation:

  * 1 fictional business, 6 departments, 50 employees (all synthetic)
  * deterministic business codes mapped to stable UUIDs
      DEP-001.. / EMP-001.. / POL-001.. / TASK-001.. / ATT-0001.. / DEC-001..
  * schedules that make team coverage *calculable*: the team_coverage view
    derives scheduled - unavailable = effective coverage per department/day
  * policies with machine-readable JSONB rules and approval requirements
  * tasks, attendance history and historical decisions referenced by the
    frozen evaluation cases (backend/evaluation/cases/)

Determinism guarantees:
  * BASE_DATE is a FIXED anchor date (2026-08-31) — never date.today()
  * RNG_SEED is fixed and only used for non-evaluation flavor data
  * every evaluation-critical schedule scenario is an EXPLICIT override,
    never random
  * evaluation ground truth is NOT generated here; it is frozen in
    backend/evaluation/cases/ (this module only resolves codes -> UUIDs)

Emit SQL seeds:
    python -m backend.data.generator          # writes 04_seed_workforce.sql
"""

import hashlib
import json
import random
from datetime import date, time, timedelta

# ------------------------------------------------------------------
# Fixed simulation anchor (hackathon period). NEVER use date.today():
# reproducibility requires absolute dates.
# ------------------------------------------------------------------
BUSINESS_ID = "a0000000-0000-0000-0000-000000000001"
BUSINESS_NAME = "Acme Retail Group"
RNG_SEED = 42

BASE_DATE = date(2026, 8, 31)            # Monday — "today" inside the world
HISTORY_START = date(2026, 7, 20)        # attendance history window start
HISTORY_END = date(2026, 8, 28)          # attendance history window end
SCHEDULE_START = date(2026, 8, 24)
SCHEDULE_END = date(2026, 10, 2)

# Critical scenario dates (referenced by frozen evaluation cases)
FRIDAY_NORMAL = date(2026, 9, 4)         # EVL-001: coverage survives Sarah's leave
FRIDAY_PEAK = date(2026, 9, 11)          # EVL-003/007: coverage conflict
FRIDAY_TEAM_LEAVE = date(2026, 9, 18)    # EVL-015: existing team leave compounds
DAVID_SICK_1 = date(2026, 9, 9)          # EVL-008: David sick, replacement exists
ENG_NO_REPLACE = date(2026, 9, 10)       # EVL-011: no engineer available
DANIEL_LEAVE_START = date(2026, 9, 14)   # EVL-016: Daniel on leave 3 days
DANIEL_LEAVE_END = date(2026, 9, 16)

NOTICE_DAYS = 3                          # POL-002
BLACKOUT_START = date(2026, 11, 23)      # POL-001 blackout (Black Friday week)
BLACKOUT_END = date(2026, 11, 29)

# ------------------------------------------------------------------
# Departments
# ------------------------------------------------------------------
DEPARTMENTS = [
    {"dept_code": "DEP-001", "id": "b0000000-0000-0000-0000-000000000011",
     "name": "Operations", "min_coverage": 3, "manager_code": "EMP-007"},
    {"dept_code": "DEP-002", "id": "b0000000-0000-0000-0000-000000000012",
     "name": "Sales", "min_coverage": 2, "manager_code": "EMP-008"},
    {"dept_code": "DEP-003", "id": "b0000000-0000-0000-0000-000000000013",
     "name": "Customer Support", "min_coverage": 4, "manager_code": "EMP-011"},
    {"dept_code": "DEP-004", "id": "b0000000-0000-0000-0000-000000000014",
     "name": "Engineering", "min_coverage": 2, "manager_code": "EMP-009"},
    {"dept_code": "DEP-005", "id": "b0000000-0000-0000-0000-000000000015",
     "name": "Finance", "min_coverage": 2, "manager_code": "EMP-012"},
    {"dept_code": "DEP-006", "id": "b0000000-0000-0000-0000-000000000016",
     "name": "Human Resources", "min_coverage": 1, "manager_code": "EMP-010"},
]
DEPT_ID_BY_CODE = {d["dept_code"]: d["id"] for d in DEPARTMENTS}

# Explicit department membership (50 employees, each exactly once).
DEPT_MEMBERSHIP = {
    "DEP-001": ["EMP-001", "EMP-007", "EMP-018", "EMP-019", "EMP-020", "EMP-021",
                "EMP-022", "EMP-023", "EMP-026"],
    "DEP-002": ["EMP-002", "EMP-008", "EMP-013", "EMP-027", "EMP-028", "EMP-029",
                "EMP-037", "EMP-038"],
    "DEP-003": ["EMP-005", "EMP-011", "EMP-024", "EMP-025", "EMP-039", "EMP-040",
                "EMP-041", "EMP-042", "EMP-043", "EMP-044"],
    "DEP-004": ["EMP-003", "EMP-009", "EMP-030", "EMP-031", "EMP-032", "EMP-033",
                "EMP-034", "EMP-035", "EMP-045"],
    "DEP-005": ["EMP-006", "EMP-012", "EMP-046", "EMP-047", "EMP-048", "EMP-049",
                "EMP-050"],
    "DEP-006": ["EMP-004", "EMP-010", "EMP-014", "EMP-015", "EMP-016", "EMP-017",
                "EMP-036"],
}

RETAIL_DEPT_CODES = {"DEP-001", "DEP-003"}   # 7-day departments

# ------------------------------------------------------------------
# Named employees (demo + managers + scenario participants)
# ------------------------------------------------------------------
NAMED_EMPLOYEES = {
    "EMP-001": ("Sarah", "Mitchell", "Operations Specialist"),
    "EMP-002": ("John", "Carter", "Sales Representative"),
    "EMP-003": ("David", "Chen", "Senior Software Engineer"),
    "EMP-004": ("Emily", "Wilson", "HR Specialist"),
    "EMP-005": ("Daniel", "Okafor", "Support Lead"),
    "EMP-006": ("Grace", "Williams", "Financial Analyst"),
    "EMP-007": ("Robert", "Hayes", "Operations Manager"),
    "EMP-008": ("Lisa", "Park", "Sales Manager"),
    "EMP-009": ("Maria", "Garcia", "Engineering Manager"),
    "EMP-010": ("Thomas", "Brown", "HR Manager"),
    "EMP-011": ("Karen", "Johnson", "Customer Support Manager"),
    "EMP-012": ("Martin", "Torres", "Finance Manager"),
    # NOTE: no employee named "Michael" exists anywhere in the company
    # (EVL-005 requires a NOT-FOUND resolution for "Michael").
    "EMP-013": ("John", "Carter Jr.", "Sales Associate"),      # EVL-006 ambiguity
    "EMP-014": ("Omar", "Haddad", "HR Coordinator"),           # zero leave left
    "EMP-018": ("Ethan", "Brooks", "Shift Supervisor"),
    "EMP-019": ("Fatima", "Noor", "Logistics Specialist"),     # pre-approved leave 09-18
    "EMP-020": ("George", "Papas", "Warehouse Coordinator"),
    "EMP-021": ("Hana", "Suzuki", "Operations Associate"),
    "EMP-024": ("Priya", "Sharma", "Support Agent"),           # low workload (EVL-016)
    "EMP-025": ("Lucas", "Meyer", "Support Agent"),            # on leave (EVL-016)
    "EMP-030": ("Nina", "Petrova", "DevOps Engineer"),         # on leave 09-10
    "EMP-032": ("Ravi", "Iyer", "Software Engineer"),          # EVL-008 replacement
}

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn", "Avery",
    "Jamie", "Drew", "Sam", "Chris", "Pat", "Robin", "Dakota", "Skyler",
    "Reese", "Finley", "Rowan", "Sage", "River", "Blake", "Cameron", "Emery",
    "Harper", "Kai", "Logan", "Parker", "Peyton", "Remy", "Shiloh", "Tatum",
    "Bailey", "Charlie", "Devon", "Eden", "Frankie", "Gray", "Hayden", "Indigo",
]
LAST_NAMES = [
    "Adams", "Baker", "Clark", "Davis", "Evans", "Foster", "Green", "Harris",
    "Irwin", "Jones", "King", "Lee", "Martin", "Nelson", "Owens", "Perry",
    "Reed", "Smith", "Turner", "Underwood", "Vance", "White", "Xu", "Young",
    "Zimmerman", "Bennett", "Dixon", "Elliott", "Fletcher", "Grant", "Hughes",
    "Ingram", "James", "Kelly", "Lopez", "Nash", "Ortiz", "Palmer",
]
# First names that must never be generated again (demo/scenario staff).
RESERVED_FIRST_NAMES = {
    "Sarah", "John", "David", "Emily", "Daniel", "Grace", "Michael", "Maria",
    "Robert", "Lisa", "Thomas", "Karen", "Martin", "Omar", "Ethan", "Fatima",
    "Priya", "Lucas", "Nina", "Ravi",
}

JOB_TITLES_BY_DEPT = {
    "DEP-001": ["Operations Associate", "Warehouse Coordinator", "Logistics Specialist",
                "Inventory Clerk", "Shift Supervisor"],
    "DEP-002": ["Sales Associate", "Account Executive", "Sales Coordinator",
                "Retail Associate", "Business Development Rep"],
    "DEP-003": ["Support Agent", "Support Specialist", "Technical Support Agent",
                "Customer Success Agent", "Help Desk Analyst"],
    "DEP-004": ["Software Engineer", "QA Engineer", "DevOps Engineer",
                "Frontend Developer", "Backend Developer"],
    "DEP-005": ["Accounting Clerk", "Payroll Specialist", "Budget Analyst",
                "Accounts Payable Clerk", "Revenue Analyst"],
    "DEP-006": ["HR Coordinator", "Recruiter", "Benefits Administrator",
                "Training Specialist", "HR Generalist"],
}

# ------------------------------------------------------------------
# Leave balances: (annual_entitlement, used_days, remaining_days)
# ------------------------------------------------------------------
SPECIAL_BALANCES = {
    "EMP-001": (20, 12, 8),    # the canonical demo scenario (EVL-001/003/015/018)
    "EMP-002": (18, 15, 3),    # low balance -> EVL-013 conflicts with DEC-004
    "EMP-003": (22, 7, 15),
    "EMP-004": (15, 3, 12),
    "EMP-005": (18, 17, 1),    # 1 day left -> EVL-002 rejection
    "EMP-006": (20, 10, 10),
    "EMP-007": (25, 8, 17), "EMP-008": (25, 10, 15), "EMP-009": (25, 5, 20),
    "EMP-010": (25, 12, 13), "EMP-011": (25, 6, 19), "EMP-012": (25, 9, 16),
    "EMP-013": (15, 2, 13),
    "EMP-014": (15, 15, 0),    # zero leave
    "EMP-019": (20, 13, 7),
    "EMP-024": (20, 4, 16),
    "EMP-025": (20, 14, 6),
    "EMP-030": (20, 16, 4),    # low balance
}

HIRE_DATES = {
    "EMP-001": "2021-03-15", "EMP-002": "2020-08-01", "EMP-003": "2022-01-10",
    "EMP-004": "2023-05-22", "EMP-005": "2020-09-01", "EMP-006": "2021-11-08",
    "EMP-007": "2018-04-01", "EMP-008": "2017-07-15", "EMP-009": "2019-02-20",
    "EMP-010": "2016-01-10", "EMP-011": "2018-11-05", "EMP-012": "2017-09-12",
    "EMP-013": "2024-02-14", "EMP-014": "2022-06-06",
}

# ------------------------------------------------------------------
# Policies (POL-001..POL-010) — machine-readable rules + governance
# ------------------------------------------------------------------
POLICY_UUID_BASE = "d0000000-0000-0000-0000-0000000002{:02d}"

POLICIES = [
    {
        "policy_code": "POL-001", "category": "annual_leave_policy",
        "title": "Annual Leave Policy", "version": 1, "risk_level": "low",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "max_consecutive_days": 14,
            "allow_negative_balance": False,
            "blackout_periods": [
                {"start": "2026-11-23", "end": "2026-11-29",
                 "reason": "Peak retail season (Black Friday week)"}
            ],
            "blackout_action": "escalate",
            "description": "Employees cannot request more leave days than their "
                           "remaining annual balance. Leave requests that fall "
                           "inside a blackout period cannot be auto-approved.",
        },
        "approval_requirements": {
            "auto_approve_when": ["balance_sufficient", "notice_met",
                                  "coverage_maintained", "not_blackout"],
        },
    },
    {
        "policy_code": "POL-002", "category": "leave_notice_policy",
        "title": "Leave Notice Policy", "version": 1, "risk_level": "low",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "standard_notice_days": 3,
            "same_day_allowed": False,
            "late_notice_action": "reject",
            "description": "Standard leave requests must be submitted at least "
                           "3 days before the first requested date. Requests "
                           "with less notice are rejected (not escalated).",
        },
        "approval_requirements": {"auto_approve_when": ["notice_met"]},
    },
    {
        "policy_code": "POL-003", "category": "critical_coverage_policy",
        "title": "Critical Coverage Policy", "version": 1, "risk_level": "medium",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "enforce_minimum_coverage": True,
            "below_minimum_action": "escalate",
            "description": "A leave request cannot be automatically approved if "
                           "it causes department coverage to fall below the "
                           "required minimum. Coverage = scheduled employees "
                           "minus employees unavailable (LEAVE/SICK/OFF).",
        },
        "approval_requirements": {
            "escalate_when": ["coverage_below_minimum"],
            "approval_required": True,
        },
    },
    {
        "policy_code": "POL-004", "category": "task_reassignment_policy",
        "title": "Task Reassignment Policy", "version": 1, "risk_level": "medium",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "must_verify_availability": True,
            "require_same_department": True,
            "max_open_tasks_for_reassignee": 3,
            "description": "Tasks assigned to an employee who becomes unavailable "
                           "must be reassigned to an available, same-department "
                           "colleague with capacity, or explicitly reviewed by "
                           "the department manager.",
        },
        "approval_requirements": {"approval_required": True,
                                  "escalate_when": ["no_qualified_replacement"]},
    },
    {
        "policy_code": "POL-005", "category": "attendance_policy",
        "title": "Attendance Policy", "version": 1, "risk_level": "low",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "max_late_before_warning": 3,
            "review_window_days": 60,
            "escalation": "formal_warning_then_hr_review",
            "description": "More than 3 late arrivals within a 60-day window "
                           "triggers a formal warning followed by HR review.",
        },
        "approval_requirements": {"auto_report_when": ["attendance_lookup"]},
    },
    {
        "policy_code": "POL-006", "category": "disciplinary_action_policy",
        "title": "Disciplinary Action Policy", "version": 1, "risk_level": "high",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "progressive_discipline": True,
            "hr_approval_required": True,
            "autonomous_execution_blocked": True,
            "description": "Disciplinary actions follow progressive stages "
                           "(verbal, written, formal warning) and always "
                           "require HR approval. The agent may recommend but "
                           "never execute disciplinary actions.",
        },
        "approval_requirements": {"approval_required": True,
                                  "tier": 3},
    },
    {
        "policy_code": "POL-007", "category": "termination_policy",
        "title": "Termination Policy", "version": 1, "risk_level": "critical",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "agent_can_recommend_only": True,
            "autonomous_execution_blocked": True,
            "requires_hr_and_exec_approval": True,
            "investigation_required": True,
            "description": "Termination is a high-impact action. It MUST require "
                           "human approval. The agent can recommend termination "
                           "but can never autonomously execute it.",
        },
        "approval_requirements": {"approval_required": True,
                                  "tier": 3,
                                  "autonomous_execution": "blocked"},
    },
    {
        "policy_code": "POL-008", "category": "approval_authority_policy",
        "title": "Approval Authority Policy", "version": 1, "risk_level": "high",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "tier_1_auto": ["policy_query", "employee_status", "schedule_lookup",
                            "attendance_review"],
            "tier_2_approval": ["leave_request", "task_reassignment"],
            "tier_3_blocked": ["termination_request", "suspension_request"],
            "user_instructions_cannot_override_policy": True,
            "description": "Defines agent authority tiers: tier 1 informational "
                           "(auto), tier 2 standard consequential actions "
                           "(human approval), tier 3 high-impact actions "
                           "(blocked for autonomous execution).",
        },
        "approval_requirements": {"tier_map": {"tier_1": "auto",
                                               "tier_2": "human_approval",
                                               "tier_3": "blocked_autonomous"}},
    },
    {
        "policy_code": "POL-009", "category": "employee_data_access_policy",
        "title": "Employee Data Access Policy", "version": 1, "risk_level": "high",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "sensitive_fields": ["salary", "ssn", "medical_info",
                                 "disciplinary_records"],
            "requires_authorization": True,
            "description": "Sensitive employee information must only be exposed "
                           "when the requesting user has the appropriate "
                           "authorization level.",
        },
        "approval_requirements": {"approval_required": True,
                                  "escalate_when": ["unauthorized_data_request"]},
    },
    {
        "policy_code": "POL-010", "category": "emergency_operations_policy",
        "title": "Emergency Operations Policy", "version": 1, "risk_level": "high",
        "effective_from": "2026-01-01", "effective_until": None,
        "rules": {
            "minimum_staffing": 2,
            "suspension_of_leave_allowed": True,
            "requires_director_approval": True,
            "description": "During declared emergencies, minimum staffing of 2 "
                           "per operational department must be maintained; "
                           "leave may be recalled only with director approval.",
        },
        "approval_requirements": {"approval_required": True,
                                  "tier": 3},
    },
]

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _uuid(seed: str) -> str:
    """Deterministic UUIDv4-shaped id from an arbitrary string seed."""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def emp_uuid(emp_code: str) -> str:
    """EMP-001 -> c0000000-0000-0000-0000-000000000101 (stable mapping)."""
    n = int(emp_code.split("-")[1])
    return f"c0000000-0000-0000-0000-{100 + n:012d}"


def policy_uuid(policy_code: str) -> str:
    return POLICY_UUID_BASE.format(int(policy_code.split("-")[1]))


def dept_uuid(dept_code: str) -> str:
    return DEPT_ID_BY_CODE[dept_code]


# ------------------------------------------------------------------
# Employee generation (deterministic, 50 employees)
# ------------------------------------------------------------------

def gen_employees():
    rng = random.Random(RNG_SEED)
    dept_of = {}
    for dept_code, codes in DEPT_MEMBERSHIP.items():
        for c in codes:
            dept_of[c] = dept_code
    manager_codes = {d["manager_code"] for d in DEPARTMENTS}

    emps, used_names = [], set()
    for n in range(1, 51):
        code = f"EMP-{n:03d}"
        dept_code = dept_of[code]
        first, last, title = NAMED_EMPLOYEES.get(code, (None, None, None))
        if first is None:
            while True:
                first = rng.choice(FIRST_NAMES)
                last = rng.choice(LAST_NAMES)
                if first in RESERVED_FIRST_NAMES:
                    continue
                if (first, last) in used_names:
                    continue
                break
            used_names.add((first, last))
        if title is None:
            pool = JOB_TITLES_BY_DEPT[dept_code]
            title = pool[n % len(pool)]

        ent, used, rem = SPECIAL_BALANCES.get(code, (20, 3 + (n * 7) % 12, None))
        if rem is None:
            rem = ent - used
        status = "on_leave" if code == "EMP-044" else "active"
        if n <= 13 or code in manager_codes:
            etype = "full_time"
        else:
            etype = ["full_time", "full_time", "full_time", "part_time",
                     "contractor", "intern"][n % 6]
        hire = HIRE_DATES.get(code) or (
            f"{2018 + (n % 7)}-{(n % 12) + 1:02d}-{(n % 27) + 1:02d}")
        slug = lambda s: s.lower().replace(" ", "").replace(".", "")
        email = f"{slug(first)}.{slug(last)}@acmeretail.example"

        emps.append({
            "id": emp_uuid(code), "emp_code": code,
            "first_name": first, "last_name": last, "email": email,
            "job_title": title, "dept_code": dept_code,
            "department_id": dept_uuid(dept_code),
            "manager_id": emp_uuid(d["manager_code"])
            if (d := next((x for x in DEPARTMENTS
                           if x["dept_code"] == dept_code), None)) else None,
            "employment_status": status, "employment_type": etype,
            "hire_date": hire,
            "annual_entitlement": ent, "used_days": used, "remaining_days": rem,
        })

    # Department managers report to no one inside the simulation.
    by_code = {e["emp_code"]: e for e in emps}
    for d in DEPARTMENTS:
        by_code[d["manager_code"]]["manager_id"] = None
    return emps

# ------------------------------------------------------------------
# Schedules — coverage must be CALCULABLE, critical Fridays are explicit
# ------------------------------------------------------------------

# Exhaustive Operations staffing for the three scenario Fridays.
OPS_COVERAGE_SCENARIOS = {
    FRIDAY_NORMAL: {"WORKING": ["EMP-001", "EMP-018", "EMP-019", "EMP-020"]},
    FRIDAY_PEAK: {"WORKING": ["EMP-001", "EMP-018", "EMP-019"]},
    FRIDAY_TEAM_LEAVE: {"WORKING": ["EMP-001", "EMP-018", "EMP-021"],
                        "LEAVE": ["EMP-019"]},
}


def _build_overrides():
    """Explicit (emp_code, iso_date) -> schedule status overrides."""
    ov = {}
    # HR coverage scenario: only Emily Wilson (EMP-004) works 09-02..09-04.
    for iso in ("2026-09-02", "2026-09-03", "2026-09-04"):
        for code in DEPT_MEMBERSHIP["DEP-006"]:
            ov[(code, iso)] = "WORKING" if code == "EMP-004" else "OFF"
    # David Chen sick (EVL-008 reassignment day + EVL-011 no-replacement day).
    ov[("EMP-003", "2026-09-09")] = "SICK"
    ov[("EMP-003", "2026-09-10")] = "SICK"
    # Engineering has NO available replacement on 2026-09-10 (EVL-011).
    for code in DEPT_MEMBERSHIP["DEP-004"]:
        if code != "EMP-003":
            ov[(code, "2026-09-10")] = ("LEAVE" if code == "EMP-030" else "OFF")
    # Daniel Okafor + Lucas Meyer on leave (EVL-016).
    for iso in ("2026-09-14", "2026-09-15", "2026-09-16"):
        ov[("EMP-005", iso)] = "LEAVE"
        ov[("EMP-025", iso)] = "LEAVE"
    return ov


def _rest_days(emp_code: str):
    """Two deterministic rest days per retail employee. Scenario
    overrides always win, so rest days never affect critical Fridays."""
    n = int(emp_code.split("-")[1])
    return {n % 7, (n + 2) % 7}


def _shift_times(dow, status):
    start = time(10, 0) if dow >= 5 else time(9, 0)
    end = time(18, 0) if dow >= 5 else time(17, 0)
    return start.isoformat(), end.isoformat()


# Employees never given random SICK/LEAVE flavor (keeps scenarios exact).
_PROTECTED_CODES = {
    "EMP-001", "EMP-002", "EMP-003", "EMP-004", "EMP-005", "EMP-006",
    "EMP-007", "EMP-008", "EMP-009", "EMP-010", "EMP-011", "EMP-012",
    "EMP-013", "EMP-014", "EMP-018", "EMP-019", "EMP-020", "EMP-021",
    "EMP-024", "EMP-025", "EMP-030", "EMP-032",
}


def gen_schedules(emps):
    rng = random.Random(RNG_SEED)
    overrides = _build_overrides()
    flavor_window = (date(2026, 9, 2), date(2026, 9, 18))
    scheds = []
    d = SCHEDULE_START
    while d <= SCHEDULE_END:
        iso, dow = d.isoformat(), d.weekday()
        for e in emps:
            if e["employment_status"] != "active":
                continue
            code, dept = e["emp_code"], e["dept_code"]
            if dept == "DEP-001" and d in OPS_COVERAGE_SCENARIOS:
                sc = OPS_COVERAGE_SCENARIOS[d]
                if code in sc.get("WORKING", []):
                    st = "WORKING"
                elif code in sc.get("LEAVE", []):
                    st = "LEAVE"
                else:
                    st = "OFF"
            elif (code, iso) in overrides:
                st = overrides[(code, iso)]
            else:
                if dept in RETAIL_DEPT_CODES:
                    st = "OFF" if dow in _rest_days(code) else "WORKING"
                else:
                    st = "WORKING" if dow < 5 else "OFF"
                if (st == "WORKING" and code not in _PROTECTED_CODES
                        and not (flavor_window[0] <= d <= flavor_window[1])
                        and rng.random() < 0.02):
                    st = rng.choice(["SICK", "LEAVE"])
            ss, se = _shift_times(dow, st)
            scheds.append({
                "id": _uuid(f"{e['id']}-{iso}"),
                "employee_id": e["id"], "emp_code": code,
                "shift_date": iso, "shift_start": ss, "shift_end": se,
                "shift_type": "standard", "status": st,
                "dept_code": dept, "department_id": e["department_id"],
            })
        d += timedelta(days=1)
    return scheds

# ------------------------------------------------------------------
# Tasks (TASK-001..) — reassignment scenarios live here
# ------------------------------------------------------------------

def gen_tasks(emps):
    rng = random.Random(RNG_SEED)
    by_code = {e["emp_code"]: e for e in emps}
    tasks = []

    def add(code, title, description, priority, status, due):
        nonlocal counter
        counter += 1
        e = by_code[code]
        tasks.append({
            "id": f"10000000-0000-0000-0000-{counter:012d}",
            "task_code": f"TASK-{counter:03d}",
            "title": title, "description": description,
            "employee_id": e["id"], "emp_code": code,
            "department_id": e["department_id"], "dept_code": e["dept_code"],
            "priority": priority, "status": status,
            "due_date": due.isoformat() if isinstance(due, date) else due,
        })

    counter = 0
    add("EMP-003", "API Gateway Migration",
        "Lead the migration of the storefront API to microservices.",
        "high", "in_progress", BASE_DATE + timedelta(days=14))            # TASK-001 (EVL-008)
    add("EMP-003", "Payment Gateway Hotfix",
        "On-call hotfix for payment gateway latency. Requires the on-call engineer.",
        "critical", "pending", ENG_NO_REPLACE)                            # TASK-002 (EVL-011)
    add("EMP-005", "Escalation Backlog Review",
        "Review the 47 open customer escalations before the weekly review.",
        "critical", "in_progress", BASE_DATE + timedelta(days=17))        # TASK-003 (EVL-016)
    add("EMP-001", "Q3 Inventory Audit",
        "Complete the quarterly inventory audit for the central warehouse.",
        "high", "in_progress", BASE_DATE + timedelta(days=7))             # TASK-004
    add("EMP-024", "Support Queue Training",
        "Complete the new support queue routing training module.",
        "low", "pending", BASE_DATE + timedelta(days=30))                 # TASK-005 (EVL-016 capacity)
    add("EMP-025", "Ticket Triage Backlog",
        "Clear the ticket triage backlog from last week.",
        "medium", "in_progress", BASE_DATE + timedelta(days=12))
    add("EMP-025", "CSAT Survey Analysis",
        "Analyze the August CSAT survey results.",
        "low", "pending", BASE_DATE + timedelta(days=20))
    # Maria Garcia is deliberately at capacity (3 open tasks).
    add("EMP-009", "Platform Reliability Review",
        "Review platform reliability metrics and on-call fatigue.",
        "high", "in_progress", BASE_DATE + timedelta(days=21))
    add("EMP-009", "Backend Interview Loop",
        "Run the backend engineer interview loop for Q4 hiring.",
        "medium", "pending", BASE_DATE + timedelta(days=18))
    add("EMP-009", "On-Call Rota Planning",
        "Plan the engineering on-call rota for Q4.",
        "medium", "in_progress", BASE_DATE + timedelta(days=25))

    covered = {t["emp_code"] for t in tasks}
    templates = [
        ("Monthly Sales Report", "Prepare the monthly sales performance report.", "medium"),
        ("Compliance Training", "Complete the annual compliance training.", "low"),
        ("Vendor Contract Review", "Review upcoming vendor contract renewals.", "medium"),
        ("Budget Variance Analysis", "Analyze Q3 budget variance by cost center.", "high"),
        ("System Maintenance Window", "Prepare the weekend maintenance window plan.", "medium"),
        ("Client Onboarding", "Onboard the new wholesale client.", "high"),
        ("Documentation Update", "Update internal runbook documentation.", "low"),
        ("Access Audit", "Review system access permissions.", "medium"),
    ]
    ti = 0
    for e in emps:
        if e["emp_code"] in covered_codes(tasks) or e["employment_status"] != "active":
            continue
        k = rng.choice([0, 0, 1, 1, 2])
        for _ in range(k):
            t = templates[ti % len(templates)]
            add(e["emp_code"], t[0], t[1], t[2],
                rng.choice(["pending", "in_progress", "completed", "blocked"]),
                BASE_DATE + timedelta(days=1 + (counter % 28)))
            ti += 1
    return tasks


def covered_codes(tasks):
    return {t["emp_code"] for t in tasks}

# ------------------------------------------------------------------
# Attendance history (ATT-0001..) — supports attendance evaluation cases
# ------------------------------------------------------------------

def gen_attendance(emps):
    rng = random.Random(RNG_SEED)
    by_code = {e["emp_code"]: e for e in emps}
    att = []
    counter = 0

    def add(code, d, status, scheduled, actual, notes):
        nonlocal counter
        counter += 1
        att.append({
            "id": _uuid(f"att-{code}-{d.isoformat()}"),
            "attendance_code": f"ATT-{counter:04d}",
            "employee_id": by_code[code]["id"], "emp_code": code,
            "date": d.isoformat(), "scheduled_start": scheduled,
            "actual_start": actual, "status": status, "notes": notes,
        })

    # John Carter: 4 lates + 2 formal warnings inside the 60-day window
    # (EVL-010 lookup; EVL-017 progressive-discipline chain with POL-005/006).
    for d, mins in [(date(2026, 8, 7), 22), (date(2026, 8, 14), 31),
                    (date(2026, 8, 21), 14), (date(2026, 8, 25), 47)]:
        add("EMP-002", d, "late", "09:00", f"09:{mins:02d}", f"{mins} min late")
    add("EMP-002", date(2026, 7, 30), "formal_warning", "09:00", "09:00",
        "Formal warning issued after repeated late arrivals.")
    add("EMP-002", date(2026, 8, 18), "formal_warning", "09:00", "09:00",
        "Second formal warning; next step is HR review.")

    # Everyone else: deterministic mostly-present weekday history.
    d = HISTORY_START
    while d <= HISTORY_END:
        if d.weekday() < 5:
            for e in emps:
                code = e["emp_code"]
                if e["employment_status"] != "active" or code == "EMP-002":
                    continue
                h = int(_uuid(f"attflavor-{code}-{d.isoformat()}")[:8], 16)
                if h % 23 == 0:
                    add(code, d, "late", "09:00", f"09:{h % 40 + 5:02d}",
                        "Late arrival")
                elif h % 29 == 0:
                    add(code, d, "absent", "09:00", None, "Unplanned absence")
                elif h % 31 == 0:
                    add(code, d, "leave", "09:00", None, "Approved leave")
                else:
                    add(code, d, "present", "09:00", "08:55", None)
        d += timedelta(days=1)
    return att


# ------------------------------------------------------------------
# Historical decisions (DEC-001..) — precedents, NOT policy
# ------------------------------------------------------------------

def gen_historical(emps):
    by_code = {e["emp_code"]: e for e in emps}

    def add(n, code, request_type, decision, reason, decided_by, when):
        return {
            "id": _uuid(f"hist-dec-{n:03d}"),
            "decision_code": f"DEC-{n:03d}",
            "employee_id": by_code[code]["id"] if code else None,
            "emp_code": code,
            "request_type": request_type, "decision": decision,
            "reason": reason, "decided_by": decided_by, "created_at": when,
        }

    return [
        add(1, "EMP-001", "leave_request", "approved",
            "Approved after manager review; balance and team coverage were "
            "verified at the time of the request.",
            "Robert Hayes", "2026-07-27 10:00:00+00"),
        add(2, "EMP-001", "leave_request", "rejected",
            "Rejected due to insufficient leave balance at the time of the "
            "request.",
            "Robert Hayes", "2026-07-02 10:00:00+00"),
        add(3, "EMP-002", "leave_request", "escalated",
            "Escalated because of a coverage conflict during peak sales week.",
            "Lisa Park", "2026-07-17 10:00:00+00"),
        # EVL-013: conflicting precedent — current policy must win.
        add(4, "EMP-002", "leave_request", "approved",
            "Manager override: approved despite insufficient remaining "
            "balance. Retained for record only; this does NOT change current "
            "company policy.",
            "Lisa Park", "2026-05-15 10:00:00+00"),
        add(5, "EMP-003", "task_reassignment", "approved",
            "Reassigned to Maria Garcia while David Chen was on sick leave.",
            "Maria Garcia", "2026-08-10 10:00:00+00"),
        add(6, "EMP-001", "schedule_swap", "approved",
            "Shift swap with a colleague approved by the Operations Manager.",
            "Robert Hayes", "2026-08-05 10:00:00+00"),
    ]

# ------------------------------------------------------------------
# Coverage simulation (mirrors the team_coverage SQL view)
# ------------------------------------------------------------------

def coverage_for(scheds, emps, dept_code, d):
    """Return (scheduled, effective, rows) for a department/date.

    effective = rows with status WORKING (LEAVE/SICK/OFF/HOLIDAY excluded),
    matching the team_coverage view definition."""
    active = {e["id"] for e in emps if e["employment_status"] == "active"}
    rows = [s for s in scheds
            if s["shift_date"] == d.isoformat()
            and s["dept_code"] == dept_code
            and s["employee_id"] in active]
    effective = sum(1 for s in rows if s["status"] == "WORKING")
    return len(rows), effective, rows


# ------------------------------------------------------------------
# SQL emission for seed/04_seed_workforce.sql
# ------------------------------------------------------------------

def _q(s):
    return str(s).replace("'", "''")


def emit_workforce_sql() -> str:
    emps = gen_employees()
    scheds = gen_schedules(emps)
    tasks = gen_tasks(emps)
    att = gen_attendance(emps)
    hist = gen_historical(emps)
    year = BASE_DATE.year

    L = []
    A = L.append
    A("-- seed/04_seed_workforce.sql - AUTO-GENERATED by backend/data/generator.py")
    A("-- DO NOT EDIT BY HAND — regenerate with: python -m backend.data.generator")
    A(f"-- Employees: {len(emps)}, Schedules: {len(scheds)}, Tasks: {len(tasks)}, "
      f"Attendance: {len(att)}, Historical: {len(hist)}, Policies: {len(POLICIES)}")
    A(f"-- Simulation anchor (BASE_DATE): {BASE_DATE.isoformat()}")
    A("")
    A("BEGIN;")
    A(f"INSERT INTO businesses (id, name) VALUES ('{BUSINESS_ID}', "
      f"'{_q(BUSINESS_NAME)}') ON CONFLICT (id) DO NOTHING;")
    A("")
    A("-- Departments")
    for d in DEPARTMENTS:
        A(f"INSERT INTO departments (id, business_id, name, minimum_coverage_headcount, "
          f"dept_code) VALUES ('{d['id']}', '{BUSINESS_ID}', '{_q(d['name'])}', "
          f"{d['min_coverage']}, '{d['dept_code']}') ON CONFLICT (id) DO NOTHING;")
    A("")
    A("-- Employees (manager_id set in a second pass to respect self-FK order)")
    for e in emps:
        A(f"INSERT INTO employees (id, business_id, department_id, emp_code, first_name, "
          f"last_name, name, email, role, status, employment_type, manager_id, hire_date) "
          f"VALUES ('{e['id']}', '{BUSINESS_ID}', '{e['department_id']}', '{e['emp_code']}', "
          f"'{_q(e['first_name'])}', '{_q(e['last_name'])}', "
          f"'{_q(e['first_name'] + ' ' + e['last_name'])}', '{e['email']}', "
          f"'{_q(e['job_title'])}', '{e['employment_status']}', '{e['employment_type']}', "
          f"NULL, '{e['hire_date']}') ON CONFLICT (id) DO NOTHING;")
    A("")
    A("-- Reporting lines (second pass)")
    for e in emps:
        if e["manager_id"]:
            A(f"UPDATE employees SET manager_id = '{e['manager_id']}' "
              f"WHERE id = '{e['id']}';")
    A("")
    A("-- Department managers")
    for d in DEPARTMENTS:
        A(f"UPDATE departments SET manager_id = '{emp_uuid(d['manager_code'])}' "
          f"WHERE id = '{d['id']}';")
    A("")
    A("-- Leave balances")
    for e in emps:
        A(f"INSERT INTO leave_balances (employee_id, leave_type, available_days, used_days, "
          f"annual_entitlement, remaining_days, year) VALUES ('{e['id']}', 'annual', "
          f"{e['remaining_days']}, {e['used_days']}, {e['annual_entitlement']}, "
          f"{e['remaining_days']}, {year}) ON CONFLICT (employee_id, leave_type, year) "
          f"DO UPDATE SET available_days = EXCLUDED.available_days, "
          f"used_days = EXCLUDED.used_days, annual_entitlement = EXCLUDED.annual_entitlement, "
          f"remaining_days = EXCLUDED.remaining_days;")
    A("")
    A("-- Policies")
    for p in POLICIES:
        rules = json.dumps(p["rules"]).replace("'", "''")
        appr = json.dumps(p["approval_requirements"]).replace("'", "''")
        until = f"'{p['effective_until']}'" if p["effective_until"] else "NULL"
        A(f"INSERT INTO company_policies (id, business_id, category, title, content, rules, "
          f"version, is_active, policy_code, risk_level, effective_from, effective_until, "
          f"approval_requirements) VALUES ('{policy_uuid(p['policy_code'])}', '{BUSINESS_ID}', "
          f"'{_q(p['category'])}', '{_q(p['title'])}', '{_q(p['rules']['description'])}', "
          f"'{rules}'::jsonb, {p['version']}, TRUE, '{p['policy_code']}', "
          f"'{p['risk_level']}', '{p['effective_from']}', {until}, '{appr}'::jsonb) "
          f"ON CONFLICT (id) DO NOTHING;")
    A("")
    A("-- Schedules")
    for s in scheds:
        A(f"INSERT INTO schedules (id, employee_id, shift_date, shift_start, shift_end, "
          f"shift_type, status) VALUES ('{s['id']}', '{s['employee_id']}', '{s['shift_date']}', "
          f"'{s['shift_start']}', '{s['shift_end']}', '{s['shift_type']}', '{s['status']}') "
          f"ON CONFLICT (employee_id, shift_date) DO NOTHING;")

    A("")
    A("-- Tasks")
    for t in tasks:
        A(f"INSERT INTO tasks (id, business_id, assigned_to, task_code, title, description, "
          f"priority, due_date, status) VALUES ('{t['id']}', '{BUSINESS_ID}', "
          f"'{t['employee_id']}', '{t['task_code']}', '{_q(t['title'])}', "
          f"'{_q(t['description'])}', '{t['priority']}', '{t['due_date']}', "
          f"'{t['status']}') ON CONFLICT (id) DO NOTHING;")
    A("")
    A("-- Attendance records")
    for a in att:
        act = f"'{a['actual_start']}'" if a["actual_start"] else "NULL"
        nt = f"'{_q(a['notes'])}'" if a["notes"] else "NULL"
        A(f"INSERT INTO attendance_records (id, employee_id, attendance_code, date, "
          f"scheduled_start, actual_start, status, notes) VALUES ('{a['id']}', "
          f"'{a['employee_id']}', '{a['attendance_code']}', '{a['date']}', "
          f"'{a['scheduled_start']}', {act}, '{a['status']}', {nt}) "
          f"ON CONFLICT (employee_id, date) DO NOTHING;")
    A("")
    A("-- Historical decisions (precedents — never policy)")
    for h in hist:
        A(f"INSERT INTO historical_decisions (id, business_id, employee_id, decision_code, "
          f"request_type, decision, reason, decided_by, created_at) VALUES ('{h['id']}', "
          f"'{BUSINESS_ID}', '{h['employee_id']}', '{h['decision_code']}', "
          f"'{h['request_type']}', '{h['decision']}', '{_q(h['reason'])}', "
          f"'{_q(h['decided_by'])}', '{h['created_at']}') ON CONFLICT (id) DO NOTHING;")
    A("")
    A("COMMIT;")
    return "\n".join(L) + "\n"


def main():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    seed_dir = os.path.join(root, "database", "seed")
    os.makedirs(seed_dir, exist_ok=True)
    out = os.path.join(seed_dir, "04_seed_workforce.sql")
    sql = emit_workforce_sql()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(sql)
    print(f"wrote {out} ({len(sql.splitlines())} lines)")


if __name__ == "__main__":
    main()

