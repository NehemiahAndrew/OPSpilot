# OpsPilot — Stitch Data Map

> **Purpose:** for every screen, list every displayed data field, its likely backend source (table + field), whether it is static / fetched / real-time (SSE), and the loading / empty / error state required.
> **Important:** the Stitch design contains **no loading skeletons, no empty states, and no error states** (only in-log error *text*). Rows below therefore mark these as *required-but-not-designed*. Backend table names are proposals — no schema exists yet.

## 0. Cross-screen source entities referenced by the design

| Entity | Likely table | Notes |
|---|---|---|
| Requests | `requests` | IDs `REQ-1047..1049`; type (`LEAVE_REQUEST`); title; employee link; description; status; risk; verification counts |
| Invoices / tickets | `invoices` / `tickets` | `INV-882`, `TKT-8892` in timeline/metadata |
| Employees | `employees` | Sarah Mitchell / Alex Morgan / John Carter; `EMP-8492` vs `emp_102` (inconsistent — see gaps) |
| Agent runs | `agent_runs` | `RUN-82A91`; duration; agent count; tool-call count; status |
| Agent events | `agent_events` | timeline + stdout log rows (SSE source) |
| Evidence items | `evidence_items` | `TC-*` ids, `EV-*` refs, tool source, payloads |
| Policy checks | `policy_checks` | per-request checklist incl. `TBD` |
| Approvals | `approvals` | pending/approved/rejected; tier; risk; recommendation |
| Evaluations | `evaluations` + `evaluation_cases` | `RUN-EVAL-002`; metrics; `EVL-4091…` |

---

## 1. Screen — Operations Overview (`/`)

| Data field (as designed) | Likely source | Static/Fetched/SSE | Required loading/empty/error state |
|---|---|---|---|
| Greeting "Good afternoon, Alex" | `session.user` + time-of-day | fetched (auth) | — |
| Subtitle copy | static | static | — |
| **Live Data Mode** pill | `system_status.mode` | fetched / SSE heartbeat | skeleton; error → "Offline" tone |
| Requests Processed `24`, `+12%` | `metrics.counters.requests_processed` + `metrics.deltas.pct` | fetched (poll 15–30s) | metric skeleton; hide on error |
| Verified Resolutions `18`, `75% yield` | `metrics.counters.verified_resolutions`; derived `verified/total` | fetched | skeleton; error → `—` |
| Awaiting Approval `4` | `count(approvals where status='pending')` | fetched | skeleton; error |
| Escalated `2` | `count(requests where status='escalated')` | fetched | skeleton; error |
| Avg Resolution Time `2m 14s`, `−15s` | `metrics.avg_resolution_seconds` + delta | fetched | skeleton; error |
| **Requires Attention** `4 PENDING` | `approvals` pending | fetched (poll) | skeleton ×2; **empty state required** ("No pending approvals") — not designed |
| Approval preview cards (title, REQ/INV id, Risk, Verification `5/6`) | `approvals` ⟕ `requests` | fetched | error card + retry |
| **Live Agent Activity** rows (ts, agent, message, ref, status) | `agent_events` | **SSE** (new) + initial fetch (last ~50) | "connecting…"; **empty** ("No activity yet"); disconnect banner — none designed |
| Filter `All Agents` | client OR server filter | fetched param | — |
| Evaluation Summary 89/71/−45/−62 | `evaluations.latest.metrics` | fetched (or static demo) | skeleton; currently "Synthetic Demo Data" |

---

## 2. Screen — New Request (`/requests/new`)

| Data field (as designed) | Likely source | Static/Fetched/SSE | Required loading/empty/error state |
|---|---|---|---|
| Context Attached: `Acme Retail Group` | `session.tenant` | fetched (session) | skeleton badge; error → hide |
| `Requester: Alex Morgan` | `session.user` | fetched (session) | skeleton badge |
| Prompt textarea + placeholder | static | static | — |
| "Consequential actions…" note | static | static | — |
| Suggested Request chips (3) | `request_templates` | fetched (fallback static) | hide section on error |
| `Run OpsPilot` button | POST `/requests` → creates run | action (async) | button `busy`; **error toast**; disabled while submitting — not designed |

## 3. Screen — Live Agent Execution (`/runs/:runId`)

| Data field (as designed) | Likely source | Static/Fetched/SSE | Required loading/empty/error state |
|---|---|---|---|
| `REQ-1048` chip | `requests.id` | fetched | skeleton |
| "Time Off Request Assessment" | `requests.title` / type | fetched | skeleton |
| **Agent Active** pill | `agent_runs.status` | **SSE** | pill skeleton; failure tone |
| Employee `Sarah Mitchell` | `requests.employee_id` → `employees.name` | fetched | skeleton |
| Request quote | `requests.description` | fetched | skeleton |
| Workflow tracker (5 steps) | `agent_runs.current_stage` (derived from latest `agent_events`) | **SSE** | step skeletons; failure-step style — not designed |
| **AGENT_STDOUT** log lines | `agent_events` streamed | **SSE** (+ history fetch) | "connecting to event stream…"; empty terminal; reconnect button — not designed |
| Current Agent · Status Running · Elapsed `4.2s` | `agent_runs.current_agent`, `status`, timestamps | **SSE** | stat skeletons |
| Tools Called `5` | `agent_runs.tools_called` = `count(agent_events type='tool')` | **SSE** | — |
| Evidence Items `5` | `count(evidence_items where run_id=…)` | **SSE** | — |
| CURRENT OBJECTIVE | `agent_runs.current_objective` | **SSE** | skeleton |
| View Evidence / View Full Trajectory / **Abort Run** | routes + POST `/runs/:id/abort` | action | Abort busy/confirm state — not designed |

---

## 4. Screen — Evidence & Decision (`/requests/:id/evidence`)

| Data field (as designed) | Likely source | Static/Fetched/SSE | Required loading/empty/error state |
|---|---|---|---|
| `Request: REQ-1048` | `requests.id` | fetched | skeleton |
| **Needs Confirmation** badge | `requests.decision_state` | fetched | skeleton |
| H1 "Decision Evidence" | static | static | — |
| "Approve with Manager Confirmation" | `requests.verdict` / `requests.verification.summary` | fetched | skeleton |
| `5/6` Checks Passed · ring `83%` | `requests.verification.passed/total` (derived) | fetched | skeleton ring |
| Evidence Trail cards (title, `TC-01928..31`, subtitle, source tool, JSON payloads) | `evidence_items` | fetched (persisted at decision time) | card skeletons; **empty state** ("No evidence recorded") — not designed; failed-check styling |
| Team schedule mini-panel (`ENG-04`, date, member statuses, coverage min "2 engineers") | captured tool output `evidence_items.output_payload` | fetched | skeleton |
| Agent Recommendation prose + refs `EV-01`/`EV-03` | `requests.agent_recommendation` + `evidence_items.refs` | fetched | skeleton |
| Policy Checklist rows (✓/⚠/`TBD`) | `policy_checks` (name + result) | fetched | skeleton; partial/error state — not designed |
| Reject / Confirm Approval | POST `/approvals` / `/requests/:id/review` | action | busy + **error toast**; post-action navigation — not designed |

## 5. Screen — Agent Trajectory (`/runs/:runId/trajectory`)

| Data field (as designed) | Likely source | Static/Fetched/SSE | Required loading/empty/error state |
|---|---|---|---|
| Run ID `RUN-82A91` · Duration `6.8s` · Agents `2` · Tool Calls `5` · `Completed` | `agent_runs` (+ counts) | fetched (SSE if still wrapping up) | header skeleton |
| Graph nodes (Request Received / Intent Parser / Context Agent / Decision Agent / Authorization Check) | `run_nodes` (from `agent_events`) | fetched | **graph empty state** ("Run has no trace") — not designed |
| Node timings (0.0ms → 4.5s), Active flags | `run_nodes.latency_ms`, `state` | fetched | skeleton nodes |
| Tool-call cards (`get_user_profile()` 120ms · `get_leave_balance()` 215ms · `check_policy_db()` 85ms · `fetch_calendar()` 340ms) | `run_nodes` (type='tool_call') | fetched | skeleton |
| Node Details (name, Success, latency, Context, `PostgreSQL (HR_DB_PROD)`, Input/Output payloads) | `run_nodes` + tool registry | fetched | skeleton; **no-selection state** ("Select a node") — not designed |
| Zoom / fit controls | client UI state | static | — |

---

## 6. Screen — Approval Center (`/approvals`)

| Data field (as designed) | Likely source | Static/Fetched/SSE | Required loading/empty/error state |
|---|---|---|---|
| Tabs Pending (active) / Approved / Rejected | `approvals.status` filter | fetched (per tab) | tab skeleton; **empty feedback per tab** ("No approvals") — not designed |
| Card 1: Sarah Mitchell · Leave Request Review · Moderate Risk · Recommendation `Approve` · Verification `5/6` (83% bar) · Flag Reason | `approvals` ⟕ `requests` ⟕ `evidence_items` | fetched (poll while `Pending`) | card skeletons; error state |
| Card 2: **Consequential Action Blocked** · Tier 3 · John Carter · `execute_termination_protocol(...)` | `approvals` + `approvals.authorization_tier` + `incidents` (new entity) | fetched | skeleton; banner needs tier/policy data |
| `Approve Action` | POST `/approvals/:id/approve` | action | busy + error toast — not designed |
| `Request Tier 3 Override` | POST `/approvals/:id/override-request` | action | busy + confirmation state — not designed |

---

## 7. Screen — Agent Evaluation (`/evaluations`)

| Data field (as designed) | Likely source | Static/Fetched/SSE | Required loading/empty/error state |
|---|---|---|---|
| **Run Evaluation** (20 cases) | POST `/evaluations/run` (async job) | action | **progress view + job history** — not designed |
| Verified Task Accuracy `89%` (+18pp) vs `71%` | `evaluations.metrics.accuracy` + baseline | fetched | skeleton; badge "Demo Data" |
| Meta: `RUN-EVAL-002` · `Workforce Ops v1` · Cases `20` · `Completed (2m 18s)` | `evaluations` (id, dataset, case_count, status, duration) | fetched | skeleton |
| Performance Dimensions (5 rows; deltas +4…+19pp) | `evaluations.metrics.breakdown[]` | fetched | skeleton |
| Safety: Unsupported Claims `1/20` · Evidence Grounding `95%` · Unsafe Actions `0/20` · Approvals `100%` | `evaluations.safety_metrics` | fetched | skeleton |
| Key Finding | `evaluations.findings` | fetched | skeleton |
| Methodology list | static | static | — |
| Evaluation Cases table (`EVL-4091..4094`, difficulty, Baseline, OpsPilot, Delta) | `evaluation_cases` | fetched | table skeleton; **empty state** ("No cases run"); row error |
| Filter chips All/Easy/Medium/Hard/Adversarial | filter on `evaluation_cases.difficulty` | static filter | — |

---

## 8. Real-time (SSE) summary

- **SSE required:** Live Agent Activity (S1), Live Agent Execution log + workflow tracker + agent state counters (S3).
- **Fetch/poll:** metrics, approvals, evidence, trajectory, evaluations.
- **Static:** copy, methodology, labels, suggestion fallback, avatar URLs.
- The design does **not** specify SSE transport, reconnection, backlog replay, or last-event-id.
- The design provides **zero** loading, empty, or error UI patterns anywhere — all are required additions during implementation.

*End of STITCH_DATA_MAP.md.*