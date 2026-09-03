// verify_sql.mjs — run the FULL OpsPilot SQL pipeline (migrations + seeds)
// from a clean database against PGlite (embedded PostgreSQL), then verify
// data integrity. This is the no-server check used by CI; for a live server
// use `python -m backend.data.seed --reset` instead.
import { PGlite } from '@electric-sql/pglite';
import fs from 'fs';
import path from 'path';

const ROOT = path.resolve(import.meta.dirname, '..', '..');

function readSQL(rel) {
    return fs.readFileSync(path.join(ROOT, rel), 'utf-8');
}

const MIGRATIONS = [
    'backend/database/migrations/001_business_data.sql',
    'backend/database/migrations/002_agent_data.sql',
    'backend/database/migrations/003_audit.sql',
    'backend/database/migrations/004_evaluation.sql',
    'backend/database/migrations/005_workforce_simulation.sql',
    'backend/database/migrations/006_simulation_codes.sql',
];
// Seed 02/03 reference workforce rows, so 04 (workforce) runs before them.
const SEEDS = [
    'backend/database/seed/01_seed_business.sql',
    'backend/database/seed/04_seed_workforce.sql',
    'backend/database/seed/02_seed_agent_history.sql',
    'backend/database/seed/03_seed_evaluation_cases.sql',
];

async function main() {
    const db = await PGlite.create();
    let allPass = true;

    for (const f of [...MIGRATIONS, ...SEEDS]) {
        try {
            await db.exec(readSQL(f));
            console.log(`OK   ${f}`);
        } catch (e) {
            console.error(`FAIL ${f}\n     ${e.message}`);
            allPass = false;
        }
    }
    if (!allPass) process.exit(1);

    const checks = [
        ["SELECT COUNT(*) FROM businesses", 1, "businesses"],
        ["SELECT COUNT(*) FROM departments", 6, "departments (6)"],
        ["SELECT COUNT(*) FROM employees", 50, "employees (50)"],
        ["SELECT COUNT(*) FROM leave_balances", 50, "leave_balances (50)"],
        ["SELECT COUNT(*) FROM company_policies", 10, "company_policies (10)"],
        ["SELECT COUNT(*) FROM schedules", 1960, "schedules (1960)"],
        ["SELECT COUNT(*) FROM tasks", 39, "tasks (39)"],
        ["SELECT COUNT(*) FROM attendance_records", 1446, "attendance_records (1446)"],
        ["SELECT COUNT(*) FROM historical_decisions", 6, "historical_decisions (6)"],
        ["SELECT COUNT(*) FROM evaluation_cases", 20, "evaluation_cases (20)"],
        ["SELECT COUNT(*) FROM agent_memory", 2, "agent_memory (2)"],
        ["SELECT lb.remaining_days FROM leave_balances lb JOIN employees e ON e.id = lb.employee_id WHERE e.emp_code = 'EMP-001' AND lb.leave_type = 'annual'", 8, "Sarah (EMP-001) remaining_days = 8"],
        ["SELECT annual_entitlement FROM leave_balances lb JOIN employees e ON e.id = lb.employee_id WHERE e.emp_code = 'EMP-001'", 20, "Sarah entitlement = 20"],
        ["SELECT used_days FROM leave_balances lb JOIN employees e ON e.id = lb.employee_id WHERE e.emp_code = 'EMP-001'", 12, "Sarah used_days = 12"],
        ["SELECT remaining_days FROM leave_balances lb JOIN employees e ON e.id = lb.employee_id WHERE e.emp_code = 'EMP-005'", 1, "Daniel (EMP-005) remaining_days = 1"],
        ["SELECT COUNT(*) FROM leave_balances WHERE remaining_days <> annual_entitlement - used_days OR remaining_days < 0", 0, "leave balances internally consistent"],
        ["SELECT COUNT(*) FROM employees WHERE lower(first_name) = 'michael'", 0, "no employee named Michael (EVL-005)"],
        ["SELECT COUNT(*) FROM employees WHERE first_name = 'John'", 2, "exactly 2 Johns (EVL-006)"],
        ["SELECT effective_coverage FROM team_coverage WHERE department_name = 'Operations' AND coverage_date = DATE '2026-09-04'", 4, "team_coverage Operations 2026-09-04 = 4 (EVL-001 approve path)"],
        ["SELECT effective_coverage FROM team_coverage WHERE department_name = 'Operations' AND coverage_date = DATE '2026-09-11'", 3, "team_coverage Operations 2026-09-11 = 3 (EVL-003 conflict path)"],
        ["SELECT effective_coverage FROM team_coverage WHERE department_name = 'Operations' AND coverage_date = DATE '2026-09-18'", 3, "team_coverage Operations 2026-09-18 = 3 (EVL-015)"],
        ["SELECT s.status FROM schedules s JOIN employees e ON e.id = s.employee_id WHERE e.emp_code = 'EMP-003' AND s.shift_date = DATE '2026-09-10'", 'SICK', "David Chen SICK on 2026-09-10 (EVL-011)"],
        ["SELECT s.status FROM schedules s JOIN employees e ON e.id = s.employee_id WHERE e.emp_code = 'EMP-005' AND s.shift_date = DATE '2026-09-14'", 'LEAVE', "Daniel on LEAVE 2026-09-14 (EVL-016)"],
        ["SELECT COUNT(*) FROM tasks WHERE task_code IN ('TASK-001','TASK-002','TASK-003')", 3, "scenario tasks TASK-001..003 present"],
        ["SELECT COUNT(*) FROM tasks t JOIN employees e ON e.id = t.assigned_to WHERE t.assigned_to IS NOT NULL AND e.id IS NULL", 0, "no orphan tasks"],
        ["SELECT COUNT(*) FROM attendance_records a JOIN employees e ON e.id = a.employee_id WHERE e.emp_code = 'EMP-002' AND a.status = 'late'", 4, "John Carter 4 late records (EVL-010/017)"],
        ["SELECT COUNT(*) FROM attendance_records a JOIN employees e ON e.id = a.employee_id WHERE e.emp_code = 'EMP-002' AND a.status = 'formal_warning'", 2, "John Carter 2 formal warnings (EVL-017)"],
        ["SELECT COUNT(*) FROM historical_decisions WHERE decision_code = 'DEC-004' AND reason ILIKE '%override%'", 1, "DEC-004 conflicting precedent present (EVL-013)"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE difficulty = 'easy'", 6, "evaluation easy cases (6)"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE difficulty = 'medium'", 8, "evaluation medium cases (8)"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE difficulty = 'hard'", 4, "evaluation hard cases (4)"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE difficulty = 'adversarial'", 2, "evaluation adversarial cases (2)"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE ground_truth_reason IS NULL OR ground_truth_reason = ''", 0, "every case has ground truth"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE context = '{}'::jsonb", 0, "every case has structured context"],
        ["SELECT COUNT(*) FROM evaluation_cases c WHERE c.employee_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM employees e WHERE e.id = c.employee_id)", 0, "no case references a missing employee"],
        ["SELECT COUNT(*) FROM evaluation_cases c, UNNEST(c.expected_policy_applied) p WHERE NOT EXISTS (SELECT 1 FROM company_policies pol WHERE pol.id = p)", 0, "no case references a missing policy"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE case_number = 'EVL-020' AND expected_decision_type = 'block' AND expected_authorization_tier = 3 AND expected_approval_required = TRUE", 1, "EVL-020 termination blocked / tier 3 / approval required"],
        ["SELECT COUNT(*) FROM evaluation_cases WHERE case_number = 'EVL-019' AND expected_decision_type = 'decline'", 1, "EVL-019 user instruction cannot override policy"],
    ];

    console.log("\n--- VERIFICATION QUERIES (clean database) ---");
    for (const [sql, expected, name] of checks) {
        try {
            const r = await db.exec(sql);
            const row = r[0].rows[0];
            const actual = row[Object.keys(row)[0]];
            const num = Number(actual);
            const pass = (Number.isFinite(num) && typeof expected === 'number')
                ? num === expected
                : String(actual) === String(expected);
            if (!pass) allPass = false;
            console.log(`${pass ? 'PASS' : 'FAIL'} ${name} (got ${actual})`);
        } catch (e) {
            allPass = false;
            console.error(`FAIL ${name} — query error: ${e.message}`);
        }
    }

    console.log(`\n${allPass ? 'ALL CHECKS PASSED' : 'SOME CHECKS FAILED'}`);
    process.exit(allPass ? 0 : 1);
}

main().catch(e => { console.error(e); process.exit(1); });
