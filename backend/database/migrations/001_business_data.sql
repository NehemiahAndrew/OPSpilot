-- ============================================================
-- 001_business_data.sql
-- OpsPilot - Business domain schema (PostgreSQL 15+)
--
-- Conventions:
--   * UUID primary keys, default gen_random_uuid() (PG13+ built-in)
--   * TIMESTAMPTZ for all timestamps
--   * JSONB for machine-readable policy rules / payloads
--   * CHECK constraints for closed enumerations
--   * One index per foreign key + the dedicated indexes in the
--     OpsPilot INDEXES spec (see docs/DATABASE.md)
-- ============================================================

BEGIN;

-- ------------------------------------------------------------------
-- businesses
-- ------------------------------------------------------------------
CREATE TABLE businesses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------
-- departments
-- ------------------------------------------------------------------
CREATE TABLE departments (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id                UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    name                       TEXT NOT NULL,
    minimum_coverage_headcount INT  NOT NULL DEFAULT 1
        CHECK (minimum_coverage_headcount >= 0),
    UNIQUE (business_id, name)
);
CREATE INDEX idx_departments_business_id ON departments (business_id);

-- ------------------------------------------------------------------
-- employees
-- ------------------------------------------------------------------
CREATE TABLE employees (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id   UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    department_id UUID REFERENCES departments (id) ON DELETE SET NULL,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'on_leave', 'suspended', 'terminated')),
    manager_id    UUID REFERENCES employees (id) ON DELETE SET NULL,
    hire_date     DATE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_employees_business_id    ON employees (business_id);
CREATE INDEX idx_employees_name           ON employees (name);
CREATE INDEX idx_employees_department_id  ON employees (department_id);
CREATE INDEX idx_employees_manager_id     ON employees (manager_id);

-- ------------------------------------------------------------------
-- leave_balances
-- ------------------------------------------------------------------
CREATE TABLE leave_balances (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id    UUID NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    leave_type     TEXT NOT NULL,
    available_days NUMERIC(6, 2) NOT NULL DEFAULT 0,
    used_days      NUMERIC(6, 2) NOT NULL DEFAULT 0,
    year           INT  NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (employee_id, leave_type, year)
);
CREATE INDEX idx_leave_balances_employee_id ON leave_balances (employee_id);

-- ------------------------------------------------------------------
-- schedules
-- ------------------------------------------------------------------
CREATE TABLE schedules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    shift_date  DATE NOT NULL,
    shift_start TIME NOT NULL,
    shift_end   TIME NOT NULL,
    shift_type  TEXT NOT NULL DEFAULT 'standard'
        CHECK (shift_type IN ('standard', 'critical', 'on_call', 'remote', 'training')),
    UNIQUE (employee_id, shift_date)
);
CREATE INDEX idx_schedules_employee_id ON schedules (employee_id);
CREATE INDEX idx_schedules_shift_date  ON schedules (shift_date);

-- ------------------------------------------------------------------
-- company_policies
-- ------------------------------------------------------------------
CREATE TABLE company_policies (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id   UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    category      TEXT NOT NULL,      -- leave_policy, attendance_policy, ...
    title         TEXT NOT NULL,
    content       TEXT NOT NULL DEFAULT '',
    rules         JSONB NOT NULL DEFAULT '{}'::jsonb,
    version       INT  NOT NULL DEFAULT 1,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    department_id UUID REFERENCES departments (id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (category, version)
);
CREATE INDEX idx_company_policies_business_id_category ON company_policies (business_id, category);
CREATE INDEX idx_company_policies_department_id        ON company_policies (department_id);

-- ------------------------------------------------------------------
-- tasks
-- ------------------------------------------------------------------
CREATE TABLE tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id  UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    assigned_to  UUID REFERENCES employees (id) ON DELETE SET NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    priority     TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    due_date     DATE,
    status       TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'blocked', 'completed', 'cancelled')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tasks_business_id ON tasks (business_id);
CREATE INDEX idx_tasks_assigned_to ON tasks (assigned_to);

-- ------------------------------------------------------------------
-- attendance_records
-- ------------------------------------------------------------------
CREATE TABLE attendance_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     UUID NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    scheduled_start TIME,
    actual_start    TIME,
    status          TEXT NOT NULL
        CHECK (status IN ('present', 'late', 'absent', 'leave', 'formal_warning')),
    notes           TEXT,
    UNIQUE (employee_id, date)
);
CREATE INDEX idx_attendance_records_employee_id ON attendance_records (employee_id);
CREATE INDEX idx_attendance_records_date        ON attendance_records (date);

COMMIT;
