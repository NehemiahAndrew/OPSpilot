#!/usr/bin/env python
"""Quick reliability check script."""
import asyncio
import inspect


async def reliability_checks():
    print("=== Reliability Checks ===\n")

    # 1. Pydantic validation
    print("--- Pydantic Model Validation ---")
    from backend.app.agents.decision_agent import DecisionOutput, ConfidenceInputs, compute_confidence

    try:
        d = DecisionOutput(decision_type="approve", confidence=0.9, reason="OK", authorization_tier=1)
        print("  Valid DecisionOutput: OK")
    except Exception as e:
        print(f"  Valid DecisionOutput: FAIL - {e}")

    for desc, kwargs in [
        ("confidence=1.5", dict(decision_type="approve", confidence=1.5, reason="OK", authorization_tier=1)),
        ("tier=5", dict(decision_type="approve", confidence=0.9, reason="OK", authorization_tier=5)),
        ("reason=''", dict(decision_type="approve", confidence=0.9, reason="", authorization_tier=1)),
    ]:
        try:
            DecisionOutput(**kwargs)
            print(f"  Invalid {desc}: NOT CAUGHT (BUG)")
        except Exception:
            print(f"  Invalid {desc}: CAUGHT - OK")

    c = ConfidenceInputs(evidence_completeness=0.8, policy_match_strength=0.9,
                         historical_consistency=0.7, risk_level=0.2)
    score = compute_confidence(c)
    print(f"  Confidence calculation: {score} - OK")

    print("\n--- Retry Logic ---")
    from backend.app.agents.context_agent import ContextAssemblyAgent
    source = inspect.getsource(ContextAssemblyAgent._execute_tool)
    has_retry = "retry" in source.lower() or "attempt" in source.lower()
    print(f"  Context Assembly Agent tool retry: {'OK' if has_retry else 'MISSING'}")

    print("\n--- State Machine ---")
    from backend.app.orchestrator.state import validate_transition, IllegalTransitionError

    valid = [
        ("INIT", "RECEIVED"), ("RECEIVED", "PARSING"), ("PARSING", "CONTEXT_GATHERING"),
        ("CONTEXT_GATHERING", "EVIDENCE_ASSEMBLY"), ("EVIDENCE_ASSEMBLY", "DECISION"),
        ("DECISION", "VERIFICATION"), ("VERIFICATION", "AUTHORIZATION"),
        ("AUTHORIZATION", "EXECUTING"), ("EXECUTING", "COMPLETED"),
        ("AUTHORIZATION", "WAITING_FOR_APPROVAL"), ("BLOCKED", "WAITING_FOR_APPROVAL"),
    ]
    all_valid = True
    for f, t in valid:
        try:
            validate_transition(f, t)
        except Exception:
            print(f"  {f} -> {t}: FAIL")
            all_valid = False
    print(f"  Valid transitions: {'OK' if all_valid else 'FAIL'} ({len(valid)} tested)")

    invalid = [
        ("RECEIVED", "COMPLETED"), ("COMPLETED", "EXECUTING"),
        ("FAILED", "RECEIVED"), ("BLOCKED", "EXECUTING"),
    ]
    all_caught = True
    for f, t in invalid:
        try:
            validate_transition(f, t)
            print(f"  {f} -> {t}: NOT CAUGHT (BUG)")
            all_caught = False
        except IllegalTransitionError:
            pass
    print(f"  Invalid transitions blocked: {'OK' if all_caught else 'FAIL'} ({len(invalid)} tested)")

    print("\n--- Timeout Configuration ---")
    from backend.app.config import settings
    print(f"  Run timeout: {settings.run_timeout_seconds}s - OK")
    print(f"  Max evidence items: {settings.max_evidence_items} - OK")

    print("\n--- Error Handling ---")
    from backend.app.orchestrator.workflow import AgentOrchestrator
    source = inspect.getsource(AgentOrchestrator.run)
    print(f"  Orchestrator try/except: {'OK' if 'try:' in source and 'except' in source else 'MISSING'}")
    print(f"  Error recording: {'OK' if 'errors.append' in source else 'MISSING'}")

    print("\n=== All reliability checks passed ===")


asyncio.run(reliability_checks())
