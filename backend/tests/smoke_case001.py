"""Smoke test for CASE-001 — Sarah Mitchell's leave request.

Verifies the Context Assembly Agent produces a valid manifest
with correct tool calls and valid tool_call_ids.

Uses the seeded in-memory SQLite database (same as unit tests).
"""

import asyncio
import json
import sys
import os
from unittest.mock import patch
from uuid import uuid4

# Ensure we can import conftest
sys.path.insert(0, os.path.dirname(__file__))

from backend.app.agents.context_agent import ContextAssemblyAgent
from backend.app.llm.provider import LLMResponse, TokenUsage, ToolCallRequest
from backend.app.models.tool_contract import ToolContext
from backend.app.tools.registry import build_registry
from backend.data import generator as g
from conftest import FakeDB


class SmokeTestLLM:
    """Mock LLM that calls the full leave request tool sequence."""

    def __init__(self):
        self.call_count = 0

    async def generate(self, messages, system, tools=None, structured_output=None):
        self.call_count += 1
        emp_id = g.emp_uuid("EMP-001")
        dept_id = g.DEPT_ID_BY_CODE["DEP-001"]

        if self.call_count == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id="smoke-tc-1", name="get_employee", arguments={"identifier": "Sarah Mitchell"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            )
        elif self.call_count == 2:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id="smoke-tc-2", name="get_leave_balance", arguments={"employee_id": emp_id, "as_of_date": "2026-08-29"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            )
        elif self.call_count == 3:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCallRequest(id="smoke-tc-3", name="get_policy", arguments={"category": "annual_leave_policy"})],
                    usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                    provider="mock", model="mock", cost_usd=0.0,
                )
        elif self.call_count == 4:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id="smoke-tc-4", name="get_schedule", arguments={"employee_id": emp_id, "date_range_start": "2026-09-01", "date_range_end": "2026-09-05"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            )
        elif self.call_count == 5:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id="smoke-tc-5", name="get_team_coverage", arguments={"department_id": dept_id, "target_date": "2026-09-04"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            )
        elif self.call_count == 6:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id="smoke-tc-6", name="get_pending_requests", arguments={"employee_id": emp_id})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            )
        elif self.call_count == 7:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id="smoke-tc-7", name="get_historical_decisions", arguments={"employee_id": emp_id, "request_type": "leave"})],
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                provider="mock", model="mock", cost_usd=0.0,
            )
        else:
            items = [
                {"tool_call_id": f"smoke-tc-{i}", "evidence_type": t, "evidence_key": k, "relevance": r, "used_for": u}
                for i, (t, k, r, u) in enumerate([
                    ("employee", "employee_record", "Identify requestor", "employee identification"),
                    ("balance", "leave_balance", "Available leave days", "verify balance"),
                    ("policy", "leave_policy", "Leave policy rules", "policy compliance"),
                    ("schedule", "employee_schedule", "Work schedule around leave date", "schedule impact"),
                    ("coverage", "team_coverage", "Team coverage on leave date", "coverage assessment"),
                    ("pending", "pending_requests", "Duplicate detection", "check for duplicates"),
                    ("historical", "historical_decisions", "Past leave decisions", "precedent analysis"),
                ], start=1)
            ]
            return LLMResponse(
                content=json.dumps({"status": "complete", "items": items, "missing_data": [], "warnings": []}),
                tool_calls=[],
                usage=TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
                provider="mock", model="mock", cost_usd=0.0,
            )


def patch_db_modules(fake):
    """Apply DB patches to all modules that import from database."""
    import backend.app.database as db_mod
    import backend.app.tools.read_tools as rt_mod
    import backend.app.tools.action_tools as at_mod
    import backend.app.tools.registry as reg_mod

    db_mod.fetch_one = fake.fetch_one
    db_mod.fetch_many = fake.fetch_many
    db_mod.execute = fake.execute
    db_mod.init_pool = lambda: None
    db_mod.close_pool = lambda: None
    rt_mod.fetch_one = fake.fetch_one
    rt_mod.fetch_many = fake.fetch_many
    at_mod.fetch_one = fake.fetch_one
    at_mod.execute = fake.execute
    reg_mod.execute = fake.execute


async def smoke_test():
    fake = FakeDB()
    patch_db_modules(fake)

    tool_reg = build_registry()

    # Track tool calls
    tool_calls_made = []
    original_call_tool = tool_reg.call_tool

    async def tracking_call(name, arguments, ctx):
        tool_calls_made.append(name)
        return await original_call_tool(name, arguments, ctx)

    tool_reg.call_tool = tracking_call

    run_id = str(uuid4())
    ctx = ToolContext(
        business_id=g.BUSINESS_ID,
        requesting_user_id="USER-001",
        user_role="manager",
        run_id=run_id,
        step_id=str(uuid4()),
    )

    structured_request = {
        "request_type": "leave",
        "employee_hint": "Sarah Mitchell",
        "date_hint": "2026-09-04",
        "reason": "Vacation",
        "urgency": "normal",
    }

    llm = SmokeTestLLM()
    agent = ContextAssemblyAgent(llm_provider=llm, tool_registry=tool_reg)
    manifest = await agent.assemble(run_id, structured_request, ctx)

    print("=" * 60)
    print("SMOKE TEST: CASE-001 (Sarah Mitchell leave request)")
    print("=" * 60)
    print(f"Run ID:            {run_id}")
    print(f"Manifest ID:       {manifest.manifest_id}")
    print(f"Status:            {manifest.status}")
    print(f"Request type:      {manifest.request_type}")
    print(f"Evidence items:    {len(manifest.items)}")
    print(f"Missing data:      {manifest.missing_data}")
    print(f"Warnings:          {manifest.warnings}")
    print(f"Tools called:      {tool_calls_made}")
    print(f"LLM calls:         {llm.call_count}")
    print()

    for item in manifest.items:
        print(f"  [{item.evidence_type}] {item.evidence_key}")
        print(f"    tool_call_id: {item.tool_call_id}")
        print(f"    source:       {item.source}")
        if isinstance(item.data, dict):
            data_keys = list(item.data.keys())
        elif isinstance(item.data, list):
            data_keys = f"list of {len(item.data)} items"
        else:
            data_keys = "empty"
        print(f"    data keys:    {data_keys}")

    print()

    # Validate all tool_call_ids are real
    actual_ids = {f"smoke-tc-{i}" for i in range(1, 8)}
    all_valid = all(item.tool_call_id in actual_ids for item in manifest.items)

    print(f"All tool_call_ids valid: {all_valid}")
    print(f"Manifest status:         {manifest.status}")
    print()

    if manifest.status == "complete" and all_valid:
        print("SMOKE TEST PASSED")
    else:
        print("SMOKE TEST FAILED")
        if not all_valid:
            print("  - Some tool_call_ids are fabricated!")
        if manifest.status != "complete":
            print(f"  - Status is '{manifest.status}' not 'complete'")


if __name__ == "__main__":
    asyncio.run(smoke_test())
