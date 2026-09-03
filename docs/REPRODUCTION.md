# OpsPilot — Reproduction Guide

## Prerequisites

- **Python 3.11+** (tested on 3.13)
- **Node.js 18+**
- **PostgreSQL 15+** (or Docker Compose)
- **Git**
- **LLM API key** (OpenAI recommended, Anthropic supported)

## Quick Start (No Database)

The demo runner works without a database using FakeDB (in-memory SQLite). This is the fastest way to verify the system works.

```bash
# Clone
git clone <repo-url>
cd opspilot

# Install backend dependencies
cd backend
pip install -r requirements.txt
cd ..

# Run all demo scenarios (10/10 should pass)
PYTHONPATH=. python -m backend.scripts.run_demo

# Run specific scenario
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 1   # Leave approval
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 2   # Coverage conflict
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 3   # Termination blocked
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 4   # Constitutional violation
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 5   # Ambiguous employee
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 6   # Adversarial: fabricated employee
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 7   # Adversarial: override attempt
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 8   # Adversarial: duplicate action
PYTHONPATH=. python -m backend.scripts/run_demo --scenario 9   # Adversarial: malformed input
PYTHONPATH=. python -m backend.scripts.run_demo --scenario 10  # Adversarial: memory override
```

**Expected output:** 10/10 scenarios PASS. Unicode emoji may fail on Windows consoles — the script uses `[PASS]`/`[FAIL]` markers as fallback.

## Full Stack (With Database)

### 1. Start PostgreSQL

```bash
# Option A: Docker Compose (recommended)
docker-compose up -d postgres

# Option B: Local PostgreSQL
# Ensure PostgreSQL is running on port 5432
```

### 2. Create Database and Run Migrations

```bash
# Create database
psql -U postgres -c "CREATE DATABASE opspilot;"

# Apply migrations (in order)
psql -U postgres -d opspilot -f backend/database/migrations/001_business_data.sql
psql -U postgres -d opspilot -f backend/database/migrations/002_agent_data.sql
psql -U postgres -d opspilot -f backend/database/migrations/003_audit.sql
psql -U postgres -d opspilot -f backend/database/migrations/004_evaluation.sql

# Seed data
psql -U postgres -d opspilot -f backend/database/seed/01_seed_business.sql
psql -U postgres -d opspilot -f backend/database/seed/02_seed_agent_history.sql
psql -U postgres -d opspilot -f backend/database/seed/03_seed_evaluation_cases.sql
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env and set:
#   DATABASE_URL=postgresql://opspilot:opspilot@localhost:5432/opspilot
#   OPENAI_API_KEY=sk-...  (or ANTHROPIC_API_KEY)
#   SEED_ON_STARTUP=false
```

### 4. Start Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Verify:** `curl http://localhost:8000/health` returns `{"status":"ok"}`

### 5. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

**Verify:** Open http://localhost:3000

### 6. Run Tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
# Expected: 236 passed
```

### 7. Run Evaluation

```bash
# Baseline evaluation (no constitutional checker, no authorization gate)
curl -X POST http://localhost:8000/api/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{"system": "baseline"}'

# OpsPilot evaluation (full pipeline)
curl -X POST http://localhost:8000/api/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{"system": "opspilot"}'
```

Results are stored in `evaluation/results/`.

### 8. Run Reliability Checks

```bash
cd ..
PYTHONPATH=. python -m backend.scripts.reliability_check
```

**Expected:** All checks pass (Pydantic validation, retry logic, state machine, timeouts, error handling).

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_ENV` | No | `development` | Runtime environment |
| `DEBUG` | No | `true` | Enable debug mode |
| `API_HOST` | No | `0.0.0.0` | Backend bind address |
| `API_PORT` | No | `8000` | Backend port |
| `DATABASE_URL` | Yes* | — | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes* | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key (alternative) |
| `LLM_PROVIDER` | No | `openai` | LLM provider |
| `LLM_MODEL` | No | `gpt-4o` | LLM model name |
| `SEED_ON_STARTUP` | No | `false` | Seed database on startup |

*Required for full stack. Not required for demo runner (uses FakeDB).

## What Each Demo Scenario Tests

| # | Scenario | Tests |
|---|----------|-------|
| 1 | Sarah's leave request (normal) | Balance check, notice period, coverage, approval |
| 2 | Coverage conflict (peak Friday) | Coverage detection, escalation with approval |
| 3 | Termination blocked | Tier 3 enforcement, human approval required |
| 4 | Constitutional violation | Fabricated evidence detection, override to escalate |
| 5 | Ambiguous employee | AMBIGUOUS_EMPLOYEE handling, clarification |
| 6 | Adversarial: fabricated employee | Employee not found, system stops |
| 7 | Adversarial: override attempt | Policy override rejected, decline |
| 8 | Adversarial: duplicate action | Idempotency, no double execution |
| 9 | Adversarial: malformed input | Graceful error handling, no crash |
| 10 | Adversarial: memory override | Historical decisions treated as HISTORICAL, not policy |

## Troubleshooting

### "Unicode emoji encoding fails on Windows"
- Expected on Windows consoles. The demo runner uses `[PASS]`/`[FAIL]` markers.
- Set `PYTHONIOENCODING=utf-8` for full Unicode support.

### "ModuleNotFoundError: No module named 'backend'"
- Run from the project root (`opspilot/`), not from `backend/`.
- Ensure `PYTHONPATH=.` is set.

### "Connection refused" on PostgreSQL
- Ensure PostgreSQL is running: `docker-compose ps` or `pg_isready`
- Check `DATABASE_URL` in `.env`

### "OPENAI_API_KEY not set"
- Required for LLM agents. Set in `.env` or export as environment variable.
- Demo runner does NOT require an API key (uses FakeDB with mock responses).

### Tests fail with "FakeDB has no attribute..."
- Ensure `PYTHONPATH=.` is set when running tests.
- Run from `backend/` directory: `cd backend && PYTHONPATH=. pytest tests/ -v`

## File Structure

```
opspilot/
├── backend/
│   ├── app/
│   │   ├── agents/          # LLM Agent #1 (Context) + Agent #2 (Decision)
│   │   ├── checkers/        # Constitutional Checker + Authorization Gate
│   │   ├── llm/             # LLM provider abstraction
│   │   ├── models/          # Pydantic models (Agent, Evaluation)
│   │   ├── orchestrator/    # Workflow, Executor, EventBus
│   │   ├── routers/         # API routes (requests, approvals, audit, evaluation)
│   │   ├── tools/           # Read tools + Action tools
│   │   ├── config.py        # Settings from env vars
│   │   └── main.py          # FastAPI app
│   ├── database/
│   │   ├── migrations/      # SQL migrations (001-004)
│   │   └── seed/            # Seed data
│   ├── evaluation/          # Evaluation harness, baseline, scorer
│   ├── scripts/             # Demo runner, reliability checks
│   └── tests/               # 236 tests
├── frontend/
│   ├── app/                 # Next.js pages
│   ├── components/          # React components
│   └── lib/                 # SSE client, services
├── docs/                    # Documentation (CHANGELOG, SAFETY, TOOLS, etc.)
├── evaluation/
│   ├── cases/               # 20 frozen evaluation cases
│   ├── results/             # Baseline + OpsPilot results
│   └── trajectories/        # 4 exported trajectories
└── .env.example             # Environment template
```
