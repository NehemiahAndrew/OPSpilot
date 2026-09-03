# OpsPilot — Stitch Design Gaps

> Categories from the brief: (A) needs a backend feature not yet planned, (B) unclear how it should behave, (C) decorative but needs real data, (D) conflicts with the agent architecture. Extra categories for reference in later prompts: E, F, G.

---

## A. Requires a backend feature not yet planned

1. **SSE event stream.** Live Agent Activity (Overview) and the whole Live Agent Execution screen (stdout log, workflow tracker, running counters) are streaming UIs. There is no planned real-time channel.
2. **Run orchestration with abort.** The Live Run screen exposes `Abort Run` — requires a supervisor that can cancel mid-run (mid-tool-call), persist a partial state, and emit a terminal event.
3. **Evidence manifest store.** Evidence screen treats evidence as first-class records (`TC-01928..31`, refs `EV-01`/`EV-03`, source tool, input/output payloads). No `evidence_items` persistence is planned.
4. **Policy checklist engine.** Per-request checklist rows with pass / fail / `TBD` states require a policy rules engine keyed by request type.
5. **Tiered authorization ("Authorization Tier 3").** Approval Center Card 2 blocks a "consequential action" and offers a Tier-3 override. Requires an authorization-tier model + escalation workflow (override requester, approver routing, audit).
6. **Risk classification.** `Risk Low/Medium/Moderate/Critical` appears on S1/S4/S6. Requires a deterministic or LLM risk classifier emitted per request.
7. **Evaluation harness.** "Run Evaluation", golden dataset, `LLM-as-a-Judge (GPT-4)`, deterministic assertions, case rows, deltas. Requires an eval service, dataset versioning, async job, and result store.
8. **Predictive/safety metrics.** "Unsupported Claims 1/20", "Evidence Grounding 95%", "Unsafe Autonomous Actions 0/20" require a grounding/claims checker (hallucination + safety scanning) — a classifier per decision.
9. **Notification + settings destinations.** TopAppBar has notifications and settings on every screen; no destinations exist.
10. **Operations search.** Every top bar has a search field with different placeholders ("Search operations...", "Search logs, requests...", "Search evaluations...", "Search..."). No search backend.
11. **Incident report entity.** "Open Incident Report" (S6) implies an `incidents` entity with review UI — not planned.
12. **Data sources referenced by agent tools.** Tool calls imply: HR DB (`get_employee`, `get_leave_balance`, `HR_DB_PROD`), calendars (`get_team_calendar`, `check_team_schedule`), policy DB (`check_policy_db`), webhooks (Action Agent), email ingestion (Ingestion Agent), a historical/vector index (Decision Agent), and a ticketing/invoice queue (TKT-8892 → Finance Queue, INV-882). None planned.
13. **"Synthetic Demo Data" / "Demo Data" badges** imply a data provenance flag on every payload — needs an `is_demo`/`provenance` mechanism end-to-end.
14. **Requests list.** Sidebar "Requests" is a top-level destination; only the composer (New Request) and per-request evidence exist. A requests list/table screen and its query layer are missing.
15. **Audit Log, Improvement, System Status.** Referenced nav destinations with no designs and no backend.

---

## B. Unclear how it should behave

1. **`Review Details` (Overview preview card)** → navigates to? Evidence screen assumed, but no route/param defined in design.
2. **`View all approvals`** → `/approvals` with which tab preselected?
3. **`All Agents` filter (Live Activity)** → client-side filter or server/SSE filter?
4. **`Abort Run`** → kill workflow immediately vs graceful stop at next step boundary; what happens to partially-built evidence/manifest; is there a confirmation modal (design shows none)?
5. **`View Evidence` vs `View Full Trajectory` from a running run** → are evidence/trajectory views available for **in-progress** runs, or only after completion? Live vs replay.
6. **`Live Data Mode` pill** → decorative label or a real demo↔live toggle? If toggle, what changes (SSE on/off, demo fixtures)?
7. **`Hackathon Demo` button** → present on every screen, but styling varies (indigo #6366F1 vs theme primary) and behavior is undefined: does it seed demo data, replay a canned run, or reset state?
8. **Suggestion chips (New Request)** → do they pre-fill the textarea, submit directly, or open a template editor?
9. **`Confirm Approval` / `Reject` (Evidence) vs `Approve Action` / `Reject` (Approvals)** → post-action behavior (status update? execute downstream action? notify requester? navigate where?) is unspecified.
10. **`Request Tier 3 Override`** → what happens: modal, escalation ticket, who gets it, SLA, what the blocked action card becomes meanwhile.
11. **Time-frames are inconsistent across screens.** `Request Received` node timing is `0.0ms`; run "Duration 6.8s" vs log timestamps `14:31:59 → 14:32:05`; the Evidence team schedule says `Nov 10, 2023`. The design mixes wall-clock, relative-ms, and absolute-date frames with no statement of which is live/epoch.
12. **Node Details selection semantics.** The trajectory detail panel explicitly "mocks the clicked node". Clicking any node should swap the panel; behavior for agent nodes vs tool-call nodes, and initial selection state, is undefined.
13. **`Run Evaluation` flow.** Synchronous run with progress, or async job that navigates to a "running" state? The "20 cases" sub-label is a hard-coded count; dataset selection is not offered.
14. **Zoom/fit controls.** What do they actually do with a static vertically-rendered graph (pan/zoom on canvas)? No implementation hint in the design.
15. **Loading / empty / error UI.** The design defines none for any screen; every data-driven region needs invented states that must match Stitch styling.
16. **Topbar vs sidebar navigation.** Every screen shows both "Overview"/"Requests" topbar links and the full sidebar; which is canonical, and does the topbar "Requests" link open the list or the composer?

---

## C. Appears decorative but needs real data

1. **Top Metrics numbers** (`24`, `18`, `4`, `2`, `2m 14s`) and deltas (`+12%`, `−15s`, `75% yield`) are hard-coded while the page claims **Live Data Mode** — the pill is misleading until metrics come from real queries (or the mode is honest).
2. **Live Agent Activity entries** (S1) are canned strings referencing `REQ-1048`, `TKT-8892`, `REQ-1047`, `REQ-1046` — need real SSE events (or a replay fixture).
3. **Evaluation Summary (S1) + all Evaluation metrics (S7)** — every number sits under a "Synthetic Demo Data"/"Demo Data" badge; must be produced by the eval harness.
4. **AGENT_STDOUT log lines (S3)** — hand-written sample of a stream that agents must actually emit, including tool JSON that must match real tool-output schemas.
5. **Workflow tracker + Agent State counters** — static `checked`/`active` states and `4.2s`/`5`/`5` values; need real stage transitions and counters.
6. **Avatars** — AI-placeholder `aida-public/googleusercontent` URLs; need real user images or initial/icon fallback (S7 already falls back to a `person` icon).
7. **Greeting "Good afternoon, Alex"** — time-window computed, but the name is hard-coded and differs across screens ("Alex" vs "Alex Morgan" requester); needs the session user.
8. **Policy Checklist rows** — rendered like results but need the real policy engine; "Manager Review Required: TBD" is a placeholder state machine.
9. **Traffic-light dots + glass gradients + grid pattern + shader overlays** — pure decoration (fine as-is; no data needed).

## D. Conflicts with the agent architecture

1. **A fixed 5-stage supervised pipeline is implied** (Request Parsed → Context Gathered → Evidence Manifest → Decision → Constitutional Check), plus an "Authorization Check" node on the trajectory. There is no defined orchestration architecture yet; the UI forces one: every stage must be a distinct, observable, persistable unit.
2. **The evidence manifest is a first-class artifact.** The Evidence screen demands structured records (check id `TC-*`, source tool call, input/output payload, refs `EV-*`). Agents must therefore persist tool I/O as evidence records, not just carry context in conversation.
3. **"Constitutional Check" (tracker step 5) vs "Authorization Check" (trajectory node)** — two naming conventions for arguably one guardrail; placement/order must be reconciled in the pipeline definition.
4. **Agent roster exceeds the pipeline.** The S1 timeline names Ingestion, Extraction, Routing, Action, Verification, and Decision agents; the run pipeline only names Parser/Context/Decision. Architecture must adopt a wider agent registry or the timeline copy is misleading.
5. **Side-effectful tools vs the approval gate.** "Action Agent triggered webhook for REQ-1047… Payload delivered" coexists with "Consequential actions always require human approval". Architecture needs a tool-execution layer with a guardrail gate (auto-execute vs intercept → approval queue).
6. **Risk, tier, recommendation, verification-score, flag-reason are decision outputs** that the Approvals + Evidence screens render. Decision outputs must be structured and stable enough to drive these UI models.
7. **Run lifecycle model is implied but unspecified:** `pending → running(stage/agent) → awaiting_approval → completed | aborted | escalated`. Each screen consumes a different projection of it (live counters, evidence snapshot, finalized graph). This lifecycle must be explicit before any screen works.
8. **Eval harness depends on replayability.** Metrics like "unsupported claims", "evidence grounding", and "unsafe autonomous actions" require fully auditable, replayable runs (every tool call stored) — a hard constraint on the agent runtime.

## E. Data consistency issues found in the design

1. **Employee ID:** `EMP-8492` (evidence) vs `emp_102` (trajectory payload) vs `user="Sarah Mitchell"` (log) — three references to one person.
2. **Leave balance:** log shows `{"balance": 6, "unit": "days"}`; Trajectory payload `{"balance_days": 6.0, "accrued_to_date": 14.5, "pending_requests": 0}`; Evidence "Available: 6 days" — field naming must be normalized.
3. **Requested days:** "Requested: 2 days" (evidence) vs description "Friday off" (1 day) vs `date=NEXT_FRIDAY` (parser) — narrative mismatch.
4. **Entity families:** `REQ-*`, `INV-882`, `TKT-8892` imply requests/invoices/tickets tables that don't exist; Finance Queue is referenced but unmodeled.
5. **People corpus:** Sarah Mitchell, Alex Morgan, John Carter, Mark T., David L., John Doe — must become one seeded dataset.
6. **Calendar/date seed:** `2023-11-10` (evidence) vs "Next Friday" (tool call) vs `"current_year": 2024` (payload) — inconsistent.
7. **Run ID naming:** `RUN-82A91` (trajectory) vs `RUN-EVAL-002` (evaluation) vs `Runs` implied by `RUN-EVAL` — ID generator collision risk.
8. **Cross-screen visual drift (matters for implementation):** sidebar logo differs per screen (O badge / `memory` / `terminal` / `rocket_launch` / wordmark-only); "Hackathon Demo" button is indie `#6366F1` on some screens and theme `bg-primary` on others; search input radius differs (`rounded-lg` vs `rounded-full`); page background differs (`bg-[#0A0A0B]` vs `bg-background`).

## F. Responsive / mobile

1. Only the Overview has a mobile hamburger; other screens drop the sidebar via `hidden md:flex` with no drawer replacement.
2. S2/S3 use `h-screen overflow-hidden` flex layouts that will break below `md` (no mobile states designed).
3. Touch targets, tablet breakpoints, and mobile search/CTAs are undesigned.

---

## Verification notes
- **Screens found in Stitch output:** 7 (Overview, New Request, Live Agent Execution, Evidence & Decision, Agent Trajectory, Approval Center, Agent Evaluation).
- **Components identified:** 41 reusable components (details in `STITCH_INVENTORY.md`).
- This document intentionally contains **no proposed solutions** — only gaps, per the brief.

*End of STITCH_GAPS.md.*