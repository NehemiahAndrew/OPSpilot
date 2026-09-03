"""pytest fixtures for the OpsPilot tool-layer tests.

The runtime normally talks to PostgreSQL through ``backend.app.database``.
This environment has no PostgreSQL server, so these fixtures provide a
deterministic, in-memory SQLite database populated from the *same*
synthetic workforce world the generator produces (backend/data/generator.py).

The read/action tools issue SQL through ``fetch_one`` / ``fetch_many`` /
``execute``.  These fixtures monkeypatch those helpers (inside the tool
modules, where they are bound by ``from ... import``) with an adapter that
translates the small, known set of PostgreSQL SQL the tools use into
SQLite and executes it against the seeded in-memory database.

The seeded world is byte-for-byte the deterministic generator output, so
tests exercise the exact queries and data the real database would serve.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime

import pytest

from backend.data import generator as g

# ----------------------------------------------------------------------
# Deterministic "today" used to translate CURRENT_DATE so the tests are
# immune to the wall clock of the machine running them.
# ----------------------------------------------------------------------
FAKE_TODAY = "2026-08-29"
YEAR = g.BASE_DATE.year


# ----------------------------------------------------------------------
# Schema (SQLite flavour of the Postgres schema the tools query)
# ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE businesses (
    id TEXT PRIMARY KEY, name TEXT, created_at TEXT
);
CREATE TABLE departments (
    id TEXT PRIMARY KEY, business_id TEXT, name TEXT,
    minimum_coverage_headcount INTEGER, dept_code TEXT, manager_id TEXT,
    updated_at TEXT
);
CREATE TABLE employees (
    id TEXT PRIMARY KEY, business_id TEXT, department_id TEXT, name TEXT,
    role TEXT, status TEXT, manager_id TEXT, hire_date TEXT, created_at TEXT,
    first_name TEXT, last_name TEXT, email TEXT, employment_type TEXT,
    emp_code TEXT, updated_at TEXT
);
CREATE TABLE leave_balances (
    id TEXT PRIMARY KEY, employee_id TEXT, leave_type TEXT,
    available_days REAL, used_days REAL, annual_entitlement REAL,
    remaining_days REAL, year INTEGER, updated_at TEXT
);
CREATE TABLE schedules (
    id TEXT PRIMARY KEY, employee_id TEXT, shift_date TEXT,
    shift_start TEXT, shift_end TEXT, shift_type TEXT, status TEXT
);
CREATE TABLE company_policies (
    id TEXT PRIMARY KEY, business_id TEXT, category TEXT, title TEXT,
    content TEXT, rules TEXT, version INTEGER, is_active INTEGER,
    department_id TEXT, policy_code TEXT, risk_level TEXT,
    effective_from TEXT, effective_until TEXT, approval_requirements TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE tasks (
    id TEXT PRIMARY KEY, business_id TEXT, assigned_to TEXT, title TEXT,
    description TEXT, priority TEXT, due_date TEXT, status TEXT,
    task_code TEXT, updated_at TEXT
);
CREATE TABLE attendance_records (
    id TEXT PRIMARY KEY, employee_id TEXT, date TEXT,
    scheduled_start TEXT, actual_start TEXT, status TEXT, notes TEXT,
    attendance_code TEXT
);
CREATE TABLE historical_decisions (
    id TEXT PRIMARY KEY, business_id TEXT, employee_id TEXT,
    request_type TEXT, decision TEXT, reason TEXT, decided_by TEXT,
    created_at TEXT, decision_code TEXT
);
CREATE TABLE agent_requests (
    id TEXT PRIMARY KEY, business_id TEXT, submitted_by_user_id TEXT,
    raw_input TEXT, structured_request TEXT, request_type TEXT,
    employee_id TEXT, status TEXT, created_at TEXT, resolved_at TEXT
);
CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY, request_id TEXT, business_id TEXT, started_at TEXT,
    completed_at TEXT, status TEXT, final_decision TEXT,
    authorization_tier INTEGER
);
CREATE TABLE agent_evidence (
    id TEXT PRIMARY KEY, run_id TEXT, tool_call_id TEXT, evidence_type TEXT,
    evidence_key TEXT, evidence_value TEXT, retrieved_at TEXT,
    used_in_decision INTEGER, cited_in_reason INTEGER
);
CREATE TABLE agent_approvals (
    id TEXT PRIMARY KEY, request_id TEXT, run_id TEXT, decision_id TEXT,
    approval_reason TEXT, authorization_tier INTEGER, risk_level TEXT,
    status TEXT, reviewed_by_user_id TEXT, reviewed_at TEXT,
    review_notes TEXT, created_at TEXT, decision_payload TEXT
);
CREATE TABLE evaluation_cases (
    id TEXT PRIMARY KEY, case_number TEXT, title TEXT, description TEXT,
    raw_input TEXT, employee_id TEXT, request_type TEXT,
    expected_decision_type TEXT, expected_authorization_tier INTEGER,
    expected_approval_required INTEGER, expected_evidence_keys TEXT,
    expected_policy_applied TEXT, is_edge_case INTEGER, difficulty TEXT,
    adversarial INTEGER, created_at TEXT,
    category TEXT, context TEXT, expected_action TEXT,
    expected_evidence_types TEXT, expected_policy_codes TEXT,
    ground_truth_reason TEXT
);
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY, business_id TEXT, run_id TEXT, actor TEXT,
    action TEXT, target_type TEXT, target_id TEXT, risk_level TEXT,
    authorization_tier INTEGER, approved_by TEXT, result TEXT,
    metadata TEXT, timestamp TEXT
);
CREATE TABLE agent_tool_calls (
    id TEXT PRIMARY KEY, run_id TEXT, step_id TEXT, tool_name TEXT,
    arguments TEXT, result TEXT, success INTEGER, error_message TEXT,
    duration_ms INTEGER, called_at TEXT
);
CREATE TABLE agent_decisions (
    id TEXT PRIMARY KEY, run_id TEXT, decision_type TEXT,
    recommended_action TEXT, reason TEXT, evidence_refs TEXT,
    policy_refs TEXT, conflicts_identified TEXT,
    authorization_tier INTEGER, confidence REAL,
    verification_passed INTEGER, verification_failures TEXT,
    created_at TEXT
);
CREATE TABLE agent_memory (
    id TEXT PRIMARY KEY, business_id TEXT, employee_id TEXT,
    memory_type TEXT, content TEXT, source_run_id TEXT,
    relevance_score REAL, created_at TEXT, expires_at TEXT
);
"""


# ----------------------------------------------------------------------
# PostgreSQL -> SQLite SQL translation (limited to the SQL the tools use)
# ----------------------------------------------------------------------
def translate_sql(sql: str, params=None):
    """Translate PostgreSQL SQL to SQLite-compatible SQL.

    Key difference: PostgreSQL $N params can be reused ($2 appears multiple
    times = same value), but SQLite ? placeholders cannot. We expand
    repeated $N into separate ? and duplicate the corresponding param values.

    Returns (translated_sql, expanded_params).
    """
    s = sql
    s = re.sub(r"::uuid", "", s)
    s = re.sub(r"::jsonb", "", s)
    # JSON extraction: col->>'key'  ->  json_extract(col, '$.key')
    s = re.sub(
        r"(\w+)\s*->>\s*'([^']+)'",
        lambda m: f"json_extract({m.group(1)}, '$.{m.group(2)}')",
        s,
    )
    s = re.sub(r"CURRENT_DATE", f"'{FAKE_TODAY}'", s, flags=re.IGNORECASE)
    # ILIKE -> LIKE (SQLite LIKE is ASCII case-insensitive by default)
    s = re.sub(r"\bILIKE\b", "LIKE", s, flags=re.IGNORECASE)

    # Expand $N parameters FIRST (before INTERVAL processing)
    expanded_params = params
    if params is not None:
        param_refs = re.findall(r"\$\d+", s)
        if param_refs:
            # Map $N -> param value (1-indexed)
            param_map = {}
            for ref in set(param_refs):
                idx = int(ref[1:]) - 1  # $1 -> index 0
                param_map[ref] = params[idx]

            # Build expanded params list in order of appearance
            expanded = []
            for ref in param_refs:
                expanded.append(param_map[ref])

            # Replace all $N with ?, longest refs first so $10/$11 are
            # not corrupted by the earlier replacement of $1.
            for ref in sorted(set(param_refs), key=len, reverse=True):
                s = s.replace(ref, "?")

            expanded_params = tuple(expanded)

    # Now handle INTERVAL syntax (after $N -> ? expansion)
    # PostgreSQL: '2026-08-29' - INTERVAL '1 day' * ?
    # SQLite: date('2026-08-29', '-' || ? || ' days')
    s = re.sub(
        r"'(\d{4}-\d{2}-\d{2})'\s*-\s*INTERVAL\s*'1 day'\s*\*\s*\?",
        lambda m: f"date('{m.group(1)}', '-' || ? || ' days')",
        s,
    )
    # Legacy pattern
    s = re.sub(
        r"'(\d{4}-\d{2}-\d{2})'\s*-\s*INTERVAL\s*'\? days'",
        lambda m: f"date('{m.group(1)}', '-' || ? || ' days')",
        s,
    )

    return s, expanded_params


# ----------------------------------------------------------------------
# Build + seed the in-memory database from the deterministic world
# ----------------------------------------------------------------------
def build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cur = conn.cursor()

    def ins(table, cols, row):
        ph = ", ".join("?" * len(cols))
        cur.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph})",
            tuple(row[c] for c in cols),
        )

    cur.execute(
        "INSERT INTO businesses (id, name, created_at) VALUES (?, ?, ?)",
        (g.BUSINESS_ID, g.BUSINESS_NAME, f"{FAKE_TODAY}T00:00:00Z"),
    )

    for d in g.DEPARTMENTS:
        ins("departments",
            ["id", "business_id", "name", "minimum_coverage_headcount",
             "dept_code", "manager_id"],
            {"id": d["id"], "business_id": g.BUSINESS_ID, "name": d["name"],
             "minimum_coverage_headcount": d["min_coverage"],
             "dept_code": d["dept_code"],
             "manager_id": g.emp_uuid(d["manager_code"])})

    # employees + leave balances (deterministic generator world)
    for e in g.gen_employees():
        ins("employees",
            ["id", "business_id", "department_id", "name", "role", "status",
             "manager_id", "hire_date", "first_name", "last_name", "email",
             "employment_type", "emp_code", "created_at"],
            {"id": e["id"], "business_id": g.BUSINESS_ID,
             "department_id": e["department_id"],
             "name": f"{e['first_name']} {e['last_name']}",
             "role": e["job_title"], "status": e["employment_status"],
             "manager_id": e["manager_id"], "hire_date": e["hire_date"],
             "first_name": e["first_name"], "last_name": e["last_name"],
             "email": e["email"], "employment_type": e["employment_type"],
             "emp_code": e["emp_code"], "created_at": f"{FAKE_TODAY}T00:00:00Z"})
        ins("leave_balances",
            ["id", "employee_id", "leave_type", "available_days", "used_days",
             "annual_entitlement", "remaining_days", "year", "updated_at"],
            {"id": g._uuid(f"lb-{e['emp_code']}"), "employee_id": e["id"],
             "leave_type": "annual", "available_days": e["remaining_days"],
             "used_days": e["used_days"],
             "annual_entitlement": e["annual_entitlement"],
             "remaining_days": e["remaining_days"], "year": YEAR,
             "updated_at": f"{FAKE_TODAY}T00:00:00Z"})

    # policies
    for p in g.POLICIES:
        ins("company_policies",
            ["id", "business_id", "category", "title", "content", "rules",
             "version", "is_active", "policy_code", "risk_level",
             "effective_from", "effective_until", "approval_requirements"],
            {"id": g.policy_uuid(p["policy_code"]), "business_id": g.BUSINESS_ID,
             "category": p["category"], "title": p["title"],
             "content": p["rules"].get("description", ""),
             "rules": json.dumps(p["rules"]), "version": p["version"],
             "is_active": 1, "policy_code": p["policy_code"],
             "risk_level": p["risk_level"],
             "effective_from": p["effective_from"],
             "effective_until": p["effective_until"],
             "approval_requirements": json.dumps(p["approval_requirements"])})

    # schedules
    for s in g.gen_schedules(g.gen_employees()):
        ins("schedules",
            ["id", "employee_id", "shift_date", "shift_start", "shift_end",
             "shift_type", "status"],
            {"id": s["id"], "employee_id": s["employee_id"],
             "shift_date": s["shift_date"], "shift_start": s["shift_start"],
             "shift_end": s["shift_end"], "shift_type": s["shift_type"],
             "status": s["status"]})

    # tasks
    for t in g.gen_tasks(g.gen_employees()):
        ins("tasks",
            ["id", "business_id", "assigned_to", "title", "description",
             "priority", "due_date", "status", "task_code"],
            {"id": t["id"], "business_id": g.BUSINESS_ID,
             "assigned_to": t["employee_id"], "title": t["title"],
             "description": t["description"], "priority": t["priority"],
             "due_date": t["due_date"], "status": t["status"],
             "task_code": t["task_code"]})

    # attendance
    for a in g.gen_attendance(g.gen_employees()):
        ins("attendance_records",
            ["id", "employee_id", "date", "scheduled_start", "actual_start",
             "status", "notes", "attendance_code"],
            {"id": a["id"], "employee_id": a["employee_id"], "date": a["date"],
             "scheduled_start": a["scheduled_start"],
             "actual_start": a["actual_start"], "status": a["status"],
             "notes": a["notes"], "attendance_code": a["attendance_code"]})

    # historical decisions
    for h in g.gen_historical(g.gen_employees()):
        ins("historical_decisions",
            ["id", "business_id", "employee_id", "request_type", "decision",
             "reason", "decided_by", "created_at", "decision_code"],
            {"id": h["id"], "business_id": g.BUSINESS_ID,
             "employee_id": h["employee_id"], "request_type": h["request_type"],
             "decision": h["decision"], "reason": h["reason"],
             "decided_by": h["decided_by"], "created_at": h["created_at"],
             "decision_code": h["decision_code"]})

    conn.commit()
    return conn


# ----------------------------------------------------------------------
# The fake database helper interface (mirrors backend.app.database)
# Async methods that match the asyncpg-based database.py interface
# ----------------------------------------------------------------------
class FakeDB:
    def __init__(self):
        self.conn = build_db()

    @staticmethod
    def _coerce(params):
        """Convert date/datetime params to ISO strings."""
        out = []
        for p in params or ():
            if isinstance(p, (date, datetime)):
                out.append(p.isoformat())
            else:
                out.append(p)
        return tuple(out)

    def _rows(self, sql, params):
        translated, expanded_params = translate_sql(sql, params)
        cur = self.conn.execute(translated, self._coerce(expanded_params))
        return cur.fetchall()

    async def fetch_one(self, sql, params=None):
        rows = self._rows(sql, params)
        return dict(rows[0]) if rows else None

    async def fetch_many(self, sql, params=None):
        return [dict(r) for r in self._rows(sql, params)]

    async def execute(self, sql, params=None):
        translated, expanded_params = translate_sql(sql, params)
        cur = self.conn.execute(translated, self._coerce(expanded_params))
        self.conn.commit()
        return cur.rowcount


@pytest.fixture
def fake_db():
    """The seeded in-memory database adapter."""
    return FakeDB()


@pytest.fixture
def patch_db(monkeypatch, fake_db):
    """Monkeypatch the DB helpers inside the tool/router modules.

    The tools bind fetch_one/fetch_many/execute with ``from ... import``
    at import time, so we patch the attributes on the *consumer* modules,
    not just backend.app.database.
    """
    targets = [
        ("backend.app.tools.read_tools", "fetch_one"),
        ("backend.app.tools.read_tools", "fetch_many"),
        ("backend.app.tools.action_tools", "fetch_one"),
        ("backend.app.tools.action_tools", "execute"),
        ("backend.app.tools.registry", "execute"),
        ("backend.app.orchestrator.executor", "fetch_one"),
        ("backend.app.orchestrator.executor", "execute"),
        ("backend.app.orchestrator.executor", "fetch_many"),
        ("backend.app.routers.employees", "fetch_one"),
        ("backend.app.routers.employees", "fetch_many"),
        ("backend.app.routers.policies", "fetch_one"),
        ("backend.app.routers.policies", "fetch_many"),
        ("backend.app.routers.requests", "fetch_one"),
        ("backend.app.routers.requests", "execute"),
        ("backend.app.routers.approvals", "fetch_one"),
        ("backend.app.routers.approvals", "fetch_many"),
        ("backend.app.routers.approvals", "execute"),
        ("backend.app.routers.audit", "fetch_one"),
        ("backend.app.routers.audit", "fetch_many"),
        ("backend.app.routers.audit", "execute"),
        ("backend.app.routers.evidence", "fetch_one"),
        ("backend.app.routers.evidence", "fetch_many"),
        ("backend.app.routers.evidence", "execute"),
        ("backend.app.routers.runs", "fetch_one"),
        ("backend.app.routers.runs", "fetch_many"),
    ]
    for mod_name, attr in targets:
        mod = __import__(mod_name, fromlist=["x"])
        value = {
            "fetch_one": fake_db.fetch_one,
            "fetch_many": fake_db.fetch_many,
            "execute": fake_db.execute,
        }[attr]
        # raising=False: only patch attributes the consumer module actually
        # bound at import time.
        monkeypatch.setattr(mod, attr, value, raising=False)
    db = __import__("backend.app.database", fromlist=["x"])
    monkeypatch.setattr(db, "fetch_one", fake_db.fetch_one)
    monkeypatch.setattr(db, "fetch_many", fake_db.fetch_many)
    monkeypatch.setattr(db, "execute", fake_db.execute)
    # Mock pool init/close to prevent real DB connections
    monkeypatch.setattr(db, "init_pool", lambda: None)
    monkeypatch.setattr(db, "close_pool", lambda: None)
    return fake_db


@pytest.fixture
def ctx():
    """A standard ToolContext for the demo business."""
    from backend.app.models import ToolContext

    return ToolContext(
        business_id=g.BUSINESS_ID,
        requesting_user_id="USER-001",
        user_role="manager",
        run_id="99999999-0000-0000-0000-000000000001",
        step_id="99999999-0000-0000-0000-000000000002",
    )
