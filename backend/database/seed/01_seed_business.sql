-- ============================================================
-- seed/01_seed_business.sql
-- OpsPilot — Business root (Acme Retail Group)
--
-- The full synthetic workforce (departments, employees, policies,
-- schedules, tasks, attendance, historical decisions) is seeded by
-- seed/04_seed_workforce.sql, generated from backend/data/generator.py.
-- This seed only creates the tenant root so later seeds have a
-- stable business_id.
--
-- Deterministic IDs are used throughout. See docs/SYNTHETIC_DATA.md.
-- ============================================================

BEGIN;

INSERT INTO businesses (id, name)
VALUES ('a0000000-0000-0000-0000-000000000001', 'Acme Retail Group')
ON CONFLICT (id) DO NOTHING;

COMMIT;