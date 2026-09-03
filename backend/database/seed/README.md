# OpsPilot — Seed Data

> **Sources of truth:** `backend/data/generator.py` (synthetic world) and
> `backend/evaluation/cases/` (frozen benchmark). Seeds 03 and 04 are
> **AUTO-GENERATED** — never edit by hand; regenerate with
> `python -m backend.data.seed` (see below). Full documentation:
> `docs/SYNTHETIC_DATA.md`.

## Seed files

| File | Purpose | Generated? |
|---|---|---|
| `01_seed_business.sql` | Business root (Acme Retail Group) only. | no |
| `04_seed_workforce.sql` | Full synthetic workforce: 6 departments, 50 employees, 10 policies, 1,960 schedules, 39 tasks, 1,446 attendance records, 6 historical decisions. | **yes** (`backend/data/generator.py`) |
| `02_seed_agent_history.sql` | One historical completed agent run (provenance chain) + 2 agent_memory rows (precedent vs. current-policy test). | no |
| `03_seed_evaluation_cases.sql` | 20 frozen evaluation cases (EVL-001..020) with deterministic ground truth. | **yes** (`backend/evaluation/cases/`) |

## Applying from a clean database

**Option A — one command (recommended):**

```bash
python -m backend.data.seed --reset
# emit -> reset -> migrations 001..006 -> seeds -> full DB validation
# exits non-zero (fail loudly) if anything is broken
```

**Option B — manual psql:**

```bash
psql -U postgres -d opspilot -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Migrations (numeric order)
psql -U postgres -d opspilot -f backend/database/migrations/001_business_data.sql
psql -U postgres -d opspilot -f backend/database/migrations/002_agent_data.sql
psql -U postgres -d opspilot -f backend/database/migrations/003_audit.sql
psql -U postgres -d opspilot -f backend/database/migrations/004_evaluation.sql
psql -U postgres -d opspilot -f backend/database/migrations/005_workforce_simulation.sql
psql -U postgres -d opspilot -f backend/database/migrations/006_simulation_codes.sql

# Seeds — ORDER MATTERS: 04 (workforce) BEFORE 02/03, which reference
# workforce rows.
psql -U postgres -d opspilot -f backend/database/seed/01_seed_business.sql
psql -U postgres -d opspilot -f backend/database/seed/04_seed_workforce.sql
psql -U postgres -d opspilot -f backend/database/seed/02_seed_agent_history.sql
psql -U postgres -d opspilot -f backend/database/seed/03_seed_evaluation_cases.sql
```

All seeds are idempotent (`ON CONFLICT DO NOTHING` / `DO UPDATE`). Dates are
**absolute** (fixed anchor `2026-08-31`), so re-running is byte-stable.

## Verification

```bash
node backend/database/verify_sql.mjs        # no server needed (PGlite)
python -m backend.data.validate             # world-level checks only
python -m backend.data.seed --reset         # full pipeline + DB validation
```

`verify_sql.mjs` runs the entire pipeline from an empty database and checks
38 invariants, including Sarah Mitchell's frozen 20/12/8 balance, the
Operations coverage math on 2026-09-04 / 09-11 / 09-18 via `team_coverage`,
the no-Michael and two-Johns preconditions, and the 6/8/4/2 evaluation-case
distribution.
