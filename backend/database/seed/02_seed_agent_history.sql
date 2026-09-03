-- ============================================================
-- seed/02_seed_agent_history.sql
-- OpsPilot — Historical agent activity + memory
--
-- Provides a frozen provenance chain (request -> run -> steps ->
-- tool_calls -> evidence -> decision) plus agent_memory rows that
-- evaluation cases use to test that CURRENT POLICY always outranks
-- historical decisions and memories (see EVL-013).
--
-- References the coherent workforce world seeded by
-- seed/04_seed_workforce.sql (Sarah Mitchell = EMP-001 =
-- c0000000-0000-0000-0000-000000000101).
-- ============================================================

BEGIN;

-- ------------------------------------------------------------------
-- Historical approved Friday leave for Sarah Mitchell (July 2026)
-- ------------------------------------------------------------------
INSERT INTO agent_requests
    (id, business_id, submitted_by_user_id, raw_input, structured_request,
     request_type, employee_id, status, created_at, resolved_at)
VALUES
    ('20000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001',
     '90000000-0000-0000-0000-000000000001',
     'Sarah Mitchell would like to take a Friday off for a family event.',
     '{"type": "leave_request", "intent": "FAMILY_EVENT", "day": "Friday"}',
     'leave_request', 'c0000000-0000-0000-0000-000000000101',
     'completed', '2026-07-24 09:00:00+00', '2026-07-24 09:05:00+00')
ON CONFLICT (id) DO NOTHING;

INSERT INTO agent_runs
    (id, request_id, business_id, started_at, completed_at, status,
     final_decision, authorization_tier, confidence, total_tool_calls,
     total_duration_ms, llm_tokens_used, llm_cost_usd)
VALUES
    ('20000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001',
     'a0000000-0000-0000-0000-000000000001',
     '2026-07-24 09:00:00+00', '2026-07-24 09:05:00+00', 'completed',
     'approve', 2, 0.94, 3, 4200, 1850, 0.0120)
ON CONFLICT (id) DO NOTHING;

-- Historical run steps / tool calls / evidence (frozen provenance chain)
INSERT INTO agent_steps
    (id, run_id, step_number, agent_name, input, output, status, started_at, duration_ms)
VALUES
    ('40000000-0000-0000-0000-000000000010', '20000000-0000-0000-0000-000000000002', 1,
     'request_parser', '{"raw_input": "Sarah Mitchell would like to take a Friday off for a family event."}',
     '{"request_type": "leave_request", "employee": "Sarah Mitchell", "day": "Friday"}',
     'completed', '2026-07-24 09:00:00+00', 45),
    ('40000000-0000-0000-0000-000000000011', '20000000-0000-0000-0000-000000000002', 2,
     'context_agent', '{}',
     '{"evidence_keys": ["employee_record", "leave_balance", "schedule", "team_coverage"]}',
     'completed', '2026-07-24 09:00:05+00', 1100),
    ('40000000-0000-0000-0000-000000000012', '20000000-0000-0000-0000-000000000002', 3,
     'decision_agent',
     '{"manifest": ["employee_record", "leave_balance", "schedule", "team_coverage"]}',
     '{"decision": "approve", "authorization_tier": 2}',
     'completed', '2026-07-24 09:00:06+00', 2400)
ON CONFLICT (id) DO NOTHING;

INSERT INTO agent_tool_calls
    (id, run_id, step_id, tool_name, arguments, result, success, duration_ms, called_at)
VALUES
    ('40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000002',
     '40000000-0000-0000-0000-000000000011', 'get_employee',
     '{"name": "Sarah Mitchell"}',
     '{"status": "active", "department": "Operations", "role": "Operations Specialist"}',
     TRUE, 120, '2026-07-24 09:00:05+00'),
    ('40000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002',
     '40000000-0000-0000-0000-000000000011', 'get_leave_balance',
     '{"name": "Sarah Mitchell", "leave_type": "annual"}',
     '{"status": "success", "balance_days": 10, "unit": "days"}',
     TRUE, 215, '2026-07-24 09:00:05+00'),
    ('40000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000002',
     '40000000-0000-0000-0000-000000000011', 'get_team_calendar',
     '{"team": "Operations", "date": "2026-07-31"}',
     '{"conflicts": 0, "coverage_ok": true}',
     TRUE, 340, '2026-07-24 09:00:05+00')
ON CONFLICT (id) DO NOTHING;

INSERT INTO agent_evidence
    (id, run_id, tool_call_id, evidence_type, evidence_key, evidence_value,
     retrieved_at, used_in_decision, cited_in_reason)
VALUES
    ('50000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000002',
     '40000000-0000-0000-0000-000000000001', 'employee_record', 'TC-000001',
     '{"status": "active", "department": "Operations", "role": "Operations Specialist"}',
     '2026-07-24 09:00:05+00', TRUE, TRUE),
    ('50000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002',
     '40000000-0000-0000-0000-000000000002', 'leave_balance', 'TC-000002',
     '{"status": "success", "balance_days": 10, "unit": "days"}',
     '2026-07-24 09:00:05+00', TRUE, TRUE),
    ('50000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000002',
     '40000000-0000-0000-0000-000000000003', 'schedule', 'TC-000003',
     '{"employee": "Sarah Mitchell", "shift_type": "standard"}',
     '2026-07-24 09:00:05+00', TRUE, TRUE),
    ('50000000-0000-0000-0000-000000000004', '20000000-0000-0000-0000-000000000002',
     '40000000-0000-0000-0000-000000000003', 'team_coverage', 'TC-000004',
     '{"conflicts": 0, "coverage_ok": true}',
     '2026-07-24 09:00:05+00', TRUE, TRUE)
ON CONFLICT (id) DO NOTHING;

-- ------------------------------------------------------------------
-- Agent memory
--   1) decision_precedent  -> Sarah's July Friday leave was approved.
--      Evaluation cases must NOT treat this as authority.
--   2) policy_update       -> Annual Leave Policy tightened
--      (3-day notice, blackout periods). Current policy always wins.
-- ------------------------------------------------------------------
INSERT INTO agent_memory
    (id, business_id, employee_id, memory_type, content, source_run_id,
     relevance_score, created_at, expires_at)
VALUES
    ('30000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001',
     'c0000000-0000-0000-0000-000000000101', 'decision_precedent',
     '{"subject": "Sarah Mitchell", "request_type": "leave_request",
        "day": "Friday", "decision": "approve", "authorization_tier": 2,
        "coverage": "team covered", "outcome": "approved",
        "prior_balance_days": 10}',
     '20000000-0000-0000-0000-000000000002', 0.80,
     '2026-07-27 09:00:00+00', NULL),
    ('30000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001',
     NULL, 'policy_update',
     '{"subject": "Annual Leave Policy", "policy_code": "POL-001", "version": 1,
        "effective_from": "2026-01-01",
        "changes": ["notice_days = 3", "blackout_periods_enforced = true",
                    "coverage_minimum_enforced = true"],
        "supersedes_precedents": true,
        "policy_id": "d0000000-0000-0000-0000-000000000201"}',
     NULL, 0.95, '2026-08-21 09:00:00+00', NULL)
ON CONFLICT (id) DO NOTHING;

COMMIT;