# OpsPilot — Safety and Reliability Layer

## Why the Constitutional Checker is Deterministic

The Constitutional Checker performs all 10 checks using pure,
deterministic logic — no LLM calls, no probabilistic inference,
no model judgment. This is essential because:

1. **Reproducibility.** The same inputs always produce the same
   results. A check that "balance >= requested_days" either passes
   or fails — there is no gray area for an LLM to interpret differently
   on different runs.

2. **No circular verification.** An LLM-based verifier would be
   checking its own output. If the Decision Agent hallucinates,
   a second LLM call has no guarantee of catching it. Deterministic
   rules eliminate this circularity entirely.

3. **Auditability.** Every check produces a structured `CheckResult`
   with a name, pass/fail status, severity level, and a human-readable
   detail string. This creates a complete audit trail.

4. **Performance.** Deterministic checks execute in milliseconds
   with no network latency or token costs.

## Why the Authorization Gate Has No LLM

The Authorization Gate is a hard boundary. No LLM should ever be
able to execute a consequential action (termination, suspension,
disciplinary action) autonomously. This is enforced by pure code:

1. **Hardcoded tier mapping.** The `TIER_ACTION_MAP` is a static
   dictionary mapping action types to required tiers. No model
   can override this mapping.

2. **Non-negotiable rules.** The `evaluate()` function implements
   two absolute rules:
   - Constitutional check failure → always BLOCKED
   - Tier 3 → always BLOCKED, always requires human approval

   These rules cannot be bypassed by any prompt, context window
   manipulation, or model hallucination.

3. **Separation of concerns.** The Decision Agent proposes a
   decision (including a tier). The Constitutional Checker validates
   the evidence. The Authorization Gate enforces the permission
   boundary. No single component can override the others.

## The 10 Constitutional Checks

| Check | Name | Severity | Description |
|-------|------|----------|-------------|
| CHECK-001 | `employee_exists` | error | Employee record must exist and be active |
| CHECK-002 | `evidence_refs_valid` | error | Every evidence_ref must exist in the manifest |
| CHECK-003 | `policy_exists` | error | Policy evidence must be present for decisions |
| CHECK-004 | `balance_arithmetic_correct` | error | Available days >= requested days (arithmetic) |
| CHECK-005 | `notice_period_satisfied` | error | Requested date - today >= policy notice days |
| CHECK-006 | `coverage_not_violated` | warning/error | Team coverage must be sufficient |
| CHECK-007 | `no_duplicate_request` | error | No pending request for same employee/type/date |
| CHECK-008 | `authorization_tier_matches_action` | error | Termination/suspension must be tier 3 |
| CHECK-009 | `consequential_requires_approval` | error | Tier 3 must have requires_human_approval=True |
| CHECK-010 | `evidence_not_stale` | warning | Evidence must be retrieved within 10 minutes |

Every check is a standalone function returning a `CheckResult`.
Tests can call any check independently without setting up the full
checker pipeline.

## The Tier System

| Tier | Class | Default Gate | Human Approval | Examples |
|------|-------|-------------|----------------|----------|
| 1 | Informational / read-only | Execute | Not required | Policy query, employee status, schedule lookup |
| 2 | Standard actions | Route to Approval Center | Required (in-band) | Leave approval, task reassignment |
| 3 | Consequential actions | **BLOCKED** | Mandatory + Tier-3 override | Termination, suspension, disciplinary action |

**Tier 3 cannot be bypassed even by a correct LLM decision.**
The Authorization Gate unconditionally blocks any tier 3 action
and requires human approval. This is enforced in the `evaluate()`
function: if `decision.authorization_tier == 3`, the result is
always `permitted=False, requires_human_approval=True`. No amount
of evidence or confidence can override this.

## How the System Handles Hallucinated Evidence

The safety layer catches hallucinated evidence at multiple levels:

1. **Context Assembly Agent** (`CHECK-002` territory): The manifest
   validates that every `tool_call_id` in evidence items corresponds
   to an actual tool call. Fabricated IDs mark the manifest as
   `"invalid"`.

2. **Decision Agent**: The `_validate_decision()` method checks
   that every `evidence_ref` in the decision corresponds to a real
   evidence item in the manifest. Fabricated references override
   the decision to escalate.

3. **Constitutional Checker** (`CHECK-002`): Independently verifies
   that every `evidence_ref` in the decision exists in the manifest.
   This is a second, independent check that catches anything the
   Decision Agent might miss.

4. **Authorization Gate**: If any constitutional check fails
   (including fabricated evidence), the gate blocks execution
   regardless of the decision type or tier.

This defense-in-depth approach ensures that hallucinated evidence
cannot propagate through the system.

## Known Limitations

1. **Time-sensitive checks.** CHECK-005 (notice period) and
   CHECK-010 (evidence freshness) depend on wall-clock time.
   Results may change if the system clock is adjusted or if
   evidence ages past the 10-minute window.

2. **Policy rules structure.** CHECK-005 reads `policy.rules.notice_days`
   from the evidence data dict. If the policy data structure
   changes, this check must be updated. The check uses `.get()`
   with defaults to be resilient to missing keys.

3. **Coverage check heuristics.** CHECK-006 uses `is_coverage_sufficient`
   and `only_scheduled_employee` fields from the coverage data.
   If these fields are absent or have unexpected values, the check
   falls back to a warning rather than a hard failure.

4. **No runtime policy updates.** The checker reads evidence data
   that was already retrieved by the Context Assembly Agent. If
   policy rules change after evidence collection, the checker uses
   the stale evidence. This is by design — the evidence manifest
   is frozen at the time of collection.

5. **Deterministic ≠ exhaustive.** Deterministic checks catch known
   violation patterns. Novel attack patterns or edge cases not
   covered by the 10 checks may slip through. The system should
   be extended with additional checks as new violation patterns
   are discovered.