-- ============================================================
-- 004_evaluation.sql
-- OpsPilot - Evaluation harness domain schema (PostgreSQL 15+)
--
-- Mirrors evaluation/cases/cases.json (frozen golden dataset) and
-- evaluation/results/ (harness output). See docs/EVALUATION.md and
-- docs/ARCHITECTURE.md section 9.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------------
-- evaluation_cases (frozen golden dataset - do not modify after seed)
-- ------------------------------------------------------------------
CREATE TABLE evaluation_cases (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number                 TEXT NOT NULL UNIQUE,      -- CASE-001 ...
    title                       TEXT NOT NULL,
    description                 TEXT,
    raw_input                   TEXT NOT NULL,
    employee_id                 UUID REFERENCES employees (id) ON DELETE SET NULL,
    request_type                TEXT NOT NULL,
    expected_decision_type      TEXT NOT NULL
        CHECK (expected_decision_type IN ('approve', 'decline', 'block', 'inform',
                                          'escalate', 'request_info')),
    expected_authorization_tier INT NOT NULL,
    expected_approval_required  BOOLEAN NOT NULL DEFAULT FALSE,
    expected_evidence_keys      TEXT[] NOT NULL DEFAULT '{}',
    expected_policy_applied     UUID[] NOT NULL DEFAULT '{}',
    is_edge_case                BOOLEAN NOT NULL DEFAULT FALSE,
    difficulty                  TEXT NOT NULL
        CHECK (difficulty IN ('easy', 'medium', 'hard', 'adversarial')),
    adversarial                 BOOLEAN NOT NULL DEFAULT FALSE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_evaluation_cases_difficulty  ON evaluation_cases (difficulty);
CREATE INDEX idx_evaluation_cases_employee_id ON evaluation_cases (employee_id);

-- ------------------------------------------------------------------
-- evaluation_runs
-- ------------------------------------------------------------------
CREATE TABLE evaluation_runs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_version TEXT NOT NULL,          -- 'baseline' | 'iteration-1' | ...
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    status         TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    total_cases    INT NOT NULL DEFAULT 0,
    passed         INT NOT NULL DEFAULT 0,
    failed         INT NOT NULL DEFAULT 0,
    overall_score  NUMERIC(6, 4)
);
CREATE INDEX idx_evaluation_runs_status ON evaluation_runs (status);

-- ------------------------------------------------------------------
-- evaluation_results
-- ------------------------------------------------------------------
CREATE TABLE evaluation_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_run_id       UUID NOT NULL REFERENCES evaluation_runs (id) ON DELETE CASCADE,
    case_id                 UUID NOT NULL REFERENCES evaluation_cases (id) ON DELETE CASCADE,
    agent_run_id            UUID REFERENCES agent_runs (id) ON DELETE SET NULL,
    system_version          TEXT NOT NULL,
    decision_correct        BOOLEAN,
    decision_score          NUMERIC(6, 4),
    evidence_valid          BOOLEAN,
    evidence_score          NUMERIC(6, 4),
    policy_applied          BOOLEAN,
    policy_score            NUMERIC(6, 4),
    authorization_correct   BOOLEAN,
    authorization_score     NUMERIC(6, 4),
    approval_gate_correct   BOOLEAN,
    approval_gate_score     NUMERIC(6, 4),
    weighted_score          NUMERIC(6, 4),
    hallucination_detected  BOOLEAN NOT NULL DEFAULT FALSE,
    unsafe_action_attempted BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_time_ms      INT,
    llm_cost_usd            NUMERIC(12, 6) NOT NULL DEFAULT 0,
    failure_reason          TEXT,
    evaluator_notes         TEXT,
    evaluated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_evaluation_results_evaluation_run_id_case_id
    ON evaluation_results (evaluation_run_id, case_id);
CREATE INDEX idx_evaluation_results_case_id ON evaluation_results (case_id);

COMMIT;