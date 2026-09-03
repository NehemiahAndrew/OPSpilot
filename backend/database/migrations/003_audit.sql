-- ============================================================
-- 003_audit.sql
-- OpsPilot - Append-only audit log (PostgreSQL 15+)
--
-- Written by the deterministic Audit Writer (docs/ARCHITECTURE.md
-- stage 8). The table is intentionally INSERT-only; updates/deletes
-- are not permitted at the application layer.
-- ============================================================

BEGIN;

CREATE TABLE audit_logs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id        UUID NOT NULL REFERENCES businesses (id) ON DELETE CASCADE,
    run_id             UUID REFERENCES agent_runs (id) ON DELETE SET NULL,
    actor              TEXT NOT NULL,     -- 'system' | 'context_agent' | 'decision_agent' | user id
    action             TEXT NOT NULL,     -- 'request.created', 'tool.called', 'decision.reached', ...
    target_type        TEXT,              -- 'request' | 'run' | 'tool' | 'policy' | 'approval'
    target_id          UUID,
    risk_level         TEXT
        CHECK (risk_level IN ('low', 'medium', 'moderate', 'critical')),
    authorization_tier INT,
    approved_by        UUID,
    result             TEXT,
    metadata           JSONB,
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_business_id ON audit_logs (business_id);
CREATE INDEX idx_audit_logs_run_id      ON audit_logs (run_id);
CREATE INDEX idx_audit_logs_timestamp   ON audit_logs (timestamp);

COMMIT;