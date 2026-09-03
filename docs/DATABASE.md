# OpsPilot — Database Schema

> **Status:** complete (Prompt 4). Migrations and seeds pass all verification queries.
> **PostgreSQL 15+** · UUID primary keys (`gen_random_uuid()`) · `TIMESTAMPTZ` timestamps · `JSONB` for machine-readable rules/payloads

---

## 1. Entity–relationship overview

```
businesses (1) ───< departments (1) ───< employees
                         │                  ├── leave_balances (1:N)
                         │                  ├── schedules (1:N)
                         │                  ├── attendance_records (1:N)
                         │                  ├── tasks (assigned_to → employees)
                         │                  └── manager_id → employees (self-ref)
                         └── company_policies (department_id nullable, category-based)

agent_requests (1) ───< agent_runs (1) ───< agent_steps (1:N)
                                           ├── agent_tool_calls (step_id → steps)
                                           ├── agent_evidence (tool_call_id → tool_calls)
                                           ├── agent_decisions (1)
                                           ├── agent_approvals (request_id → requests, run_id → runs)
                                           └── (referenced by) audit_logs.run_id

agent_memory — business-scoped, employee-scoped, source_run_id → agent_runs

evaluation_cases (frozen golden) ←── evaluation_results (evaluation_run_id → evaluation_runs)

audit_logs — business-scoped, run_id → agent_runs (nullable)
```

---

## 2. Schema by migration

### 2.1 `001_business_data.sql` — Business domain

| Table | Columns | PK | FK | Notes |
|---|---|---|---|---|
| businesses | id PK, name, created_at | id | — | Tenant root |
| departments | id PK, business_id, name, minimum_coverage_headcount | id | → businesses | CHECK(minimum_coverage_headcount >= 0), unique(business_id, name) |
| employees | id PK, business_id, department_id, name, role, status, manager_id, hire_date, created_at | id | → businesses, → departments, self→employees | status CHECK IN ('active','inactive','on_leave','suspended','terminated') |
| leave_balances | id PK, employee_id, leave_type, available_days, used_days, year, updated_at | id | → employees | NUMERIC(6,2), unique(employee_id, leave_type, year) |
| schedules | id PK, employee_id, shift_date, shift_start, shift_end, shift_type | id | → employees | shift_type CHECK IN ('standard','critical','on_call','remote','training'), unique(employee_id, shift_date) |
| company_policies | id PK, business_id, category, title, content, rules JSONB, version, is_active, department_id, created_at | id | → businesses, → departments | unique(category, version); rules JSONB holds machine-readable policy logic |
| tasks | id PK, business_id, assigned_to, title, description, priority, due_date, status, created_at | id | → businesses, → employees(assigned_to) | priority CHECK IN ('low','medium','high','critical'), status CHECK IN ('pending','in_progress','blocked','completed','cancelled') |
| attendance_records | id PK, employee_id, date, scheduled_start, actual_start, status, notes | id | → employees | status CHECK IN ('present','late','absent','leave','formal_warning'), unique(employee_id, date) |

### 2.2 `002_agent_data.sql` — Agent execution provenance

| Table | Columns | PK | FK | Notes |
|---|---|---|---|---|
| agent_requests | id PK, business_id, submitted_by_user_id, raw_input, structured_request JSONB, request_type, employee_id, status, created_at, resolved_at | id | → businesses, → employees | status CHECK IN ('pending','parsing','processing','awaiting_approval','approved','rejected','completed','escalated','blocked','failed','aborted') |
| agent_runs | id PK, request_id, business_id, started_at, completed_at, status, final_decision, authorization_tier, confidence, total_tool_calls, total_duration_ms, llm_tokens_used, llm_cost_usd | id | → businesses, → agent_requests | status CHECK IN ('pending','running','awaiting_approval','completed','failed','aborted','blocked') |
| agent_steps | id PK, run_id, step_number, agent_name, input JSONB, output JSONB, status, retry_count, retry_reason, started_at, duration_ms | id | → agent_runs | status CHECK IN ('pending','running','completed','failed','skipped') |
| agent_tool_calls | id PK, run_id, step_id, tool_name, arguments JSONB, result JSONB, success, error_message, duration_ms, called_at | id | → agent_runs, → agent_steps | |
| agent_evidence | id PK, run_id, tool_call_id, evidence_type, evidence_key, evidence_value JSONB, retrieved_at, used_in_decision, cited_in_reason | id | → agent_runs, → agent_tool_calls | Evidence frozen at manifest; evidence_key like TC-* / EV-* |
| agent_decisions | id PK, run_id, decision_type, recommended_action, reason, evidence_refs TEXT[], policy_refs UUID[], conflicts_identified TEXT[], authorization_tier, confidence, verification_passed, verification_failures TEXT[], created_at | id | → agent_runs | decision_type CHECK IN ('approve','decline','block','inform','escalate','request_info') |
| agent_approvals | id PK, request_id, run_id, decision_id, approval_reason, authorization_tier, risk_level, status, reviewed_by_user_id, reviewed_at, review_notes, created_at | id | → agent_requests, → agent_runs, → agent_decisions | unique(decision_id); risk_level CHECK, status CHECK |
| agent_memory | id PK, business_id, employee_id, memory_type, content JSONB, source_run_id, relevance_score, created_at, expires_at | id | → businesses, → employees, → agent_runs | memory_type CHECK IN ('decision_precedent','policy_update','employee_fact','general') |

### 2.3 `003_audit.sql` — Audit log

| Table | Columns | PK | FK | Notes |
|---|---|---|---|---|
| audit_logs | id PK, business_id, run_id, actor, action, target_type, target_id, risk_level, authorization_tier, approved_by, result, metadata JSONB, timestamp | id | → businesses, → agent_runs | Append-only INSERT; risk_level CHECK |

### 2.4 `004_evaluation.sql` — Evaluation harness

| Table | Columns | PK | FK | Notes |
|---|---|---|---|---|
| evaluation_cases | id PK, case_number, title, description, raw_input, employee_id, request_type, expected_decision_type, expected_authorization_tier, expected_approval_required, expected_evidence_keys TEXT[], expected_policy_applied UUID[], is_edge_case, difficulty, adversarial, created_at | id | → employees | case_number UNIQUE; frozen after seed |
| evaluation_runs | id PK, system_version, started_at, completed_at, status, total_cases, passed, failed, overall_score | id | — | status CHECK |
| evaluation_results | id PK, evaluation_run_id, case_id, agent_run_id, system_version, decision_correct, decision_score, evidence_valid, evidence_score, policy_applied, policy_score, authorization_correct, authorization_score, approval_gate_correct, approval_gate_score, weighted_score, hallucination_detected, unsafe_action_attempted, resolution_time_ms, llm_cost_usd, failure_reason, evaluator_notes, evaluated_at | id | → evaluation_runs, → evaluation_cases, → agent_runs | |

---

## 3. Indexes

Every foreign key has a dedicated index. Key additional indexes:

| Index | Table | Column(s) |
|---|---|---|
| idx_departments_business_id | departments | business_id |
| idx_employees_business_id | employees | business_id |
| idx_employees_name | employees | name |
| idx_employees_department_id | employees | department_id |
| idx_employees_manager_id | employees | manager_id |
| idx_leave_balances_employee_id | leave_balances | employee_id |
| idx_schedules_employee_id | schedules | employee_id |
| idx_schedules_shift_date | schedules | shift_date |
| idx_company_policies_business_id_category | company_policies | business_id, category |
| idx_tasks_assigned_to | tasks | assigned_to |
| idx_agent_requests_status | agent_requests | status |
| idx_agent_runs_request_id | agent_runs | request_id |
| idx_agent_runs_status | agent_runs | status |
| idx_agent_steps_run_id | agent_steps | run_id |
| idx_agent_tool_calls_run_id | agent_tool_calls | run_id |
| idx_agent_evidence_run_id | agent_evidence | run_id |
| idx_agent_decisions_run_id | agent_decisions | run_id |
| idx_agent_approvals_status | agent_approvals | status |
| idx_audit_logs_timestamp | audit_logs | timestamp |
| idx_evaluation_cases_difficulty | evaluation_cases | difficulty |
| idx_evaluation_results_eval_run_case | evaluation_results | evaluation_run_id, case_id |

## 4. Provenance chain (evidence traceability)

```
agent_requests
    |  POST /api/v1/requests
    v
agent_runs
    |  [1 Parser] → [2 Context Agent] → [3 Evidence Manifest] → [4 Decision Agent]
    |--→ agent_steps (one per agent invocation)
    |         └─→ agent_tool_calls (every tool invocation)
    |                  └─→ agent_evidence (every factual record captured)
    |--→ agent_decisions (single canonical decision per run)
    └─→ agent_approvals (when tier ≥ 2)
    |
    v
audit_logs (append-only, captures every event + tool call + decision + approval)
```

**Key properties:**
- `agent_evidence` is **frozen** at the Evidence Manifest stage — no later stage can mutate prior evidence.
- Each evidence row carries `evidence_key` (e.g. `TC-0001928`), `evidence_value` (JSON payload), and booleans `used_in_decision` / `cited_in_reason`.
- `agent_tool_calls.result` → `agent_evidence.evidence_value` is the 1:1 source of every fact the Decision Agent reads.
- `agent_decisions.evidence_refs` is an array of `evidence_key` strings the Decision Agent cited.
- `audit_logs` captures every action with `actor`, `action`, `target_type`, `target_id`, `result`, and `risk_level`.

---

## 5. Policies and machine-readable rules

`company_policies.rules` is a JSONB column holding machine-readable logic.
The deterministic `constitutional.py` checker reads these rules directly (no LLM).

| Policy ID | Category | Version | Active | Key rules |
|---|---|---|---|---|
| d…0001 | leave_policy | 1 | No | notice_days: 0, same_day_requests_allowed: true, requires_manager_approval: false — superseded, enables CASE-016 |
| d…0002 | leave_policy | 2 | Yes | notice_days: 3, same_day_requests_allowed: false, requires_manager_approval: true |
| d…0003 | attendance_policy | 1 | Yes | max_late_arrivals: 3, warning_threshold: 2, review_window_days: 60 |
| d…0004 | scheduling_policy | 1 | Yes | min_coverage: ops:2, sales:2, inventory:1, support:2, finance:1; horizon: 14d |
| d…0005 | remote_work_policy | 1 | Yes | allowed: sales, ops, finance, support; NOT inventory |
| d…0006 | disciplinary_policy | 1 | Yes | tier: 3, requires_hr_approval: true, autonomous_execution: false |
| d…0007 | suspension_policy | 1 | Yes | tier: 3, requires_hr_approval: true, requires_investigation: true |
| d…0008 | task_reassignment_policy | 1 | Yes | requires_manager_approval: true, must_check_availability: true, notice_days: 2 |

---

## 6. Authorization tiers and risk mapping

| Tier | Description | Auto-execute? | Human approval required? |
|---|---|---|---|
| Tier 1 | Informational / read-only / policy lookup | Yes | No |
| Tier 2 | Standard consequential action, low/moderate risk | No | Yes (standard approval flow) |
| Tier 3 | High-risk action (termination, suspension) | No — BLOCKED | Yes — mandatory Tier-3 override + human approval |

**Risk levels** on `agent_approvals` and `audit_logs`:
- `low` — informational queries, read-only lookups
- `medium` — standard leave, task reassignments
- `moderate` — leave with minor coverage concerns
- `critical` — disciplinary / termination / suspension (Tier 3)

---

## 7. Constraints summary

- **All PKs**: UUID with `DEFAULT gen_random_uuid()`
- **All timestamps**: `TIMESTAMPTZ NOT NULL DEFAULT now()`
- **CHECK constraints**: enforced on all enum-like fields (status, risk_level, decision_type, memory_type, difficulty, priority)
- **Unique constraints**: per-tenant where appropriate (unique(employee_id, leave_type, year), unique(category, version) on policies, unique(case_number) on evaluation_cases)
- **Self-referential FK**: employees.manager_id → employees.id
- **Append-only**: audit_logs — INSERT only
- **Frozen**: evaluation_cases — seeded once, never modified

---

## 8. Seed data reference

See `backend/database/seed/README.md` for the full employee → case mapping.

| Table | Seeded rows |
|---|---|
| businesses | 1 (Acme Retail Group) |
| departments | 5 |
| employees | 7 |
| leave_balances | 7 |
| schedules | 31 (next 30 days) |
| company_policies | 8 |
| tasks | 3 |
| attendance_records | 6 (4 late + 2 formal warnings, all John Carter) |
| agent_requests | 1 (historical) |
| agent_runs | 1 (historical) |
| agent_steps | 3 (historical provenance) |
| agent_tool_calls | 3 (historical provenance) |
| agent_evidence | 4 (TC-000001 through TC-000004) |
| agent_memory | 2 (decision_precedent + policy_update) |
| evaluation_cases | 20 (frozen golden dataset) |

---

## 9. Applying migrations and seeds

```bash
# Migrations (run in numeric order)
psql -U postgres -d opspilot -f backend/database/migrations/001_business_data.sql
psql -U postgres -d opspilot -f backend/database/migrations/002_agent_data.sql
psql -U postgres -d opspilot -f backend/database/migrations/003_audit.sql
psql -U postgres -d opspilot -f backend/database/migrations/004_evaluation.sql

# Seeds (run in numeric order)
psql -U postgres -d opspilot -f backend/database/seed/01_seed_business.sql
psql -U postgres -d opspilot -f backend/database/seed/02_seed_agent_history.sql
psql -U postgres -d opspilot -f backend/database/seed/03_seed_evaluation_cases.sql
```

> **All seeds are idempotent** (`ON CONFLICT DO NOTHING`) and **evergreen**
> (dates computed via `CURRENT_DATE`). Re-running is safe.

---

— End of DATABASE.md —