#!/usr/bin/env python3
"""
validate.py — Data integrity validation for the OpsPilot synthetic world.

Two layers:
  * validate_world()     — pure-Python checks over the generated data
                           (no database required). Used by seed.py and CI.
  * validate_database()  — the same checks against the seeded database
                           (takes a psycopg2 cursor-like object), plus
                           FK-orphan checks, the team_coverage view values
                           and the frozen evaluation-case distribution.

The seed process FAILS LOUDLY (non-zero exit) if any check fails.
"""

from typing import Dict, List, Tuple

from backend.data.generator import (
    FRIDAY_NORMAL, FRIDAY_PEAK, FRIDAY_TEAM_LEAVE, ENG_NO_REPLACE,
    DANIEL_LEAVE_START, DANIEL_LEAVE_END, BLACKOUT_START, BLACKOUT_END,
    DEPARTMENTS, DEPT_MEMBERSHIP, POLICIES, coverage_for,
    gen_attendance, gen_employees, gen_historical, gen_schedules, gen_tasks,
)


def validate_departments() -> List[str]:
    errors = []
    if len(DEPARTMENTS) != 6:
        errors.append(f"Expected 6 departments, got {len(DEPARTMENTS)}")
    codes = [d["dept_code"] for d in DEPARTMENTS]
    if codes != [f"DEP-{i:03d}" for i in range(1, 7)]:
        errors.append(f"Department codes wrong: {codes}")
    expected_cov = {"DEP-001": 3, "DEP-002": 2, "DEP-003": 4,
                    "DEP-004": 2, "DEP-005": 2, "DEP-006": 1}
    for d in DEPARTMENTS:
        if d["min_coverage"] != expected_cov[d["dept_code"]]:
            errors.append(f"{d['dept_code']} min coverage "
                          f"{d['min_coverage']} != {expected_cov[d['dept_code']]}")
    total = sum(len(v) for v in DEPT_MEMBERSHIP.values())
    if total != 50:
        errors.append(f"Department membership totals {total}, expected 50")
    flat = [c for v in DEPT_MEMBERSHIP.values() for c in v]
    if len(set(flat)) != 50:
        errors.append("Employees appear in more than one department")
    return errors


def validate_employees(emps: List[Dict]) -> List[str]:
    errors = []
    if len(emps) != 50:
        errors.append(f"Expected 50 employees, got {len(emps)}")
    codes = [e["emp_code"] for e in emps]
    if codes != [f"EMP-{i:03d}" for i in range(1, 51)]:
        errors.append("Employee codes are not exactly EMP-001..EMP-050")
    ids = {e["id"] for e in emps}
    by_code = {e["emp_code"]: e for e in emps}

    required = ("id", "emp_code", "first_name", "last_name", "email",
                "job_title", "department_id", "employment_status",
                "employment_type", "hire_date", "annual_entitlement",
                "used_days", "remaining_days")
    for e in emps:
        for f in required:
            if f not in e or (e[f] is None and f != "manager_id"):
                errors.append(f"{e.get('emp_code', '?')} missing/None field: {f}")
        if e["manager_id"] and e["manager_id"] not in ids:
            errors.append(f"{e['emp_code']} has unknown manager_id")
        if e["remaining_days"] < 0 or e["used_days"] < 0:
            errors.append(f"{e['emp_code']} negative balance values")
        if e["annual_entitlement"] - e["used_days"] != e["remaining_days"]:
            errors.append(f"{e['emp_code']} balance inconsistent")

    demo = {"EMP-001": ("Sarah", "Mitchell", "Operations Specialist"),
            "EMP-002": ("John", "Carter", "Sales Representative"),
            "EMP-003": ("David", "Chen", "Senior Software Engineer"),
            "EMP-004": ("Emily", "Wilson", "HR Specialist"),
            "EMP-005": ("Daniel", "Okafor", "Support Lead"),
            "EMP-006": ("Grace", "Williams", "Financial Analyst")}
    for code, (fn, ln, role) in demo.items():
        e = by_code.get(code)
        if not e:
            errors.append(f"Demo employee {code} missing")
        elif (e["first_name"], e["last_name"], e["job_title"]) != (fn, ln, role):
            errors.append(f"{code} identity mismatch: "
                          f"{e['first_name']} {e['last_name']} / {e['job_title']}")

    # Frozen leave-balance scenarios
    if by_code["EMP-001"]["remaining_days"] != 8 or \
       by_code["EMP-001"]["annual_entitlement"] != 20 or \
       by_code["EMP-001"]["used_days"] != 12:
        errors.append("Sarah Mitchell balance must be 20/12/8")
    if by_code["EMP-005"]["remaining_days"] != 1:
        errors.append("Daniel Okafor must have exactly 1 remaining day")
    if by_code["EMP-014"]["remaining_days"] != 0:
        errors.append("EMP-014 must have zero remaining leave")

    # Adversarial / ambiguity preconditions
    if [e for e in emps if e["first_name"].lower() == "michael"]:
        errors.append("No employee named Michael may exist")
    johns = [e for e in emps if e["first_name"] == "John"]
    if len(johns) != 2:
        errors.append(f"Expected exactly 2 Johns, got {len(johns)}")

    for d in DEPARTMENTS:
        m = by_code[d["manager_code"]]
        if m["dept_code"] != d["dept_code"]:
            errors.append(f"Manager {d['manager_code']} not in {d['dept_code']}")
    return errors

def validate_policies() -> List[str]:
    errors = []
    if len(POLICIES) != 10:
        errors.append(f"Expected 10 policies, got {len(POLICIES)}")
    codes = {p["policy_code"] for p in POLICIES}
    if codes != {f"POL-{i:03d}" for i in range(1, 11)}:
        errors.append(f"Policy codes wrong: {sorted(codes)}")
    by = {p["policy_code"]: p for p in POLICIES}
    checks = [
        ("POL-001", ("allow_negative_balance", False)),
        ("POL-002", ("standard_notice_days", 3)),
        ("POL-003", ("enforce_minimum_coverage", True)),
        ("POL-004", ("must_verify_availability", True)),
        ("POL-005", ("max_late_before_warning", 3)),
        ("POL-006", ("autonomous_execution_blocked", True)),
        ("POL-007", ("agent_can_recommend_only", True)),
        ("POL-008", ("user_instructions_cannot_override_policy", True)),
        ("POL-009", ("requires_authorization", True)),
        ("POL-010", ("minimum_staffing", 2)),
    ]
    for code, (key, expected) in checks:
        if by[code]["rules"].get(key) != expected:
            errors.append(f"{code}.{key} rule mismatch")
    if by["POL-007"]["approval_requirements"].get("autonomous_execution") != "blocked":
        errors.append("POL-007 must block autonomous execution")
    bp = by["POL-001"]["rules"]["blackout_periods"][0]
    if bp["start"] != BLACKOUT_START.isoformat() or bp["end"] != BLACKOUT_END.isoformat():
        errors.append("POL-001 blackout period mismatch")
    return errors


def validate_schedules(emps, scheds) -> List[str]:
    errors = []
    if len(scheds) < 1500:
        errors.append(f"Too few schedule rows: {len(scheds)}")
    emp_ids = {e["id"] for e in emps}
    for s in scheds:
        if s["employee_id"] not in emp_ids:
            errors.append(f"Schedule references unknown employee")
        if s["status"] not in ("WORKING", "OFF", "LEAVE", "SICK", "HOLIDAY"):
            errors.append(f"Bad schedule status {s['status']}")

    def eff(d, dept):
        return coverage_for(scheds, emps, dept, d)[1]

    # The three Operations Fridays (frozen coverage math)
    if eff(FRIDAY_NORMAL, "DEP-001") != 4:
        errors.append("2026-09-04 Operations effective coverage must be 4 (EVL-001)")
    if eff(FRIDAY_PEAK, "DEP-001") != 3:
        errors.append("2026-09-11 Operations effective coverage must be 3 (EVL-003/007/018)")
    if eff(FRIDAY_TEAM_LEAVE, "DEP-001") != 3:
        errors.append("2026-09-18 Operations effective coverage must be 3 (EVL-015)")
    if not any(s["emp_code"] == "EMP-019" and s["status"] == "LEAVE"
               for s in scheds if s["shift_date"] == "2026-09-18"
               and s["dept_code"] == "DEP-001"):
        errors.append("EMP-019 must be on LEAVE on 2026-09-18")

    # David Chen sick + no engineering replacement on 2026-09-10
    for d in ("2026-09-09", "2026-09-10"):
        row = next((s for s in scheds if s["shift_date"] == d
                    and s["emp_code"] == "EMP-003"), None)
        if not row or row["status"] != "SICK":
            errors.append(f"David Chen must be SICK on {d}")
    if eff(ENG_NO_REPLACE, "DEP-004") != 0:
        errors.append("Engineering coverage on 2026-09-10 must be 0 (EVL-011)")
    ravi = next((s for s in scheds if s["shift_date"] == "2026-09-09"
                 and s["emp_code"] == "EMP-032"), None)
    if not ravi or ravi["status"] != "WORKING":
        errors.append("EMP-032 must be WORKING on 2026-09-09 (EVL-008)")

    # Daniel on leave + candidates for EVL-016
    for d in ("2026-09-14", "2026-09-15", "2026-09-16"):
        row = next((s for s in scheds if s["shift_date"] == d
                    and s["emp_code"] == "EMP-005"), None)
        if not row or row["status"] != "LEAVE":
            errors.append(f"Daniel Okafor must be on LEAVE on {d}")
    priya = next((s for s in scheds if s["shift_date"] == "2026-09-14"
                  and s["emp_code"] == "EMP-024"), None)
    if not priya or priya["status"] != "WORKING":
        errors.append("EMP-024 must be WORKING on 2026-09-14 (EVL-016)")

    # HR single-coverage window (EVL-014)
    import datetime as _dt
    for d in ("2026-09-02", "2026-09-03", "2026-09-04"):
        if eff(_dt.date.fromisoformat(d), "DEP-006") != 1:
            errors.append(f"HR effective coverage on {d} must be 1 (EVL-014)")

    sarah = next(s for s in scheds if s["shift_date"] == "2026-09-04"
                 and s["emp_code"] == "EMP-001")
    if sarah["status"] != "WORKING":
        errors.append("Sarah must be scheduled WORKING on 2026-09-04")
    return errors

def validate_tasks_attendance_history(emps, tasks, att, hist) -> List[str]:
    errors = []
    emp_ids = {e["id"] for e in emps}
    for t in tasks:
        if t["employee_id"] not in emp_ids:
            errors.append(f"Task {t.get('task_code')} references unknown employee")
    tcodes = {t["task_code"] for t in tasks}
    for need in ("TASK-001", "TASK-002", "TASK-003"):
        if need not in tcodes:
            errors.append(f"Missing scenario task {need}")
    t1 = next(t for t in tasks if t["task_code"] == "TASK-001")
    t3 = next(t for t in tasks if t["task_code"] == "TASK-003")
    if t1["emp_code"] != "EMP-003":
        errors.append("TASK-001 must belong to David Chen")
    if t3["emp_code"] != "EMP-005":
        errors.append("TASK-003 must belong to Daniel Okafor")

    if len(att) < 300:
        errors.append(f"Too few attendance records: {len(att)}")
    for a in att:
        if a["employee_id"] not in emp_ids:
            errors.append(f"Attendance {a['attendance_code']} references unknown employee")
    john = [a for a in att if a["emp_code"] == "EMP-002"]
    lates = [a for a in john if a["status"] == "late"]
    warns = [a for a in john if a["status"] == "formal_warning"]
    if len(lates) != 4 or len(warns) != 2:
        errors.append(f"John Carter attendance must be 4 lates + 2 warnings "
                      f"(got {len(lates)}/{len(warns)})")

    if len(hist) != 6:
        errors.append(f"Expected 6 historical decisions, got {len(hist)}")
    dcs = {h["decision_code"] for h in hist}
    if dcs != {f"DEC-{i:03d}" for i in range(1, 7)}:
        errors.append(f"Historical decision codes wrong: {sorted(dcs)}")
    dec4 = next(h for h in hist if h["decision_code"] == "DEC-004")
    if "override" not in dec4["reason"].lower():
        errors.append("DEC-004 must record the manager-override conflict")
    for h in hist:
        if h["employee_id"] and h["employee_id"] not in emp_ids:
            errors.append(f"{h['decision_code']} references unknown employee")
    return errors


def validate_evaluation_cases(emps) -> List[str]:
    """Every case must reference existing employees/policies (no impossible
    references) — the frozen ground truth must resolve against the world."""
    from backend.evaluation.cases import get_all_cases
    from backend.data.generator import NAMED_EMPLOYEES
    errors = []
    codes = {e["emp_code"] for e in emps}
    pol_codes = {p["policy_code"] for p in POLICIES}
    for c in get_all_cases():
        if c.get("employee_code") and c["employee_code"] not in codes:
            errors.append(f"{c['case_id']} references unknown employee "
                          f"{c['employee_code']}")
        for p in c["expected_policy_ids"]:
            if p not in pol_codes:
                errors.append(f"{c['case_id']} references unknown policy {p}")
        # Scenario-specific sanity
        if c["case_id"] == "EVL-020":
            if c["employee_code"] != "EMP-003":
                errors.append("EVL-020 must target David Chen (EMP-003)")
        if c["case_id"] == "EVL-019":
            if c["employee_code"] != "EMP-005":
                errors.append("EVL-019 must target Daniel Okafor (EMP-005)")
    # Named employees used by the ambiguous/unknown cases
    if "Michael" in {v[0] for v in NAMED_EMPLOYEES.values()}:
        errors.append("A named employee called Michael exists (breaks EVL-005)")
    return errors


def validate_world() -> Tuple[bool, List[str], Dict]:
    emps = gen_employees()
    scheds = gen_schedules(emps)
    tasks = gen_tasks(emps)
    att = gen_attendance(emps)
    hist = gen_historical(emps)
    sections = [
        ("Departments", validate_departments),
        ("Employees", lambda: validate_employees(emps)),
        ("Policies", validate_policies),
        ("Schedules/Coverage", lambda: validate_schedules(emps, scheds)),
        ("Tasks/Attendance/History",
         lambda: validate_tasks_attendance_history(emps, tasks, att, hist)),
        ("Evaluation cases", lambda: validate_evaluation_cases(emps)),
    ]
    all_errors: List[str] = []
    for name, fn in sections:
        errs = fn()
        if errs:
            all_errors.extend(f"[{name}] {e}" for e in errs)
    report = {
        "employees": len(emps), "departments": len(DEPARTMENTS),
        "policies": len(POLICIES), "schedules": len(scheds),
        "tasks": len(tasks), "attendance_records": len(att),
        "historical_decisions": len(hist),
        "coverage_fri_0904": coverage_for(scheds, emps, "DEP-001", FRIDAY_NORMAL)[1],
        "coverage_fri_0911": coverage_for(scheds, emps, "DEP-001", FRIDAY_PEAK)[1],
        "coverage_fri_0918": coverage_for(scheds, emps, "DEP-001", FRIDAY_TEAM_LEAVE)[1],
    }
    return (not all_errors), all_errors, report

# ------------------------------------------------------------------
# Database-level validation (run AFTER migrations + seeds)
# ------------------------------------------------------------------

def validate_database(cur) -> Tuple[bool, List[str], Dict]:
    """cur: psycopg2 cursor-like (execute + fetchone/fetchall)."""
    errors = []

    def one(sql):
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None

    def check(name, actual, expected):
        if actual != expected:
            errors.append(f"DB {name}: expected {expected}, got {actual}")

    check("businesses", one("SELECT COUNT(*) FROM businesses"), 1)
    check("departments", one("SELECT COUNT(*) FROM departments"), 6)
    check("employees", one("SELECT COUNT(*) FROM employees"), 50)
    check("leave_balances", one("SELECT COUNT(*) FROM leave_balances"), 50)
    check("company_policies", one("SELECT COUNT(*) FROM company_policies"), 10)
    check("historical_decisions", one("SELECT COUNT(*) FROM historical_decisions"), 6)
    check("evaluation_cases", one("SELECT COUNT(*) FROM evaluation_cases"), 20)
    if one("SELECT COUNT(*) FROM schedules") < 1500:
        errors.append("DB schedules: too few rows")
    if one("SELECT COUNT(*) FROM attendance_records") < 300:
        errors.append("DB attendance_records: too few rows")

    # FK orphans (defensive — the schema should already enforce this)
    orphans = [
        ("schedules", "SELECT COUNT(*) FROM schedules s LEFT JOIN employees e "
                      "ON e.id = s.employee_id WHERE e.id IS NULL"),
        ("tasks", "SELECT COUNT(*) FROM tasks t LEFT JOIN employees e "
                  "ON e.id = t.assigned_to WHERE t.assigned_to IS NOT NULL "
                  "AND e.id IS NULL"),
        ("leave_balances", "SELECT COUNT(*) FROM leave_balances lb LEFT JOIN "
                           "employees e ON e.id = lb.employee_id WHERE e.id IS NULL"),
        ("attendance", "SELECT COUNT(*) FROM attendance_records a LEFT JOIN "
                       "employees e ON e.id = a.employee_id WHERE e.id IS NULL"),
    ]
    for name, sql in orphans:
        n = one(sql)
        if n:
            errors.append(f"DB orphan rows in {name}: {n}")

    # Leave balances internally consistent
    bad = one("SELECT COUNT(*) FROM leave_balances "
              "WHERE remaining_days <> annual_entitlement - used_days "
              "OR remaining_days < 0")
    if bad:
        errors.append(f"DB leave_balances inconsistent rows: {bad}")

    # Sarah's frozen scenario
    sarah = one("SELECT lb.remaining_days FROM leave_balances lb "
                "JOIN employees e ON e.id = lb.employee_id "
                "WHERE e.emp_code = 'EMP-001' AND leave_type = 'annual'")
    if sarah != 8:
        errors.append(f"DB Sarah (EMP-001) remaining_days must be 8, got {sarah}")

    # Ambiguity preconditions
    if one("SELECT COUNT(*) FROM employees WHERE lower(first_name) = 'michael'") != 0:
        errors.append("DB: an employee named Michael exists (breaks EVL-005)")
    if one("SELECT COUNT(*) FROM employees WHERE first_name = 'John'") != 2:
        errors.append("DB: expected exactly 2 employees named John")

    # Coverage view values on the three scenario Fridays
    for d, expected in (("2026-09-04", 4), ("2026-09-11", 3), ("2026-09-18", 3)):
        got = one(f"SELECT effective_coverage FROM team_coverage "
                  f"WHERE department_name = 'Operations' "
                  f"AND coverage_date = DATE '{d}'")
        if got != expected:
            errors.append(f"DB team_coverage Operations {d}: expected "
                          f"{expected}, got {got}")

    # Evaluation case distribution + reference integrity
    cur.execute("SELECT difficulty, COUNT(*) FROM evaluation_cases GROUP BY difficulty")
    dist = {r[0]: r[1] for r in cur.fetchall()}
    if dist != {"easy": 6, "medium": 8, "hard": 4, "adversarial": 2}:
        errors.append(f"DB evaluation difficulty distribution wrong: {dist}")
    missing_emp = one("SELECT COUNT(*) FROM evaluation_cases c "
                      "WHERE c.employee_id IS NOT NULL AND NOT EXISTS "
                      "(SELECT 1 FROM employees e WHERE e.id = c.employee_id)")
    if missing_emp:
        errors.append(f"DB evaluation_cases with missing employee: {missing_emp}")
    missing_pol = one("SELECT COUNT(*) FROM evaluation_cases c, UNNEST("
                      "c.expected_policy_applied) p WHERE NOT EXISTS "
                      "(SELECT 1 FROM company_policies pol WHERE pol.id = p)")
    if missing_pol:
        errors.append(f"DB evaluation_cases referencing missing policies: {missing_pol}")

    report = {
        "businesses": one("SELECT COUNT(*) FROM businesses"),
        "departments": one("SELECT COUNT(*) FROM departments"),
        "employees": one("SELECT COUNT(*) FROM employees"),
        "policies": one("SELECT COUNT(*) FROM company_policies"),
        "schedules": one("SELECT COUNT(*) FROM schedules"),
        "tasks": one("SELECT COUNT(*) FROM tasks"),
        "attendance_records": one("SELECT COUNT(*) FROM attendance_records"),
        "historical_decisions": one("SELECT COUNT(*) FROM historical_decisions"),
        "evaluation_cases": one("SELECT COUNT(*) FROM evaluation_cases"),
        "difficulty_distribution": dist,
    }
    return (not errors), errors, report



def main() -> int:
    ok, errors, report = validate_world()
    print("=" * 64)
    print("OpsPilot Synthetic Workforce — World Validation")
    print("=" * 64)
    for k, v in report.items():
        print(f"  {k}: {v}")
    if errors:
        print(f"\nFAILED: {len(errors)} error(s)")
        for i, e in enumerate(errors[:30], 1):
            print(f"  {i}. {e}")
        return 1
    print("\nPASSED: all world-level checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
