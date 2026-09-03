-- ============================================================
-- 005_workforce_simulation.sql
-- OpsPilot — Synthetic Workforce Simulation schema extensions
--
-- Extends the base schema to support the full 50-employee
-- Acme Retail Group simulation for the Frontier Engineering
-- Challenge 2026.
--
-- Adds:
--   * first_name, last_name, email, employment_type on employees
--   * status column on schedules (WORKING/OFF/LEAVE/SICK/HOLIDAY)
--   * updated_at columns on key tables
--   * historical_decisions table
--   * team_coverage view (calculated from schedules)
-- ============================================================

BEGIN;

-- ------------------------------------------------------------------
-- Extend employees with simulation-specific fields
-- ------------------------------------------------------------------
ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS first_name     TEXT,
    ADD COLUMN IF NOT EXISTS last_name      TEXT,
    ADD COLUMN IF NOT EXISTS email          TEXT,
    ADD COLUMN IF NOT EXISTS employment_type TEXT NOT NULL DEFAULT 'full_time'
        CHECK (employment_type IN ('full_time', 'part_time', 'contractor', 'intern')),
    ADD COLUMN IF NOT EXISTS updated_at      TIMESTAMPTZ NOT NULL DEFAULT now();

-- Backfill first_name / last_name from existing name column
UPDATE employees SET
    first_name = split_part(name, ' ', 1),
    last_name  = split_part(name, ' ', 2)
WHERE first_name IS NULL;

-- ------------------------------------------------------------------
-- Extend schedules with status for coverage calculation
-- ------------------------------------------------------------------
ALTER TABLE schedules
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'WORKING'
        CHECK (status IN ('WORKING', 'OFF', 'LEAVE', 'SICK', 'HOLIDAY'));

-- ------------------------------------------------------------------
-- Extend departments with updated_at
-- ------------------------------------------------------------------
ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ------------------------------------------------------------------
-- Extend tasks with updated_at
-- ------------------------------------------------------------------
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ------------------------------------------------------------------
-- Extend leave_balances with annual_entitlement / remaining_days
-- ------------------------------------------------------------------
ALTER TABLE leave_balances
    ADD COLUMN IF NOT EXISTS annual_entitlement NUMERIC(6,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS remaining_days    NUMERIC(6,2) NOT NULL DEFAULT 0;

-- Sync remaining_days from available_days where not set
UPDATE leave_balances SET remaining_days = available_days WHERE remaining_days = 0;

-- ------------------------------------------------------------------
-- historical_decisions — previous operational decisions (NOT policy)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historical_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    employee_id     UUID REFERENCES employees (id) ON DELETE SET NULL,
    request_type    TEXT NOT NULL,
    decision        TEXT NOT NULL
        CHECK (decision IN ('approved', 'rejected', 'escalated', 'withdrawn')),
    reason          TEXT,
    decided_by      TEXT,          -- who made the historical decision
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_historical_decisions_business_id  ON historical_decisions (business_id);
CREATE INDEX idx_historical_decisions_employee_id  ON historical_decisions (employee_id);

-- ------------------------------------------------------------------
-- team_coverage view — calculates effective coverage per department per day
--
-- Logic:
--   scheduled  = employees with a schedule row for that date
--   available  = scheduled employees whose status = 'WORKING'
--   effective  = available count
--   required   = departments.minimum_coverage_headcount
--   deficit    = required - effective  (positive = shortfall)
-- ------------------------------------------------------------------
CREATE OR REPLACE VIEW team_coverage AS
WITH scheduled AS (
    SELECT
        e.department_id,
        s.shift_date AS coverage_date,
        COUNT(*) FILTER (WHERE s.status = 'WORKING') AS effective_coverage,
        COUNT(*) AS total_scheduled
    FROM schedules s
    JOIN employees e ON e.id = s.employee_id
    WHERE e.status = 'active'
    GROUP BY e.department_id, s.shift_date
)
SELECT
    d.id                AS department_id,
    d.name              AS department_name,
    s.coverage_date,
    s.total_scheduled,
    s.effective_coverage,
    d.minimum_coverage_headcount AS required_coverage,
    (s.effective_coverage - d.minimum_coverage_headcount) AS coverage_delta,
    (s.effective_coverage >= d.minimum_coverage_headcount) AS meets_minimum
FROM scheduled s
JOIN departments d ON d.id = s.department_id;

COMMIT;