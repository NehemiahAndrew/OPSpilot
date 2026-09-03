-- ============================================================
-- 002_agent_data.sql
-- OpsPilot - Agent execution domain schema (PostgreSQL 15+)
--
-- Tables capture the full provenance chain documented in
-- docs/ARCHITECTURE.md section 8:
--   requests -> runs -> steps -> tool_calls -> evidence
--                        -> decisions -> approvals
--   runs -> memory (decision precedents / policy updates)
-- ============================================================

BEGIN;

-- ------------------------------------------------------------------
-- agent_requests
-- ------------------------------------------------------------------
CREATE TABLE agent_requests (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id          UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    submitted_by_user_id UUID,
    raw_input            TEXT NOT NULL,
    structured_request  JSONB,
    request_type         TEXT NOT NULL,
    employee_id          UUID REFERENCES employees (id) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'parsing', 'processing', 'awaiting_approval',
                          'approved', 'rejected', 'completed', 'escalated',
                          'blocked', 'failed', 'aborted')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at          TIMESTAMPTZ
);
CREATE INDEX idx_agent_requests_business_id ON agent_requests (business_id);
CREATE INDEX idx_agent_requests_employee_id ON agent_requests (employee_id);
CREATE INDEX idx_agent_requests_status      ON agent_requests (status);

-- ------------------------------------------------------------------
-- agent_runs
-- ------------------------------------------------------------------
CREATE TABLE agent_runs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id         UUID NOT NULL REFERENCES agent_requests (id) ON DELETE CASCADE,
    business_id        UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ,
    status             TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('pending', 'running', 'awaiting_approval',
                          'completed', 'failed', 'aborted', 'blocked')),
    final_decision     TEXT,
    authorization_tier INT,
    confidence         NUMERIC(5, 4),
    total_tool_calls   INT NOT NULL DEFAULT 0,
    total_duration_ms  INT NOT NULL DEFAULT 0,
    llm_tokens_used    INT NOT NULL DEFAULT 0,
    llm_cost_usd       NUMERIC(12, 6) NOT NULL DEFAULT 0
);
CREATE INDEX idx_agent_runs_request_id  ON agent_runs (request_id);
CREATE INDEX idx_agent_runs_status      ON agent_runs (status);
CREATE INDEX idx_agent_runs_business_id ON agent_runs (business_id);

-- ------------------------------------------------------------------
-- agent_steps
-- ------------------------------------------------------------------
CREATE TABLE agent_steps (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    step_number  INT  NOT NULL,
    agent_name   TEXT NOT NULL,
    input        JSONB,
    output       JSONB,
    status       TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    retry_count  INT NOT NULL DEFAULT 0,
    retry_reason TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms  INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_agent_steps_run_id ON agent_steps (run_id);

-- ------------------------------------------------------------------
-- agent_tool_calls
-- ------------------------------------------------------------------
CREATE TABLE agent_tool_calls (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    step_id       UUID REFERENCES agent_steps (id) ON DELETE SET NULL,
    tool_name     TEXT NOT NULL,
    arguments     JSONB,
    result        JSONB,
    success       BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    duration_ms   INT NOT NULL DEFAULT 0,
    called_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_tool_calls_run_id   ON agent_tool_calls (run_id);
CREATE INDEX idx_agent_tool_calls_step_id  ON agent_tool_calls (step_id);

-- ------------------------------------------------------------------
-- agent_evidence
-- ------------------------------------------------------------------
CREATE TABLE agent_evidence (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    tool_call_id     UUID REFERENCES agent_tool_calls (id) ON DELETE SET NULL,
    evidence_type    TEXT NOT NULL,
    evidence_key     TEXT NOT NULL,
    evidence_value   JSONB,
    retrieved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    used_in_decision BOOLEAN NOT NULL DEFAULT FALSE,
    cited_in_reason  BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_agent_evidence_run_id       ON agent_evidence (run_id);
CREATE INDEX idx_agent_evidence_tool_call_id ON agent_evidence (tool_call_id);

-- ------------------------------------------------------------------
-- agent_decisions
-- ------------------------------------------------------------------
CREATE TABLE agent_decisions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                UUID NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    decision_type         TEXT NOT NULL
        CHECK (decision_type IN ('approve', 'decline', 'block', 'inform',
                                 'escalate', 'request_info')),
    recommended_action    TEXT NOT NULL DEFAULT '',
    reason                TEXT,
    evidence_refs         TEXT[] NOT NULL DEFAULT '{}',
    policy_refs           UUID[] NOT NULL DEFAULT '{}',
    conflicts_identified  TEXT[] NOT NULL DEFAULT '{}',
    authorization_tier    INT,
    confidence            NUMERIC(5, 4),
    verification_passed   BOOLEAN,
    verification_failures TEXT[] NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_decisions_run_id ON agent_decisions (run_id);

-- ------------------------------------------------------------------
-- agent_approvals
-- ------------------------------------------------------------------
CREATE TABLE agent_approvals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          UUID REFERENCES agent_requests (id) ON DELETE CASCADE,
    run_id              UUID REFERENCES agent_runs (id) ON DELETE CASCADE,
    decision_id         UUID UNIQUE REFERENCES agent_decisions (id) ON DELETE CASCADE,
    approval_reason     TEXT,
    authorization_tier  INT,
    risk_level          TEXT
        CHECK (risk_level IN ('low', 'medium', 'moderate', 'critical')),
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected',
                          'override_requested', 'expired')),
    reviewed_by_user_id UUID,
    reviewed_at         TIMESTAMPTZ,
    review_notes        TEXT,
    decision_payload    JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_approvals_request_id ON agent_approvals (request_id);
CREATE INDEX idx_agent_approvals_run_id     ON agent_approvals (run_id);
CREATE INDEX idx_agent_approvals_status     ON agent_approvals (status);

-- ------------------------------------------------------------------
-- agent_memory (decision precedents / policy updates / facts)
-- ------------------------------------------------------------------
CREATE TABLE agent_memory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    employee_id     UUID REFERENCES employees (id) ON DELETE CASCADE,
    memory_type     TEXT NOT NULL
        CHECK (memory_type IN ('decision_precedent', 'policy_update',
                               'employee_fact', 'general')),
    content         JSONB NOT NULL,
    source_run_id   UUID REFERENCES agent_runs (id) ON DELETE SET NULL,
    relevance_score NUMERIC(5, 4) NOT NULL DEFAULT 0.5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ
);
CREATE INDEX idx_agent_memory_business_id   ON agent_memory (business_id);
CREATE INDEX idx_agent_memory_employee_id   ON agent_memory (employee_id);
CREATE INDEX idx_agent_memory_source_run_id ON agent_memory (source_run_id);

COMMIT;
