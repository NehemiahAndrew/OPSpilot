# OpsPilot — Stitch UI Inventory

> **Source:** Stitch-generated HTML/CSS/JS pasted by the design lead.
> **Dedup note:** the first five screens were pasted more than once (byte-identical copies); after deduplication exactly **7 distinct screens** were identified.
> **Scope:** inventory only. No redesigns, no improvements, no application code.

---

## 1. Screens

### Screen 1 — Operations Overview
- **Design title:** `OpsPilot - Operations Overview` — **Proposed route:** `/`
- **Sidebar active item:** Overview
- **Key UI sections:**
  - Page header: dynamic greeting ("Good afternoon, Alex"), subtitle ("Here's what's happening across your workforce operations."), **Live Data Mode** status pill (emerald dot)
  - **Top Metrics Cards** — 5-card grid (`grid-cols-2 md:grid-cols-5`): Requests Processed `24` (+12%), Verified Resolutions `18` ("75% yield"), Awaiting Approval `4` (primary-tinted overlay), Escalated `2` (error-tinted overlay), Avg Resolution Time `2m 14s` (−15s)
  - **Requires Attention** panel (1 col): header + `4 PENDING` count chip, 2 approval preview cards, footer "View all approvals" link
  - **Live Agent Activity** timeline (2-col span): black terminal surface, monospace rows, "Filter by: **All Agents**" chip, linked IDs (`REQ-1048`, `TKT-8892`, `REQ-1047`, `REQ-1046`)
  - **Evaluation Summary: OpsPilot vs Baseline**: Verified Task Accuracy 89% vs 71% bar chart; KPI tiles Time to Resolution −45%, Human Touchpoints −62%; **"Synthetic Demo Data"** badge
- **Interactive elements:** sidebar nav; top-bar search ("Search operations..."), notifications, settings, mobile menu; `Review Details` buttons; `View all approvals` link; `All Agents` chip; linked request IDs; Overview/Requests sub-nav
- **Status states visible:** Live Data Mode (emerald pulse); `4 PENDING`; Risk Low (secondary) / Medium (tertiary); Verification `5/6`, `4/5`; timeline `SUCCESS` (emerald); error entry (`error` icon, "failed to parse PDF attachment… Escalating to human queue"); older entries `opacity-60`/`opacity-40`; Synthetic Demo Data badge

### Screen 2 — New Request (composer)
- **Design title:** `OpsPilot - New Request` — **Proposed route:** `/requests/new`
- **Sidebar active item:** Requests
- **Key UI sections:**
  - Centered hero header ("Ask OpsPilot to handle a workforce request" + explanation)
  - **Glass input card** (`glass-panel`, blur, grid-pattern page bg): **Context Attached** badges (tenant `Acme Retail Group`, `Requester: Alex Morgan`), large prompt `textarea` (placeholder "Sarah needs Friday off. Check whether she can take the day and handle the request."), bottom action bar with info note ("Consequential actions always require human approval.") and **Run OpsPilot** button (`send_spark` + glow shadow)
  - **Suggested Requests** pills: Check leave eligibility · Resolve a schedule conflict · Explain a company policy
  - Custom thin scrollbar CSS for textarea
- **Interactive elements:** textarea, `Run OpsPilot` submit, 3 suggestion chips, context badges (static), sidebar, notifications/settings/avatar
- **Status states visible:** none (pre-submit static screen); focus glow on textarea

### Screen 3 — Live Agent Execution
- **Design title:** `OpsPilot - Live Agent Execution` — **Proposed route:** `/runs/:runId`
- **Sidebar active item:** Agent Runs
- **Key UI sections:**
  - **Context header:** `REQ-1048` chip, "Time Off Request Assessment", **Agent Active** pill (`pulse-dot`), employee `Sarah Mitchell`, quoted request ("I'd like to take Friday off because I have a family event.")
  - **Workflow Tracker** (5 steps): Request Parsed ✓ · Context Gathered ✓ · Evidence Manifest ✓ · **Decision** (active, pulsing `psychology`) · Constitutional Check (pending, dimmed)
  - **AGENT_STDOUT streaming log** (2 cols): terminal chrome + traffic-light dots; color-coded `[SYSTEM]` `[SUPERVISOR]` `[PARSER]` `[CONTEXT]` `[TOOL]` (JSON results) `[DECISION]` (animated `…`)
  - **AGENT STATE** panel: Current Agent (Decision Agent), Status Running, Elapsed `4.2s`, Tools Called `5`, Evidence Items `5`, CURRENT OBJECTIVE quote block
  - Footer: `View Evidence`, `View Full Trajectory`, `Abort Run`
- **Interactive elements:** scrollable streaming log, footer action buttons, sidebar, search ("Search logs, requests...")
- **Status states visible:** Agent Active (pulse); steps completed (emerald `check`)/active (primary)/pending (dim); Running; tool `success`; `…` typing animation

---

## Screen summary so far (provisional count)

| # | Screen | Proposed route | Title tag |
|---|--------|---------------|-----------|
| 1 | Operations Overview | `/` | OpsPilot - Operations Overview |
| 2 | New Request | `/requests/new` | OpsPilot - New Request |
| 3 | Live Agent Execution | `/runs/:runId` | OpsPilot - Live Agent Execution |

### Screen 4 — Evidence & Decision
- **Design title:** `OpsPilot - Evidence & Decision` — **Proposed route:** `/requests/:id/evidence`
- **Sidebar active item:** Evidence
- **Key UI sections:**
  - Page header: `Request: REQ-1048`, **Needs Confirmation** badge (tertiary), H1 "Decision Evidence", actions `Reject` (outline) + `Confirm Approval` (primary)
  - **Verification Status**: `shield_person` avatar, "Approve with Manager Confirmation", `5/6` "Checks Passed", **SVG circular progress ring** at 83%
  - **Evidence Trail** (3 cards): *Employee Record Verified* (TC-01928, `get_employee(id="EMP-8492")`, JSON payload) · *Leave Balance Sufficient* (TC-01929, "Requested: 2 days • Available: 6 days") · *Team Coverage Conflict Detected* (TC-01931, warning style, expanded `check_team_schedule(team_id="ENG-04", date="2023-11-10")` + team mini-schedule panel)
  - **Agent Recommendation** panel: pulsing dot, prose, refs `EV-01` / `EV-03`
  - **Policy Checklist** (6): Active Employee Status ✓ · Sufficient Balance ✓ · Notice Period Met (>14d) ✓ · No Overlapping Requests ✓ · Department Coverage Minimum ⚠ (`priority_high`) · Manager Review Required `TBD`
- **Interactive elements:** Reject / Confirm Approval; expand/collapse evidence cards (`expand_more`/`expand_less`)
- **Status states visible:** Needs Confirmation; Checks Passed 5/6 · 83%; passed (`check_circle`/`check` primary); warning (tertiary); `TBD`; expanded vs collapsed

### Screen 5 — Agent Trajectory
- **Design title:** `OpsPilot - Agent Trajectory` — **Proposed route:** `/runs/:runId/trajectory`
- **Sidebar active item:** Agent Runs
- **Key UI sections:**
  - Page header: H2 "Agent Trajectory"; stats strip (Run ID `RUN-82A91`, Duration `6.8s`, Agents `2`, Tool Calls `5`, **Completed** `check_circle`); subtitle "Inspect every step, tool call, decision, verification, and approval."
  - **Execution Graph** (8 cols): vertical graph — Request Received (0.0ms) · Intent Parser (45.2ms) · Context Agent (Active 1.2s) · tool pairs (`get_user_profile()` 120ms, `get_leave_balance()` 215ms **selected**, `check_policy_db()` 85ms, `fetch_calendar()` 340ms) · Decision Agent (Active 4.5s) · Authorization Check (Pass)
  - **Node Details panel** (4 cols, mocking selected node): tool name, `Success`, 215ms, Context, `PostgreSQL (HR_DB_PROD)`, Input/Output JSON payloads
  - Graph header controls: `zoom_in`, `zoom_out`, `fit_screen`
- **Interactive elements:** node/tool selection (border-2 glow), Node Details, zoom controls
- **Status states visible:** Completed run; active nodes (Context/Decision); tool `Success • <ms>`; Authorization `Pass`; selected emphasis

### Screen 6 — Approval Center
- **Design title:** `Approval Center - OpsPilot` — **Proposed route:** `/approvals`
- **Sidebar active item:** Approvals
- **Key UI sections:**
  - Page header: H2 "Approval Center", subtitle "Review consequential or policy-sensitive agent actions before execution."
  - **Tabs:** `Pending` (active, primary underline) · `Approved` · `Rejected`
  - **Card 1 (Moderate Risk):** `person_cancel` avatar; "Sarah Mitchell / Leave Request Review"; **Moderate Risk** badge; block with **Agent Recommendation** `Approve` (`thumb_up`), Verification Score 83% bar `5/6`, **Flag Reason**; actions `Review Evidence` / `Reject` / `Approve Action` (indigo `#6366F1`)
  - **Card 2 (Critical Risk):** **Consequential Action Blocked** banner (`gavel`, "Authorization Tier: 3 required…"); `person_remove` avatar; "John Carter / Disciplinary Action Execution"; **Critical Risk** badge; proposed action `execute_termination_protocol(user_id="jcarter", immediately=True)`; actions `Open Incident Report` / `Request Tier 3 Override`
- **Interactive elements:** tabs; Review Evidence / Reject / Approve Action / Open Incident Report / Request Tier 3 Override
- **Status states visible:** Pending; Moderate (tertiary) / Critical (error) risk; Consequential block (Tier 3); Appr. recommendation Approve; 5/6

### Screen 7 — Agent Evaluation
- **Design title:** `OpsPilot - Agent Evaluation` — **Proposed route:** `/evaluations`
- **Sidebar active item:** Evaluations
- **Key UI sections:**
  - Page header: H1 "Agent Evaluation", subtitle, **Run Evaluation** button ("20 cases", `play_arrow`)
  - **Primary metric card:** Verified Task Accuracy **89%** (+18pp), "OpsPilot 89% vs Baseline 71%", **Demo Data** badge, meta grid (RUN-EVAL-002 · Workforce Ops v1 · Cases 20 · Completed 2m 18s)
  - **Performance Dimensions** (dual bars OpsPilot/Baseline): Decision Correctness 92/76 (+16pp) · Evidence Validity 95/76 (+19pp) · Policy Compliance 96/88 (+8pp) · Authorization 74/70 (+4pp) · Approval Gate Accuracy 100/88 (+12pp)
  - **Safety & Reliability** (border-left metrics): Unsupported Claims `1/20`, Evidence Grounding `95%`, Unsafe Autonomous Actions `0/20`, Approval Gate Accuracy `100%`
  - **Key Finding** (`lightbulb`); **Methodology** (Golden Dataset Baseline, LLM-as-a-Judge GPT-4, Deterministic Assertions)
  - **Evaluation Cases** table (4 rows EVL-4091…4094; difficulty; Passed/Failed; Improved/Unchanged/Regression) + filter chips All/Easy/Medium/Hard/Adversarial
- **Interactive elements:** Run Evaluation; filter chips; table rows (hover, chevron)
- **Status states visible:** Completed; Demo Data; Passed (emerald)/Failed (error); Improved/Unchanged/Regression

### Screens referenced in the nav but **not provided**
- **Improvement** (`trending_up`) — no HTML · **Audit Log** (`history`) — no HTML · **System Status** (`cloud_done`) — no HTML

**Final screen count: 7 designed screens + 3 nav-only destinations.**

## 2. Reusable components

Legend — **Appears:** S1 Overview · S2 New Request · S3 Live Run · S4 Evidence · S5 Trajectory · S6 Approvals · S7 Evaluations.

| # | Component | Appears | Props it will need |
|---|-----------|---------|--------------------|
| 1 | **SideNavBar** | S1–S7 | `activeKey`, `onNavigate`, `logoVariant` ('O' badge / memory / terminal / rocket_launch / bare wordmark), `demoAction`, `systemStatusLink` |
| 2 | **TopAppBar** | S1–S7 | `activeTab`, `searchPlaceholder`, `onSearch`, `onNotifications`, `onSettings`, `user`, `mobileMenu` |
| 3 | **GlobalSearchInput** | S1–S7 | `placeholder`, `value`, `onChange`, `variant` (rounded-lg vs rounded-full) |
| 4 | **UserAvatar** | S1–S6 | `src`, `alt`, `fallbackIcon`/`fallbackInitial`, `size` |
| 5 | **PageHeader** | S1, S4, S5, S6, S7 | `title`, `subtitle`, `meta` (badges/stats strip), `actions` slot |
| 6 | **MetricCard** | S1 | `label`, `value`, `deltaText`, `deltaTone` ('up'/'neutral'/'error'), `tint` ('none'/'primary'/'error'), `subText` |
| 7 | **DeltaBadge** | S1, S7 | `value` ('+12%', '+18pp', '−15s', 'Improved'…), `tone` ('up'/'down'/'neutral') |
| 8 | **StatusPill** | S1, S3, S4, S7 | `label` ('Live Data Mode'/'4 PENDING'/'Agent Active'/'Needs Confirmation'/'Demo Data'), `tone`, `dot`, `pulsing` |
| 9 | **RiskBadge** | S1, S6 | `level` ('Low'/'Medium'/'Moderate'/'Critical'), `icon` |
| 10 | **ReferenceChip** (mono entity badge) | S1, S3, S4, S5, S7 | `refId` ('REQ-1048'/'TC-01928'/'RUN-82A91'/'EVL-4091'), `tone` |
| 11 | **Panel** (card container) | S1–S7 | `bg`, `borderTone`, `radius`, `padding`, `header` slot, `hover` |
| 12 | **PanelHeader** | S1, S3, S4, S5, S7 | `icon`, `title`, `action` slot (badge/chip/filter/zoom), `accent` |
| 13 | **ApprovalPreviewCard** | S1 | `title`, `refId`, `riskLevel`, `verification`, `onReview` |
| 14 | **ActivityLogRow** | S1 | `timestamp`, `actor`, `message` (rich nodes), `status`, `icon`, `dim` |
| 15 | **FilterChip** | S1, S7 | `label`, `active`, `onClick` |
| 16 | **SuggestionChip** | S2 | `icon`, `label`, `onClick` |
| 17 | **ContextBadge** | S2 | `icon`, `label`, `value` |
| 18 | **PromptTextarea** | S2 | `placeholder`, `value`, `onChange`, `rows` |
| 19 | **RunButton** (primary CTA) | S2, S7 | `label`, `icon`, `subLabel` ('20 cases'), `loading`, `onClick` |
| 20 | **WorkflowTracker** + **WorkflowStep** | S3 | `steps[]` ({id, label, icon, state: done\|active\|pending}) |

| 21 | **StreamLogPanel** + **LogLine** | S3 (concept in S1) | `lines[]` ({ts, level, source, text, tone}), `autoScroll`, `trafficLights` |
| 22 | **AgentStatePanel** + **StatTile** | S3 | `currentAgent`, `status`, `elapsed`, `toolsCalled`, `evidenceItems`, `objective` |
| 23 | **TrafficLights** (decorative) | S3 | — (no props; decorative dots) |
| 24 | **EvidenceCard** | S4 | `title`, `checkId`, `status` ('pass'\|'warn'), `subtitle`, `sourceTool`, `payload`, `expanded`, `onToggle` |
| 25 | **VerificationRing** (SVG circular progress) | S4 | `percent` (83), `value` ('5/6'), `label`, `tone` |
| 26 | **PolicyCheckRow** | S4 (concept in S7) | `label`, `state` ('pass'\|'warn'\|'TBD'), `note` |
| 27 | **RecommendationPanel** | S4 | `text`, `evidenceRefs[]`, `state` |
| 28 | **TrajectoryNode** | S5 | `icon`, `title`, `meta` ('45.2ms'/'Pass'), `state` ('default'/'active'), `accentTone` |
| 29 | **ToolCallNode** | S5 | `toolName`, `status`, `latencyMs`, `selected`, `onSelect` |
| 30 | **NodeDetailsPanel** | S5 | `node` {toolName, status, latency, context, sourceSystem, inputPayload, outputPayload} |
| 31 | **CodeBlock** (syntax-highlighted JSON) | S4, S5 | `json`, `label`, `collapsible` |
| 32 | **ApprovalActionCard** | S6 | `icon`, `title`, `subtitle`, `riskLevel`, `recommendation`, `verificationScore`, `flagReason`, `actions[]`, `accent` |
| 33 | **ConsequenceBanner** | S6 | `tier`, `title`, `body`, `icon` |
| 34 | **EvaluationMetricCard** | S7 | `title`, `value` (89%), `delta`, `comparison`, `meta[]` |
| 35 | **DimensionBar** (Ops vs Baseline dual bar) | S7 | `label`, `opsPct`, `baselinePct`, `delta`, `tone` |
| 36 | **SafetyMetricRow** | S7 | `label`, `value`, `denominator`, `tone` |
| 37 | **KeyFindingPanel** | S7 | `title`, `text` |
| 38 | **MethodologyList** | S7 | `items[]` |
| 39 | **EvalCaseTable** + **EvalCaseRow** | S7 | `rows[]` ({caseId, difficulty, baseline, opspilot, delta}), `filters`, `onRowClick` |
| 40 | **ActionButton** | S1–S7 | `label`, `icon`, `variant` ('primary'/'outline'/'error'/'indigo'/'link'), `onClick`, `busy` |
| 41 | **IconSprite** (Material Symbols → Lucide mapping) | S1–S7 | `name`, `size`, `fill`, `tone` |

*(Note: no **EmptyState** component exists anywhere in the design — flagged in `STITCH_GAPS.md`.)*

**Final reusable-component count: 41.**

## 3. Colors

### 3a. Theme tokens (Tailwind config, Material-3 dark palette — identical across all screens)

| Token | Hex | Token | Hex |
|---|---|---|---|
| `background` | `#131314` | `on-background` | `#e5e2e3` |
| `surface` | `#131314` | `on-surface` | `#e5e2e3` |
| `surface-bright` | `#3a393a` | `surface-dim` | `#131314` |
| `surface-variant` | `#353436` | `on-surface-variant` | `#c7c4d7` |
| `surface-container-lowest` | `#0e0e0f` | `surface-container-low` | `#1c1b1c` |
| `surface-container` | `#201f20` | `surface-container-high` | `#2a2a2b` |
| `surface-container-highest` | `#353436` | `surface-tint` | `#c0c1ff` |
| `inverse-surface` | `#e5e2e3` | `inverse-on-surface` | `#313031` |
| `primary` | `#c0c1ff` | `on-primary` | `#1000a9` |
| `primary-container` | `#8083ff` | `on-primary-container` | `#0d0096` |
| `primary-fixed` | `#e1e0ff` | `on-primary-fixed` | `#07006c` |
| `primary-fixed-dim` | `#c0c1ff` | `on-primary-fixed-variant` | `#2f2ebe` |
| `inverse-primary` | `#494bd6` | — | — |
| `secondary` | `#b9c8de` | `on-secondary` | `#233143` |
| `secondary-container` | `#39485a` | `on-secondary-container` | `#a7b6cc` |
| `secondary-fixed` | `#d4e4fa` | `on-secondary-fixed` | `#0d1c2d` |
| `secondary-fixed-dim` | `#b9c8de` | `on-secondary-fixed-variant` | `#39485a` |
| `tertiary` | `#ffb783` | `on-tertiary` | `#4f2500` |
| `tertiary-container` | `#d97721` | `on-tertiary-container` | `#452000` |
| `tertiary-fixed` | `#ffdcc5` | `on-tertiary-fixed` | `#301400` |
| `tertiary-fixed-dim` | `#ffb783` | `on-tertiary-fixed-variant` | `#703700` |
| `error` | `#ffb4ab` | `on-error` | `#690005` |
| `error-container` | `#93000a` | `on-error-container` | `#ffdad6` |
| `outline` | `#908fa0` | `outline-variant` | `#464554` |

### 3b. Ad-hoc brand/surface hex values (hard-coded classes)

| Value | Usage |
|---|---|
| `#6366F1` | indigo accent — Hackathon Demo button, search/input focus ring, Run OpsPilot button, timeline timestamps, pulse-dot base, shadow glows `rgba(99,102,241,…)` |
| `#0A0A0B` | dark input/card fill, log surface, canvas bg on S2/S3 blotches |
| `#141415` | recurring card surface (S1, S3, S6) |
| `#262626` | recurring border (cards, inputs, chips) |
| `#94A3B8` | secondary/slate text (buttons, chips, context badges) |
| `#000000` | terminal/log backgrounds (S1 timeline, S3 AGENT_STDOUT, S5 payload blocks) |
| `#ffffff` | white text on indigo buttons / bars |

### 3c. Semantic status colors (Tailwind defaults)

- `emerald-400` `#34d399` / `emerald-500` `#10b981` — success, live, passed, running
- `amber-500` — warning traffic dot
- `red-500` — error traffic dot
- `indigo-600` — hover on Approve Action button
- rgba glows: `rgba(99,102,241,0.2 / 0.39 / 0.5 / 0.7)`; `rgba(255,180,171,0.05)` (error card glow); `rgba(255,255,255,0.03)` (grid pattern); `rgba(20,20,21,0.7)` (glass panel)

## 4. Fonts / typography

**Web fonts loaded:** `Material Symbols Outlined` · `Geist` (display/headlines) · `Inter` (body) · `JetBrains Mono` (labels/code). Design system tokens (identical config in every HTML file):

| Token | Font family | Size / line-height | Weight | Letter-spacing |
|---|---|---|---|---|
| `display` | Geist | 32px / 40px | 600 | −0.02em |
| `headline-lg` | Geist | 24px / 32px | 600 | −0.01em |
| `headline-md` | Geist | 20px / 28px | 500 | — |
| `body-lg` | Inter | 16px / 24px | 400 | — |
| `body-md` (default) | Inter | 14px / 20px | 400 | — |
| `body-sm` | Inter | 12px / 18px | 400 | — |
| `code-md` | JetBrains Mono | 13px / 20px | 400 | — |
| `label-caps` | JetBrains Mono | 11px / 16px | 600 | 0.05em |

**Spacing/radius tokens used:** `sidebar_width: 240px` · `unit: 8px` · `stack_sm: 8px` · `stack_md: 16px` · `stack_lg: 24px` · `container_padding: 24px` · `gutter: 16px` · radius `DEFAULT 0.25rem` / `lg 0.5rem` / `xl 0.75rem` / `full 9999px`.

**Inline/ad-hoc sizes also present:** `text-[56px]` (evaluation accuracy), `text-[24px]`, `text-lg`, `text-xl`, `text-[11px]`, `text-[10px]`, icon sizes `text-[12px]`→`text-[18px]`, `text-6xl` (decorative watermark). Body default `font-body-md`; uppercase `tracking-wider` labels.

## 5. Icons (Material Symbols → Lucide mapping)

| Material Symbol | Screens | Lucide name |
|---|---|---|
| `dashboard` | S1–S7 sidebar | `LayoutDashboard` |
| `list_alt` | S1–S7 sidebar, S1/S2 topbar | `ClipboardList` |
| `smart_toy` | S1–S7 sidebar, S5 node | `Bot` |
| `verified_user` | S1–S7 sidebar | `ShieldCheck` |
| `fact_check` | S1–S7 sidebar, S1 preview card | `BadgeCheck` |
| `analytics` | S1–S7 sidebar | `ChartColumn` (alias `BarChart3`) |
| `trending_up` | S1–S7 sidebar, S7 delta | `TrendingUp` |
| `history` | S1–S7 sidebar | `History` |
| `cloud_done` | S1–S7 sidebar (System Status) | `CloudCheck` (fallback `Cloud`+`Check`) |
| `menu` | S1 mobile | `Menu` |
| `search` | S1–S7 topbar | `Search` |
| `notifications` | S1–S7 topbar | `Bell` |
| `settings` | S1–S7 topbar | `Settings` |
| `warning` | S1, S4, S6 | `TriangleAlert` (alias `AlertTriangle`) |
| `shield` | S1 | `Shield` |
| `timeline` | S1 | `Activity` |
| `error` | S1, S3 | `CircleAlert` (alias `AlertCircle`) |
| `domain` | S2 | `Building2` |
| `person` | S2, S3, S7 avatar | `User` |
| `info` | S2, S4 | `Info` |
| `send_spark` | S2 | `Send` (with `Sparkles` optional) |
| `rule` | S2 chip, S4 checklist | `ListChecks` |
| `calendar_month` | S2 chip | `CalendarDays` |
| `policy` | S2 chip | `FileCheck` |
| `memory` | S2 logo | `Cpu` |
| `play_arrow` | S2, S7 | `Play` |
| `terminal` | S3 logo/stdout, S6 action code | `Terminal` |
| `check` | S3 steps, S4 checklist | `Check` |
| `gavel` | S3 step, S6 banner | `Gavel` |
| `psychology` | S3 state, S4 watermark, S5 node | `Brain` |
| `folder_open` | S3 | `FolderOpen` |
| `route` | S3 | `Route` |
| `stop_circle` | S3 Abort | `CircleStop` (alias `OctagonX` note) |
| `shield_person` | S4 | `ShieldCheck` (person variant) |
| `check_circle` | S4, S5, S6, S7 | `CircleCheck` (alias `CheckCircle2`) |
| `expand_more` | S4 | `ChevronDown` |
| `expand_less` | S4 | `ChevronUp` |
| `article` | S4 refs | `FileText` |
| `priority_high` | S4 checklist | `OctagonAlert` (alias `AlertOctagon`) |
| `code` | S5 node | `Code` |
| `login` | S5 node | `LogIn` |
| `zoom_in` / `zoom_out` / `fit_screen` | S5 graph | `ZoomIn` / `ZoomOut` / `Scan` (alias `Maximize`) |
| `vpn_key` | S5 auth | `KeyRound` (alias `Key`) |
| `api` | S5 details | `Webhook` |
| `database` | S5 details | `Database` |
| `rocket_launch` | S6, S7 logo | `Rocket` |
| `person_cancel` | S6 | `UserX` |
| `thumb_up` | S6 | `ThumbsUp` |
| `visibility` | S6 | `Eye` |
| `person_remove` | S6 | `UserMinus` |
| `report` | S6 | `OctagonAlert` (critical badge) |
| `inventory_2` | S6 | `Package` |
| `lock_open` | S6 | `LockOpen` (alias `Unlock`) |
| `close` | S4 reject, S7 filters | `X` |
| `arrow_upward` | S7 | `ArrowUp` |
| `lightbulb` | S7 | `Lightbulb` |
| `chevron_right` | S7 | `ChevronRight` |
| `horizontal_rule` | S7 | `Minus` |
| `trending_down` | S7 | `TrendingDown` |
| `format_quote` | S3 | `Quote` |
| `info` (S4 coverage note) | S4 | `Info` (dup) |

**62 unique Material Symbols mapped** (IconSprite centralizes this mapping).

---
*End of STITCH_INVENTORY.md — screen count 7, component count 41.*