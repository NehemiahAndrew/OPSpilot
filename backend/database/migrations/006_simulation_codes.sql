-- ============================================================
-- 006_simulation_codes.sql
-- OpsPilot — Stable business identifiers + evaluation ground truth
--
-- Adds:
--   * departments.dept_code / manager_id        (DEP-001..)
--   * employees.emp_code                        (EMP-001..)
--   * company_policies.policy_code / risk_level /
--     effective_from / effective_until / approval_requirements (POL-001..)
--   * tasks.task_code                           (TASK-001..)
--   * attendance_records.attendance_code        (ATT-0001..)
--   * historical_decisions.decision_code        (DEC-001..)
--   * evaluation_cases ground-truth columns     (category, context,
--     expected_action, expected_evidence_types, expected_policy_codes,
--     ground_truth_reason)
-- ============================================================

BEGIN;

-- ------------------------------------------------------------------
-- Departments: stable code + department manager
-- ------------------------------------------------------------------
ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS dept_code TEXT,
    ADD COLUMN IF NOT EXISTS manager_id UUID REFERENCES employees (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS uq_departments_dept_code
    ON departments (dept_code) WHERE dept_code IS NOT NULL;

-- ------------------------------------------------------------------
-- Employees: stable business code
-- ------------------------------------------------------------------
ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS emp_code TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_emp_code
    ON employees (emp_code) WHERE emp_code IS NOT NULL;

-- ------------------------------------------------------------------
-- Policies: stable code + governance metadata
-- ------------------------------------------------------------------
ALTER TABLE company_policies
    ADD COLUMN IF NOT EXISTS policy_code        TEXT,
    ADD COLUMN IF NOT EXISTS risk_level         TEXT
        CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical')),
    ADD COLUMN IF NOT EXISTS effective_from     DATE,
    ADD COLUMN IF NOT EXISTS effective_until    DATE,
    ADD COLUMN IF NOT EXISTS approval_requirements JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS uq_company_policies_policy_code
    ON company_policies (policy_code) WHERE policy_code IS NOT NULL;

-- ------------------------------------------------------------------
-- Tasks / attendance / historical decisions: stable codes
-- ------------------------------------------------------------------
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_task_code
    ON tasks (task_code) WHERE task_code IS NOT NULL;

ALTER TABLE attendance_records ADD COLUMN IF NOT EXISTS attendance_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_attendance_code
    ON attendance_records (attendance_code) WHERE attendance_code IS NOT NULL;

ALTER TABLE historical_decisions ADD COLUMN IF NOT EXISTS decision_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_historical_decisions_decision_code
    ON historical_decisions (decision_code) WHERE decision_code IS NOT NULL;

-- ------------------------------------------------------------------
-- Evaluation cases: frozen ground-truth extensions
-- ------------------------------------------------------------------
ALTER TABLE evaluation_cases
    ADD COLUMN IF NOT EXISTS category               TEXT,
    ADD COLUMN IF NOT EXISTS context                JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS expected_action        TEXT,
    ADD COLUMN IF NOT EXISTS expected_evidence_types TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS expected_policy_codes  TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS ground_truth_reason    TEXT;

CREATE INDEX IF NOT EXISTS idx_evaluation_cases_category
    ON evaluation_cases (category);

COMMIT;