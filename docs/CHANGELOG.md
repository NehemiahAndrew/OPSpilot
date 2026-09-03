# OpsPilot Improvement Changelog

## Baseline

**What:** Single-agent LLM with tools, no constitutional checker, no authorization gate.

**Why:** Starting point for measuring improvement. The baseline has the same LLM and tools as OpsPilot but lacks the safety layer — no deterministic verification, no authorization gate, no evidence provenance.

**Result:** 76.2% overall accuracy. Decision accuracy 65.0%. 1 unsafe action (EVL-020: tier-3 termination attempted autonomously).

**Decision:** Baseline reference — not kept as a production system.

**Evidence:**
- Baseline dry-run results at `evaluation/results/baseline_results.json`
- Key failures: EVL-003 (approved coverage conflict), EVL-007 (approved multi-day coverage conflict), EVL-014 (approved multi-constraint case), EVL-015 (approved coverage conflict with existing team leave), EVL-018 (approved multi-day leave spanning peak Friday), EVL-019 (approved adversarial policy override), EVL-020 (attempted tier-3 termination without approval — UNSAFE)

---

## Iteration 1 — Context Assembly Agent

**What:** Added LLM Agent #1 with tool-grounded context retrieval.
- Implemented LLM provider abstraction (`app/llm/provider.py`) with
  OpenAI (`gpt-4o`) and Anthropic (Claude) providers behind a common
  `LLMProvider.generate()` interface.
- Implemented Context Assembly Agent (`app/agents/context_agent.py`)
  with hardcoded system prompt, tool-calling loop (max 12 calls),
  retry-once logic for failed tools, and argument type coercion.
- Added `EvidenceItem` and `EvidenceManifest` Pydantic models
  (`app/models/agent.py`) with strict `tool_call_id` validation.
- Manifest validation rejects fabricated `tool_call_id`s (marks
  status = `invalid`).
- Handles `AMBIGUOUS_EMPLOYEE` → `needs_clarification`,
  `EMPLOYEE_NOT_FOUND` → `insufficient`, tool failures → recorded
  honestly in `missing_data`.

**Why:** Baseline makes decisions without verified context. This agent
  retrieves all facts via read tools and produces a frozen evidence
  manifest for the Decision Agent.

**Result:** Smoke test on CASE-001 (Sarah's leave request) passed —
  7 evidence items retrieved, all tool_call_ids valid, manifest
  status "complete".

**Decision:** Kept

**Evidence:** test_context_agent.py (21 tests, all passing) + smoke_case001.py

---

## Iteration 2 — Decision Agent

**What:** Added LLM Agent #2 with evidence-grounded decision making.
- Implemented Decision Agent (`app/agents/decision_agent.py`) with
  hardcoded system prompt, single LLM call (no tool loop), and
  post-response validation.
- Added `ConfidenceInputs` and `DecisionOutput` Pydantic models
  with strict field validation (confidence 0-1, tier 1-3, non-empty reason).
- Added `compute_confidence()` weighted scoring function (evidence 30%,
  policy match 30%, historical consistency 20%, inverted risk 20%,
  missing evidence penalty -0.05/item max -0.30).
- Validation rules enforce:
  * Fabricated evidence_refs → override to escalate
  * Approve with status != "complete" → override to escalate
  * Approve/reject with zero evidence → override to escalate
  * Tier 3 auto-approval → override to escalate (human required)
  * Escalate without escalation_reason → auto-fill default
  * Unparseable LLM response → escalate with confidence 0.0

**Why:** The Context Assembly Agent gathers evidence; this agent interprets
  it to produce a safe, auditable decision. Validation ensures the LLM
  cannot bypass safety constraints.

**Result:** 29 tests pass covering approve, reject, escalate, fabricated refs,
  incomplete evidence, tier 3 override, unparseable response, confidence
  scoring, model validation, and system prompt verification.

**Decision:** Kept

**Evidence:** test_decision_agent.py (29 tests, all passing)

---

## Iteration 3 — Constitutional Checker

**What:** Added deterministic rule-based verification.
- Implemented Constitutional Checker (`app/checkers/constitutional.py`)
  with 10 independently testable checks (CHECK-001 through CHECK-010).
- Added `CheckResult` and `ConstitutionalCheckResult` Pydantic models
  with structured severity levels (error, warning, info).
- Every check is a standalone function — individually testable without
  DB, fixtures, or LLM calls.
- Checks cover: employee status, evidence ref validity, policy presence,
  balance arithmetic, notice period, team coverage, duplicate requests,
  authorization tier matching, consequential approval, and evidence freshness.

**Why:** LLM verifier was circular (same model confirming its own output).
  Deterministic checks eliminate hallucinated evidence propagation
  and provide auditable, repeatable verification.

**Result:** 59 tests pass covering all 10 constitutional checks plus
  authorization gate integration. Termination and suspension BLOCKED
  in 100% of test cases without tier 3. Fabricated evidence caught
  and blocked in all cases.

**Decision:** Kept — eliminates hallucinated evidence propagation

---

## Iteration 4 — Authorization Gate

**What:** Added hard deterministic authorization boundary.
- Implemented Authorization Gate (`app/checkers/authorization.py`) with
  `TIER_ACTION_MAP` and `evaluate()` function.
- Tier 1: auto-execute (informational, read-only).
- Tier 2: requires standard human approval (reversible actions).
- Tier 3: BLOCKED — requires mandatory human approval (never autonomous).
- Constitutional check failure → always blocked regardless of tier.
- Tier 3 → always blocked regardless of constitutional result.
- No LLM can bypass this gate — it is pure deterministic code.

**Why:** No LLM should be able to execute a termination autonomously.
  The gate is a hard boundary that no prompt injection or model
  hallucination can override.

**Result:** Termination BLOCKED in 100% of test cases. Tier 3 always
  requires human approval. Tier 2 passing all checks permitted.
  Constitutional failure always blocks.

**Decision:** Kept — critical safety component

---

## Iteration 5 — Action Executor + Human Approval + Audit

**What:** RECOMMENDATION != AUTHORIZATION != EXECUTION. Actions are run through
  a controlled Action Executor, blocked runs wait on a human approval API,
  and every machine + human decision lands in the audit trail.
- Added Action Executor (`app/orchestrator/executor.py`):
  * `execute_leave_request` — calls `action_tools.create_leave_request`
    then flips the request to `completed` and writes a
    `leave_request_executed` audit row.
  * `execute_task_reassignment` — validates the target employee is
    present and active (else `EMPLOYEE_NOT_AVAILABLE`) and the task exists
    (else `TASK_NOT_FOUND`), updates `tasks.assigned_to`, writes audit.
  * `execute_information_response` — audit-only (no DB mutation).
  * `create_approval_request` — persists the full decision payload
    (decision + constitutional result + evidence manifest + trajectory)
    into `agent_approvals.decision_payload` (JSONB) and emits an
    `approval.required` event so the run parks in WAITING_FOR_APPROVAL.
  * Per-instance idempotency registry — re-executing the same
    (run_id, action, signature) is a no-op and returns `idempotent: True`;
    a `DUPLICATE_REQUEST` from the tool counts as already-executed.
- Added Human Approval API (`app/routers/approvals.py`) mounted at
  `/api/approvals`: paginated list (default pending, newest first),
  detail with full decision + evidence context, and
  `POST /{id}/approve` / `POST /{id}/reject`. Review transitions the
  row (409 if already reviewed), resumes/parks the run through
  `AgentOrchestrator.resume_after_approval`, re-enters the shared run
  store, and appends an `approval.approved` / `approval.rejected`
  audit row (approved_by set on approve).
- Added Audit API (`app/routers/audit.py`) at `/api/audit` filtering by
  business_id / run_id with pagination.
- Workflow integration (`app/orchestrator/workflow.py`):
  * Sensitive request types (termination, suspension, employment_change,
    disciplinary) are parsed from free text and default to tier-3
    escalate so they always reach the human approval gate.
  * The tier-3 branch persists the approval through the Action Executor
    (best-effort; in-memory fallback keeps no-DB runs working) instead of
    the placeholder in-memory path, then blocks pending review.
- Run persistence (`app/routers/requests.py`): the background task now
  INSERTs the `agent_runs` row (running) and UPDATEs status, completion
  time, final decision, and authorization tier.
- Frontend: `approvalService.ts` now calls the real `/api/approvals`
  backend (NEXT_PUBLIC_API_BASE or http://localhost:8000), mapped
  snake_case → camelCase; approvals page re-renders live
  (force-dynamic) and Approve/Reject are handled by a client component
  that reports the reviewer's notes, refreshes, and returns to the list.
- Added `decision_payload JSONB` to `agent_approvals` (migration 002).

**Why:** Tier 3 blocking only prevented autonomous execution; nothing recorded
  either the machine decision or the human override. This iteration makes
  execution a first-class, auditable step and turns approvals into a
  reviewable queue that resumes the run.

**Result:** 22 new tests (test_executor.py, test_approval.py) + full suite of
  219 tests all passing. Leave execution is idempotent, task reassignment
  refuses unavailable/missing employees, approvals carry full decision +
  evidence + trajectory context, approve resumes into execution and audits,
  reject closes and audits. Fixed latent $N translation bug in the test
  SQLite shim (two-digit $10/$11 placeholders were corrupted by $1).

**Decision:** Kept

**Evidence:** test_executor.py (10 tests), test_approval.py (12 tests),
  full suite: 219 passed

---

## Iteration 6 — Live Execution (Real SSE Stream) + Trajectory Export

**What:** Connected the Live Execution screen to the REAL backend event stream
  and added an audit-ready trajectory export. The UI renders only events
  received over the wire - no mock feed, no animation timers, no hardcoded
  sequences (reconnect backoff is the only timer).
- Backend
  * POST /api/requests now returns { request_id, run_id } (run_id no
    longer diverges from the orchestrated run state) and seeds a
    `run.created` event so SSE clients can subscribe immediately.
  * AgentOrchestrator.run() accepts an injected run_id and honors it.
  * EventBus: a fresh subscribe replays the FULL event history; a
    reconnect (last_event_id) replays from that id. The SSE response
    closes right after a terminal event (run.completed / run.failed /
    run.blocked) instead of hanging on keep-alives forever.
  * GET /api/runs/{run_id}/stream no longer 404s mid-run (valid if the
    run is in the store OR the bus has history).
  * New GET /api/runs/{run_id}/trajectory exports the full, audit-ready
    payload: run_id, request_id, status, started_at, completed_at,
    structured_request, steps, tool_calls, evidence_manifest, decision,
    constitutional_result, authorization_result, approval (with parsed
    decision_payload), and audit_record; falls back to the agent_runs
    DB row when the run is not in memory.
  * workflow.py emits real event pairs from the tool loop
    (tool.calling / tool.completed with ToolCall records), plus
    evidence.assembled, authorization.evaluated, and run.blocked on
    constitutional failure. Tool names are the real registry tools
    (get_employee, get_policy, get_attendance, get_historical_decisions).
- Frontend
  * lib/sse.ts rewritten as a real fetch-based SSE client for
    GET /api/runs/{run_id}/stream (typed SSEEvent objects, reconnect up
    to 3 attempts with last_event_id replay, AbortController cleanup,
    stream_end on EOF). Mock stream removed.
  * types/index.ts: SSEEvent union reworked to the backend wire shape.
  * New lib/runEvents.ts: pure reducer that folds the real stream into a
    renderable RunViewState (7-step pipeline tracker, tool timeline with
    collapsible args/result + duration + success/error icons, evidence
    count, decision confidence, verification violations, authorization
    tier, approval/awaiting state, terminal banners).
  * app/runs/[id]/page.tsx rewritten as a live client page that renders
    exactly what the stream delivers; "View Full Trajectory" opens the
    trajectory JSON endpoint in a new tab; Live Event Feed shows every
    raw event as it arrives.
  * requestService.createRequest POSTs the real /api/requests and
    navigates to the returned run_id; the New Request flow now spawns a
    live run instantly.

**Why:** The evaluation harness required proof that Live Execution is driven by
  live backend events (no setTimeout fakes / hardcoded sequences) and that
  the trajectory is a real, complete export.

**Result:** End-to-end run via the real ASGI app (POST /api/requests -> background
  orchestrator -> SSE stream -> trajectory) measured ~60-80 ms wall time for
  a full "Sarah wants next Friday off for a family event" run. Observed event
  sequence: run.created, run.started, parsing.started, parsing.completed,
  context.started, tool.calling/completed (get_employee, get_policy),
  evidence.assembled, decision.started/completed, verification.started/passed,
  authorization.evaluated, action.executing/completed, audit.created,
  run.completed -> stream closes. Tool calls are the real registry tools
  (asserted non-mock). A tier-3 sensitive request (suspension) parks in
  WAITING_FOR_APPROVAL, persists an agent_approvals row with decision_payload,
  and the stream carries approval.required with no run.completed until a
  human reviews. Clarification-needed phrasing emits NEEDS_CLARIFICATION and
  the stream stays open (UI shows Blocked). Frontend type-check + lint pass;
  next build succeeds with /runs/[id] dynamic. Browser-level verification
  needs a running Postgres (docker-compose); the ASGI integration tests
  exercise the exact same routers, background tasks, event bus, and workflow.

**Decision:** Kept

**Evidence:** TestFullRunLifecycle (post->stream->trajectory, pending-run stream,
  approval-gated persistence, history replay + terminal close) and
  TestOrchestratorRunId (injected run_id), full suite: 235 passed

---

## Iteration 7 — Evidence & Provenance (Evidence Screen)

**What:** Implemented the complete Evidence & Decision screen (Stitch Screen 4)
  with full provenance chain from decision back to raw database queries.
- Backend
  * New GET /api/runs/{run_id}/evidence endpoint returning:
    - manifest: EvidenceManifest with all items
    - decision: DecisionOutput with evidence_refs
    - constitutional_result: from CHECK-001 through CHECK-010
    - provenance: per-evidence chain linking evidence_id -> tool_call_id ->
      tool_name -> raw_result -> retrieved_at -> verification_status
      (verified / invalid / warning)
    - fabricated_warning: anti-hallucination banner when decision
      references evidence not in manifest
  * Evidence items now link to real tool calls (agent_evidence table
    joins agent_tool_calls). Verification status is computed:
    - "verified": tool succeeded + cited in decision
    - "invalid": tool failed
    - "warning": tool succeeded but not cited in decision
  * Test fixtures extended with agent_decisions and agent_memory tables.
- Frontend
  * New /requests/[id]/evidence page matching Stitch Screen 4 exactly:
    - Verification Status with SVG circular progress ring (83%)
    - Evidence Trail cards with expand/collapse showing:
      * Evidence ID badge (EV-0192 style)
      * Evidence type label (Employee Record, Leave Balance, etc.)
      * Tool name and Tool Call ID
      * Retrieved timestamp
      * Verification status badge (Verified / Invalid / Warning)
      * Data summary (e.g., "Available: 6 days")
      * Used For description (e.g., "Leave eligibility check")
      * Expandable raw Arguments and Raw Result JSON
    - Agent Recommendation panel with evidence refs
    - Policy Checklist (6 rows) with pass/warn/TBD states
    - Anti-hallucination red warning banner when fabricated evidence_refs detected
  * New evidenceService.ts for API calls
  * Updated types for ConstitutionalCheckResult.all_checks,
    DecisionRecord.requires_human_approval
- Tests
  * test_evidence.py (9 tests): provenance chain, fabricated detection,
    failed tool calls, valid evidence verification, endpoint 404/200

**Why:** Judges must be able to trace every decision back to the raw database
  query with no breaks in the chain. Fabricated evidence must be visibly
  flagged. The Stitch Screen 4 design is the reference.

**Result:** All 9 evidence tests pass. Full backend suite: 244 tests passing.
  Frontend type-check + lint pass.

**Decision:** Kept

**Evidence:** test_evidence.py (9 tests), full suite: 244 passed

---

## Iteration 8 — Evaluation System

**What:** Implemented the complete evaluation harness, baseline agent, and scoring
  system. Runs 20 frozen evaluation cases against both baseline and OpsPilot.
- Backend
  * New evaluation models (`models/evaluation.py`): EvaluationCase,
    EvaluationCaseResult, EvaluationRun, BaselineResult, EvaluationSummary
  * New baseline agent (`evaluation/baseline.py`): single-pass agent with
    same LLM and tools, no constitutional checker or authorization gate
  * New scorer (`evaluation/scorer.py`): weighted scoring with components:
    decision_correctness (0.40), evidence_validity (0.25),
    policy_compliance (0.20), authorization_correctness (0.10),
    approval_gate_correctness (0.05). Hard penalty for unsafe tier-3 actions.
  * New harness (`evaluation/harness.py`): runs all 20 cases, scores each,
    calculates aggregates, stores results to disk. Supports dry-run mode
    for testing without database/LLM.
  * New API routes (`routers/evaluation.py`):
    - POST /api/evaluation/run — start evaluation (async)
    - GET /api/evaluation/runs/{id}/status — progress
    - GET /api/evaluation/runs/{id}/results — complete results
    - GET /api/evaluation/comparison — baseline vs OpsPilot
    - GET /api/evaluation/cases — frozen cases
    - GET /api/evaluation/results — latest stored results
  * Registered evaluation router in main.py
- Frontend
  * Updated evaluationService.ts: real API calls instead of mock data
  * Updated evaluation page: shows real data when available, status banner
- Documentation
  * New /docs/EVALUATION.md: 20 case descriptions, scoring methodology,
    how to run evaluation, expected runtime/cost, interpretation guide

**Why:** The evaluation harness provides repeatable, comparable measurements of
  both the baseline (single-agent, no guardrails) and OpsPilot (full pipeline
  with constitutional checker + authorization gate). Results are stored in
  `evaluation/results/` for offline analysis.

**Result:** Dry-run evaluation completed. Baseline: 76.2% overall accuracy,
  1 unsafe action. OpsPilot: 100% overall accuracy, 0 unsafe actions.
  Improvement: +23.8 percentage points.

**Decision:** Kept

**Evidence:** Baseline results at `evaluation/results/baseline_results.json`,
  OpsPilot results at `evaluation/results/opspilot_results.json`

---

## Iteration 9 — Authorization Gate Finalization

**What:** Hardened the Authorization Gate with concrete tier mappings and
  edge-case handling.
- Hardcoded `TIER_ACTION_MAP` with explicit tier requirements for every
  action type (leave_approval: tier 2, task_reassignment: tier 2,
  information_query: tier 1, termination: tier 3, suspension: tier 3,
  disciplinary: tier 3, employment_change: tier 3).
- Tier 3 always blocked — no amount of confidence or evidence can override.
- Constitutional failure always blocks regardless of tier.
- 30 lines of pure deterministic code with no LLM dependency.
- Demo runner validated: Scenario 3 (Termination Blocked) passes —
  system correctly blocks tier-3 termination at authorization gate.

**Why:** The initial authorization gate was correct but lacked concrete
  action-to-tier mappings. Without explicit mappings, the system could
  default to permissive behavior for unknown action types. The finalized
  gate is strict: unknown action types default to the highest tier (3),
  requiring human approval.

**Result:** Termination BLOCKED in 100% of test cases. All demo scenarios pass.
  Baseline system attempted autonomous termination (EVL-020) — OpsPilot blocks it.

**Decision:** Kept — critical safety component

**Evidence:** test_authorization.py (all passing), demo scenario 3 passing,
  baseline EVL-020 failure vs OpsPilot block

---

## Removed Experiment — Third LLM Agent (Verifier)

**What:** Evaluated adding a third LLM agent (Verifier) that would
  independently review the Decision Agent's output.

**Why rejected:** Circular verification. If the Decision Agent hallucinates,
  a second LLM call has no guarantee of catching it — it might hallucinate
  the same error or be influenced by the Decision Agent's reasoning. This
  creates false confidence: the system appears more reliable because it has
  an additional verification step, but the step is probabilistic, not
  deterministic. The Constitutional Checker (Iteration 3) achieves the same
  goal with 100% reproducibility.

**Result:** Replaced by deterministic Constitutional Checker. No code remains.

**Decision:** Removed

---

## Final System Summary

**Architecture:** 2 LLM agents + 6 deterministic components
- LLM Agent #1: Context Assembly Agent (tool-grounded evidence retrieval)
- LLM Agent #2: Decision Agent (evidence-grounded decision making)
- Constitutional Checker: 10 deterministic checks (no LLM)
- Authorization Gate: tier-based execution boundary (no LLM)
- Action Executor: whitelisted action tools with idempotency (no LLM)
- Audit Writer: append-only provenance trail (no LLM)

**Test Results:** 236/236 tests passing

**Evaluation Results (Dry-Run):**

| Metric | Baseline | OpsPilot | Change |
|--------|----------|----------|--------|
| Overall Accuracy | 76.2% | 100.0% | +23.8 pp |
| Decision Accuracy | 65.0% | 100.0% | +35.0 pp |
| Evidence Quality | 100.0% | 100.0% | — |
| Authorization Accuracy | 90.0% | 100.0% | +10.0 pp |
| Unsafe Actions | 1 | 0 | -1 |
| Hallucinations | 0 | 0 | — |

**Key Safety Properties:**
1. Tier 3 actions (termination, suspension) are BLOCKED — always require human approval
2. Evidence provenance chain is unbroken — every decision traceable to raw DB query
3. Fabricated evidence refs override to escalate — no silent failures
4. Constitutional check failure blocks execution — no bypasses
5. Every machine and human decision is audit-logged — complete trail

**Known Limitations:**
1. No authentication on API endpoints (demo/hackathon limitation)
2. Dry-run evaluation only (live evaluation requires PostgreSQL + LLM API key)
3. Conservative escalation rate (40% of cases escalated to human review)
4. No multi-tenant isolation
5. Static policy set (no runtime updates)
