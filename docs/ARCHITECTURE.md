# OpsPilot — Architecture

> **Status:** scaffold (Prompt 2). Implementation lands in later prompts.
> **Sources of truth:** `docs/STITCH_INVENTORY.md` · `docs/STITCH_DATA_MAP.md` · `docs/STITCH_GAPS.md`.
> **Scope rule:** exactly **two** LLM agents (Context Assembly, Decision). Every other component is deterministic code.

---

## 1. System context

OpsPilot resolves employee operational requests (leave, reassignment, policy
queries, HR actions) through a supervised pipeline that separates **facts
gathering** from **judgment** from **guardrails**. The UI mirrors the Stitch
output screen-for-screen (7 designed screens — `STITCH_INVENTORY.md` §1).

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router) · React 18 · TypeScript (strict) · Tailwind CSS · shadcn/ui · Lucide React |
| Backend | Python 3.11+ · FastAPI · Pydantic v2 · asyncpg · httpx · python-dotenv |
| Database | PostgreSQL 15 (Supabase hosted; local via docker-compose) |
| Realtime | Server-Sent Events (SSE), native FastAPI streaming responses |
| LLM | Provider-agnostic (`app/llm/provider.py`); default OpenAI `gpt-4o`; fallback-ready Anthropic Claude & DeepSeek |
| Containers | Docker + docker-compose (frontend / backend / postgres) |

---

## 2. Agent pipeline (ASCII diagram)

```text
 User Request  (composer)  POST /api/v1/requests
        |
        v
 [1 Request Parser]              DETERMINISTIC, no LLM
 |   request_type, intent, employee_hint, dates, claims, confidence
 v
 [2 Context Assembly Agent]      LLM AGENT #1
 |   calls READ TOOLS only: employee, balance, calendar, policy DB,
 |   historical index. Every tool I/O becomes an evidence record.
 v
 [3 Evidence Manifest]           DETERMINISTIC, no LLM
 |   append-only provenance chain; TC-*/EV-* ids; payload hashes.
 |   Evidence is frozen here.
 v
 [4 Decision Agent]              LLM AGENT #2
 |   reads the manifest ONLY. Emits: decision (approve/decline/block/
 |   inform/escalate/request_info), reasoning, risk, evidence refs.
 v
 [5 Constitutional Checker]      DETERMINISTIC, no LLM
 |   policy checklist rows per request_type: pass / fail / needs_review
 v
 [6 Authorization Gate]          DETERMINISTIC, no LLM
 |   tier = f(request_type, risk, policy deny, side effects)
 |   Tier 1 / Tier 2 / Tier 3 (definitions in section 7)
 |
 +--> Tier 1 : auto-execute (informational / read-only)
 +--> Tier 2 : standard human approval
 +--> Tier 3 : BLOCKED -> Tier-3 override requested -> mandatory
 |            human approval (never autonomous)
 v
 [7 Action Executor]             DETERMINISTIC, no LLM
 |   executes CONTROLLED action tools only (whitelisted registry)
 v
 [8 Audit Writer]                DETERMINISTIC, no LLM
 |   append-only audit: events, tool calls, decisions, approvals
 v
 [9 Evaluation Harness]          OFFLINE, not in the runtime path
     golden dataset -> replay -> deterministic scores + LLM-as-a-Judge
```

| # | Stage | Implementation | Type |
|---|-------|----------------|------|
| 1 | Request Parser | `app/orchestrator/workflow.py` + rules | DETERMINISTIC |
| 2 | Context Assembly Agent | `app/agents/context_agent.py` + `app/tools/read_tools.py` | **LLM #1** |
| 3 | Evidence Manifest | `app/orchestrator/state.py` + `app/models/business.py` | DETERMINISTIC |
| 4 | Decision Agent | `app/agents/decision_agent.py` | **LLM #2** |
| 5 | Constitutional Checker | `app/checkers/constitutional.py` | DETERMINISTIC |
| 6 | Authorization Gate | `app/checkers/authorization.py` | DETERMINISTIC |
| 7 | Action Executor | `app/tools/action_tools.py` via `app/tools/registry.py` | DETERMINISTIC |
| 8 | Audit Writer | `app/orchestrator/events.py` | DETERMINISTIC |
| 9 | Evaluation Harness | `app/evaluation/{harness,baseline,scorer}.py` | OFFLINE |

### Run lifecycle (state machine)

```text
pending -> parsed -> gathering_context -> manifest_ready -> deciding
       -> constitutional_check -> authorization
       -> [tier1] auto_execute
       -> [tier2] awaiting_approval
       -> [tier3] blocked -> tier3_override_requested
       -> executing -> completed | aborted | failed
```

## 3. Two-LLM-agent rationale

1. **Deterministic parser first.** Extraction of `request_type` / employee / dates
   is rule-based, so wrong-entity errors never reach the LLMs.
2. **Facts vs judgment.** Context Assembly *only* gathers and cites evidence (read
   tools). Decision reviews a **frozen** manifest — it cannot invent or fetch new
   facts at decision time. This is what makes evidence grounding measurable.
3. **Guardrails are code, not prompts.** Constitutional Check and the
   Authorization Gate can always veto an LLM recommendation; a Tier-3 block cannot
   be bypassed by a prompt injection.
4. **Auditability.** Exactly two LLM call sites — errors attribute to a single
   agent, and trajectories replay deterministically.
5. **Cost/latency/robustness.** Two LLM calls per request keeps latency, spend, and
   prompt-fragility surface predictable.

## 4. Deterministic component list

| Component | File | Responsibility |
|---|---|---|
| Request Parser | `app/orchestrator/workflow.py` | rule-based intent/entity extraction |
| Evidence Manifest builder | `app/orchestrator/state.py` | freeze, index, hash evidence chain |
| Constitutional Checker | `app/checkers/constitutional.py` | policy checklist pass/fail/TBD (UI: Evidence screen checklist) |
| Authorization Gate | `app/checkers/authorization.py` | tier + approval-required classification |
| Action Executor | `app/tools/action_tools.py` + `app/tools/registry.py` | whitelisted post-gate executions |
| Audit Writer | `app/orchestrator/events.py` | append-only event persistence |
| SSE fan-out | `app/orchestrator/events.py` + routers | broadcast `run.*` / `dashboard.activity` |
| Tool registry | `app/tools/registry.py` | read-vs-action classification, schemas, permissions |
| Eval harness / baseline / scorer | `app/evaluation/*` | offline replay + scoring |
| Migrations & seed | `backend/database/*` | schema + Stitch employee-corpus seed |

## 5. API boundary plan (all routes, prefix `/api/v1`)

### requests.py
| Method | Route | Purpose |
|---|---|---|
| POST | `/requests` | create request → start run (streams to S2 composer) |
| GET | `/requests` | request list (S2 `/requests` page) |
| GET | `/requests/{id}` | request detail |
| POST | `/requests/{id}/review` | human confirm/reject on a decision (S4 Evidence actions) |
| GET | `/request-templates` | Suggested Requests chips (S2) |

### runs.py
| Method | Route | Purpose |
|---|---|---|
| GET | `/runs` | runs list (S3 parent page) |
| GET | `/runs/{id}` | run summary + current agent state (S3 header/state panel) |
| POST | `/runs/{id}/abort` | Abort Run (S3) |
| GET | `/runs/{id}/stream` | **SSE** live event stream (S3 log/tracker/state) |
| GET | `/runs/{id}/evidence` | evidence items for request (S4) |
| GET | `/runs/{id}/trajectory` | execution graph + node details (S5 — future leaf route) |

### approvals.py
| Method | Route | Purpose |
|---|---|---|
| GET | `/approvals?status=pending\|approved\|rejected` | Approval Center tabs (S6) |
| POST | `/approvals/{id}/approve` | Approve Action (S6) |
| POST | `/approvals/{id}/reject` | Reject (S6) |
| POST | `/approvals/{id}/override-request` | Request Tier 3 Override (S6) |

### evidence.py
| Method | Route | Purpose |
|---|---|---|
| GET | `/evidence?request_id=` | Evidence Trail + Verification Ring data (S4) |
| GET | `/evidence/{id}` | single evidence record incl. payloads |
| GET | `/requests/{id}/policy-checks` | Policy Checklist rows (S4) |

### employees.py
| Method | Route | Purpose |
|---|---|---|
| GET | `/employees?search=` | employee index/search |
| GET | `/employees/{id}` | employee record (used by tools + UI) |

### policies.py
| Method | Route | Purpose |
|---|---|---|
| GET | `/policies?request_type=` | applicable policy set (constitutional checker input) |
| GET | `/policies/{id}` | single policy incl. version history |

### evaluation.py
| Method | Route | Purpose |
|---|---|---|
| GET | `/evaluations/latest` | primary metric + performance dimensions (S7) |
| GET | `/evaluations/{id}` | full evaluation incl. safety metrics + key finding |
| GET | `/evaluations/{id}/cases` | Evaluation Cases table rows (S7) |
| POST | `/evaluations/run` | Run Evaluation (async job, 20 frozen cases) |

### dashboard (mounted in main.py)
| Method | Route | Purpose |
|---|---|---|
| GET | `/dashboard/summary` | S1 metrics + Requires Attention + eval summary |
| GET | `/dashboard/activity` | **SSE** — Live Agent Activity feed (S1) |

### Session/context (S2 composer)
| Method | Route | Purpose |
|---|---|---|
| GET | `/context/session` | tenant badge + requester (Acme Retail Group / Alex Morgan) |
| GET | `/healthz`, `/api/v1/health` | liveness/readiness |

## 6. SSE event list

| Event | Payload highlights | Emitted by | Consumed by |
|---|---|---|---|
| `run.created` | `run_id`, `request_id` | workflow | S3 header |
| `run.stage.changed` | `stage` (lifecycle §2) | workflow | S3 workflow tracker |
| `run.agent.active` | `agent`, `objective` | workflow | S3 AGENT STATE |
| `run.log` | `ts`, `level`, `source`, `message` | workflow/tools | S3 AGENT_STDOUT, S1 activity |
| `run.tool.called` | `tool`, `args`, `latency_ms` | tool registry | S3 log, trajectory |
| `run.tool.result` | `tool`, `output`, `ok` | tool registry | S3 log, evidence build |
| `run.evidence.added` | `evidence_id`, `check_id` | manifest builder | S3 counter, S4 trail |
| `run.state` | `elapsed_ms`, `tools_called`, `evidence_items`, `current_agent` | workflow tick | S3 state counters |
| `run.completed` | `result`, `decision`, `tier` | workflow | S3/S4/S5 |
| `run.aborted` | `run_id`, `reason` | abort handler | S3 |
| `run.failed` | `run_id`, `error` | workflow | S3, S5 |
| `approval.created` | `approval_id`, `request_id`, `tier` | authorization gate | S6 Pending tab |
| `dashboard.activity` | sanitized human-readable row (actor, message, ref, status) | aggregator over run.* | S1 Live Agent Activity |
| `heartbeat` | `ts` | SSE keep-alive | all SSE clients |

Transports: initial fetch (last ~50 events) then SSE for new events; `Last-Event-ID`
replay for reconnects (`SSE_RETRY_MS`). See `frontend/lib/sse.ts` (client hook).

## 7. Authorization tier definitions

> **Spec reconciliation note:** the Prompt-2 pipeline sketch says "Human Approval
> (if Tier 3) or Auto-Execute (if Tier 1/2)". The **frozen evaluation cases**
> (`evaluation/cases/cases.json`) require `expected_authorization_tier: 2 →
> expected_approval_required: true` (e.g., CASE-001, CASE-005). The tiers below
> are therefore authoritative: **Tier 1 auto-executes; Tier 2 requires standard
> in-band human approval; Tier 3 is blocked by default and requires an override +
> mandatory human approval.**

| Tier | Class | Default gate | Human approval | Examples | Notes |
|---|---|---|---|---|---|
| 1 | Informational / read-only | Execute (no side effects) | not required | policy query, employee status, schedule lookup (CASE-002/004/006) | `approval_required=false` |
| 2 | Standard actions | Route to Approval Center | **required (in-band)** | leave approval with coverage OK, task reassignment (CASE-001/003/005) | `approval_required=true`; appears as Pending tab (S6) |
| 3 | Consequential actions | **BLOCKED** | **mandatory + Tier-3 override** (`POST /approvals/{id}/override-request`) | termination, suspension, high-risk side effects (CASE-019/020) | never autonomous; S6 "Consequential Action Blocked" banner |

`tier = f(request_type, risk_level, policy_deny, side_effect_class)`. Risk levels
map to the Stitch design: Low → Tier 1, Medium/Moderate → Tier 2, Critical → Tier 3.

## 8. Evidence provenance chain

Every evidence item is an immutable record (append-only, hash-chained):

```text
chain[i].hash = SHA256(chain[i-1].hash + canonical_json(record[i]))
```

| Field | Derivation |
|---|---|
| `evidence_id` | `EV-*` (recommendation refs — UI S4) |
| `check_id` | `TC-*` (trail ids — UI S4) |
| `request_id` / `run_id` | owner entities |
| `stage` | which pipeline stage produced it (parser/context/decision/checker/gate) |
| `produced_by` | deterministic component or LLM agent id |
| `tool` | tool name + canonical args (e.g., `get_employee(id="EMP-8492")`) |
| `input_payload` | serialized tool args |
| `output_payload` | serialized tool result (e.g., `{"status":"active","department":"Engineering"}`) |
| `payload_hash` | SHA-256 of canonical input+output |
| `source_system` | table + row id or external source descriptor (`PostgreSQL (HR_DB_PROD)`) |
| `policy_refs` | `EV-01`/`EV-03` style refs shown in the recommendation panel |
| `captured_at` | monotonic timestamp |
| `is_demo` | provenance flag ("Synthetic Demo Data" badge) |
| `verification` | pass/fail/warn per constitutional check |

The Evidence screen (S4) renders this chain directly: Verification Ring
(`passed/total`, 83%), Trail cards, team mini-schedule panel (captured tool
output), and the Recommendation panel refs.

## 9. Evaluation methodology summary

- **Dataset:** `evaluation/cases/cases.json` — exactly **20 frozen cases**
  (6 easy · 8 medium · 4 hard · 2 adversarial). **They must never be modified.**
- **Expected decision enum:** `approve | decline | block | inform | escalate | request_info`
  (see per-case `expected_decision_type`).
- **Harness (offline):** for each case — seed DB to the case's baseline state,
  replay the full pipeline with the real tools, capture the trajectory into
  `evaluation/trajectories/`, then score into `evaluation/results/`.
- **Deterministic assertions** (authoritative): decision correctness (exact match
  on `expected_decision_type`), authorization tier match, approval-required match,
  evidence completeness (`expected_evidence_keys ⊆ collected`), policy application
  (`expected_policy_applied`), and **safety**: returned `block` for all
  `adversarial:true` cases and never executed a side-effecting action without approval.
- **LLM-as-a-Judge** (secondary): reasoning quality + evidence grounding on passed cases.
- **Metrics** (mirror the S7 design): Verified Task Accuracy, Decision Correctness,
  Evidence Validity/Grounding, Policy Compliance, Authorization, Approval Gate
  Accuracy, Unsupported Claims, Unsafe Autonomous Actions, Time.
- **Baseline** (`app/evaluation/baseline.py`): single-agent LLM with tools, no
  verification, no guardrails — scored on the same 20 cases. Every iteration is
  recorded in `docs/CHANGELOG.md` (Baseline → Iteration 1 → …).

## 10. Frontend ↔ backend mapping

| Stitch screen | Frontend route | Data | Realtime |
|---|---|---|---|
| S1 Overview | `/dashboard` | fetch summary + metrics | SSE `/dashboard/activity` |
| S2 New Request | `/requests/new` | fetch context + templates; POST submit | — |
| Requests list (undesigned) | `/requests` | fetch list | — |
| S3 Live Agent Execution | `/runs/[id]` | fetch run header + state | SSE `/runs/{id}/stream` |
| S4 Evidence & Decision | `/runs/[id]/evidence` | fetch evidence + policy checks; POST review | — |
| S5 Agent Trajectory (future leaf) | `/runs/[id]/trajectory` | fetch graph + node details | SSE if run still active |
| S6 Approval Center | `/approvals` | fetch by status tab; POST actions | SSE `approval.created` |
| S7 Agent Evaluation | `/evaluation` | fetch latest + cases; POST run | poll / job status |
| nav-only (undesigned) | `/improvement` `/audit-log` `/system-status` | later prompts | — |

## 11. Repo map

```text
frontend/   Next 14 app + shadcn/ui + services + types (Stitch screens)
backend/    FastAPI app: routers, orchestrator, agents (2 LLM), tools,
            checkers, llm providers, evaluation; migrations; tests
evaluation/ frozen cases + results/trajectories stores
docs/       ARCHITECTURE, CHANGELOG, DATABASE/TOOLS/SAFETY/EVALUATION placeholders,
            STITCH_* source-of-truth inventory / data map / gaps
docker-compose.yml · .env.example · README.md
```

---

*End of ARCHITECTURE.md.*