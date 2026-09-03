#!/usr/bin/env python3
"""
seed.py — One-command reproducible seed for the OpsPilot synthetic world.

Pipeline:
  1. EMIT   — regenerate the auto-generated SQL seeds from the Python
              sources of truth:
                * seed/04_seed_workforce.sql  (backend/data/generator.py)
                * seed/03_seed_evaluation_cases.sql (backend/evaluation/cases)
                * evaluation/cases/cases.json (frozen benchmark export)
  2. SEED   — optional --reset (DROP SCHEMA public CASCADE), then apply
              migrations 001..006 and seeds 01, 02, 04, 03 in order.
              Seed 03 runs LAST because it references employees/policies.
  3. VERIFY — run the full DB-level validation; FAIL LOUDLY (exit 1) if
              data integrity is broken.

Usage:
  python -m backend.data.seed                # emit + seed + verify
  python -m backend.data.seed --reset        # from a clean database
  python -m backend.data.seed --skip-db      # emit + world validation only
  python -m backend.data.seed --no-emit      # use existing seed files

Connection: DATABASE_URL, or POSTGRES_* vars, or .env, or the
docker-compose default postgresql://opspilot:opspilot@localhost:5432/opspilot
"""

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MIGRATIONS_DIR = os.path.join(ROOT, "backend", "database", "migrations")
SEEDS_DIR = os.path.join(ROOT, "backend", "database", "seed")
CASES_JSON = os.path.join(ROOT, "evaluation", "cases", "cases.json")

MIGRATIONS = [
    "001_business_data.sql",
    "002_agent_data.sql",
    "003_audit.sql",
    "004_evaluation.sql",
    "005_workforce_simulation.sql",
    "006_simulation_codes.sql",
]
# NOTE: 04 (workforce) runs BEFORE 02/03, which reference employees/policies.
SEEDS = [
    "01_seed_business.sql",
    "04_seed_workforce.sql",
    "02_seed_agent_history.sql",
    "03_seed_evaluation_cases.sql",
]

DEFAULT_DSN = "postgresql://opspilot:opspilot@localhost:5432/opspilot"

# ------------------------------------------------------------------
# Emit auto-generated artifacts
# ------------------------------------------------------------------

def emit():
    from backend.data.generator import emit_workforce_sql
    from backend.evaluation.cases import emit_cases_json, emit_cases_sql

    out04 = os.path.join(SEEDS_DIR, "04_seed_workforce.sql")
    with open(out04, "w", encoding="utf-8", newline="\n") as f:
        f.write(emit_workforce_sql())
    print(f"EMIT  {os.path.relpath(out04, ROOT)}")

    out03 = os.path.join(SEEDS_DIR, "03_seed_evaluation_cases.sql")
    with open(out03, "w", encoding="utf-8", newline="\n") as f:
        f.write(emit_cases_sql())
    print(f"EMIT  {os.path.relpath(out03, ROOT)}")

    os.makedirs(os.path.dirname(CASES_JSON), exist_ok=True)
    with open(CASES_JSON, "w", encoding="utf-8", newline="\n") as f:
        f.write(emit_cases_json())
    print(f"EMIT  {os.path.relpath(CASES_JSON, ROOT)}")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


# ------------------------------------------------------------------
# Database connection
# ------------------------------------------------------------------

def resolve_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "opspilot")
    pw = os.environ.get("POSTGRES_PASSWORD", "opspilot")
    db = os.environ.get("POSTGRES_DB", "opspilot")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def load_dotenv_if_present():
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if " " in v or "#" in v:      # ignore inline comments w/ spaces
                v = v.split(" #")[0].strip()
            os.environ.setdefault(k, v)


# ------------------------------------------------------------------
# Seed + verify pipeline
# ------------------------------------------------------------------

def run_db_pipeline(reset: bool) -> int:
    try:
        import psycopg2
    except ImportError:
        print("FATAL: psycopg2 is not installed. Run: pip install psycopg2-binary")
        return 1

    dsn = resolve_dsn()
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except Exception as e:  # fail loudly with actionable guidance
        print(f"FATAL: cannot connect to PostgreSQL at {dsn}\n  {e}")
        print("Start the database with: docker compose up -d db")
        return 1

    conn.autocommit = True
    cur = conn.cursor()
    exit_code = 0
    try:
        if reset:
            print("RESET dropping schema public ...")
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")

        print("\n-- MIGRATIONS --")
        for name in MIGRATIONS:
            path = os.path.join(MIGRATIONS_DIR, name)
            cur.execute(_read(path))
            print(f"OK    migrations/{name}")

        print("\n-- SEEDS --")
        for name in SEEDS:
            path = os.path.join(SEEDS_DIR, name)
            cur.execute(_read(path))
            print(f"OK    seed/{name}")

        print("\n-- VALIDATION --")
        from backend.data.validate import validate_database
        conn.autocommit = False
        cur = conn.cursor()
        ok, errors, report = validate_database(cur)
        conn.rollback()
        for k, v in report.items():
            print(f"  {k}: {v}")
        if not ok:
            print(f"\nSEED FAILED DATA INTEGRITY — {len(errors)} error(s):")
            for i, e in enumerate(errors[:30], 1):
                print(f"  {i}. {e}")
            exit_code = 1
        else:
            print("\nSEED COMPLETE — all database checks PASSED")
    except Exception as e:
        print(f"\nFATAL: seed pipeline failed: {e}")
        exit_code = 1
    finally:
        cur.close()
        conn.close()
    return exit_code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OpsPilot seed orchestrator")
    parser.add_argument("--reset", action="store_true",
                        help="drop schema public first (clean database)")
    parser.add_argument("--skip-db", action="store_true",
                        help="only emit artifacts + run world validation")
    parser.add_argument("--no-emit", action="store_true",
                        help="use existing seed files, do not regenerate")
    args = parser.parse_args(argv)

    if not args.no_emit:
        emit()
    else:
        print("EMIT  skipped (--no-emit)")

    print("\n-- WORLD VALIDATION --")
    from backend.data.validate import validate_world
    ok, errors, report = validate_world()
    for k, v in report.items():
        print(f"  {k}: {v}")
    if not ok:
        print(f"\nFAILED world validation — {len(errors)} error(s):")
        for i, e in enumerate(errors[:30], 1):
            print(f"  {i}. {e}")
        return 1
    print("  world checks: PASSED")

    if args.skip_db:
        print("\nDB seeding skipped (--skip-db)")
        return 0

    load_dotenv_if_present()
    return run_db_pipeline(reset=args.reset)


if __name__ == "__main__":
    raise SystemExit(main())
