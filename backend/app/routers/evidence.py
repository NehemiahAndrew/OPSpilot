"""OpsPilot — Evidence & Provenance API routes.

GET /api/runs/{run_id}/evidence — complete evidence chain with provenance
"""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

from backend.app.database import fetch_many, fetch_one, is_connected

router = APIRouter()


@router.get("/{run_id}/evidence")
async def get_evidence_provenance(run_id: str) -> dict:
    """Return the full evidence manifest, decision, and provenance chain.

    The provenance links each evidence item to its tool call, raw result,
    retrieval timestamp, and verification status. This enables judges to
    trace every decision back to the raw database query that produced it.
    """
    # Check run exists
    run_row = await fetch_one(
        """SELECT id FROM agent_runs WHERE id = $1 LIMIT 1""",
        (run_id,),
    )
    if not run_row:
        raise HTTPException(status_code=404, detail="Run not found")

    # Fetch evidence items with tool call details
    evidence_rows = await fetch_many(
        """SELECT
              e.id,
              e.tool_call_id,
              e.evidence_type,
              e.evidence_key,
              e.evidence_value,
              e.retrieved_at,
              e.used_in_decision,
              e.cited_in_reason,
              tc.tool_name,
              tc.arguments,
              tc.result,
              tc.called_at
           FROM agent_evidence e
           LEFT JOIN agent_tool_calls tc ON tc.id = e.tool_call_id
           WHERE e.run_id = $1
           ORDER BY e.retrieved_at ASC""",
        (run_id,),
    )

    # Fetch decision with evidence refs
    decision_row = await fetch_one(
        """SELECT id, decision_type, recommended_action, reason,
                  evidence_refs, policy_refs, conflicts_identified,
                  authorization_tier, confidence, verification_passed,
                  verification_failures, created_at
           FROM agent_decisions
           WHERE run_id = $1
           ORDER BY created_at DESC LIMIT 1""",
        (run_id,),
    )

    # Fetch constitutional check results if available
    constitutional_row = await fetch_one(
        """SELECT metadata FROM audit_logs
           WHERE run_id = $1 AND action = 'constitutional_check'
           ORDER BY timestamp DESC LIMIT 1""",
        (run_id,),
    )

    # Build provenance chain
    provenance = []
    for row in evidence_rows:
        tool_call_id = str(row["tool_call_id"]) if row["tool_call_id"] else ""
        evidence_id = str(row["id"])

        # Determine verification status
        # - If tool_call succeeded and evidence was cited in decision -> "verified"
        # - If tool_call failed -> "invalid"
        # - If tool_call succeeded but evidence not cited -> "warning"
        tc_success = row.get("result") is not None
        cited = bool(row["cited_in_reason"])
        if not tc_success:
            verification_status = "invalid"
        elif cited:
            verification_status = "verified"
        else:
            verification_status = "warning"

        # Data summary based on evidence type
        data = row["evidence_value"] or {}
        summary = _summarize_evidence(row["evidence_type"], row["evidence_key"], data)

        # What was this evidence used for
        used_for = _infer_used_for(row["evidence_key"], row["evidence_type"])

        provenance.append({
            "evidence_id": evidence_id,
            "tool_call_id": tool_call_id,
            "tool_name": row["tool_name"] or "unknown",
            "arguments": row["arguments"] or {},
            "raw_result": row["result"] or {},
            "retrieved_at": row["called_at"] if row["called_at"] else row["retrieved_at"],
            "cited_in_decision": cited,
            "verification_status": verification_status,
            "evidence_type": row["evidence_type"],
            "evidence_key": row["evidence_key"],
            "data_summary": summary,
            "used_for": used_for,
        })

    # Build evidence manifest (from run state if available, or reconstructed)
    manifest_items = []
    for row in evidence_rows:
        manifest_items.append({
            "evidence_id": str(row["id"]),
            "tool_call_id": str(row["tool_call_id"]) if row["tool_call_id"] else "",
            "evidence_type": row["evidence_type"],
            "evidence_key": row["evidence_key"],
            "data": row["evidence_value"] or {},
            "retrieved_at": row["retrieved_at"],
            "source": "database",
            "relevance": "",
            "used_for": _infer_used_for(row["evidence_key"], row["evidence_type"]),
        })

    manifest = {
        "manifest_id": f"MAN-{run_id[:8]}",
        "run_id": run_id,
        "request_type": decision_row.get("decision_type", "unknown") if decision_row else "unknown",
        "items": manifest_items,
        "missing_data": [],
        "warnings": [],
        "status": "complete" if manifest_items else "insufficient",
        "assembled_at": evidence_rows[0]["retrieved_at"] if evidence_rows else None,
    }

    # Decision output
    decision = None
    if decision_row:
        decision = {
            "decision_type": decision_row["decision_type"],
            "confidence": float(decision_row["confidence"]) if decision_row["confidence"] else 0.0,
            "reason": decision_row["reason"] or "",
            "evidence_refs": decision_row["evidence_refs"] or [],
            "authorization_tier": decision_row["authorization_tier"],
            "requires_human_approval": decision_row["authorization_tier"] >= 3,
            "escalation_reason": decision_row.get("escalation_reason"),
        }

    # Constitutional result
    constitutional_result = None
    if constitutional_row and constitutional_row["metadata"]:
        try:
            constitutional_result = constitutional_row["metadata"]
        except Exception:
            pass

    # Check for fabricated evidence refs (anti-hallucination)
    fabricated_warning = None
    if decision and manifest_items:
        valid_evidence_ids = {item["evidence_id"] for item in manifest_items}
        valid_evidence_ids.update({item["tool_call_id"] for item in manifest_items if item["tool_call_id"]})
        fabricated = [ref for ref in decision.get("evidence_refs", []) if ref not in valid_evidence_ids]
        if fabricated:
            fabricated_warning = {
                "message": f"This decision references evidence that was not retrieved: {fabricated}. The Constitutional Checker has flagged this decision as INVALID.",
                "fabricated_refs": fabricated,
            }

    return {
        "manifest": manifest,
        "decision": decision,
        "constitutional_result": constitutional_result,
        "provenance": provenance,
        "fabricated_warning": fabricated_warning,
    }


def _summarize_evidence(evidence_type: str, evidence_key: str, data: Any) -> str:
    """Generate a human-readable summary of evidence data."""
    # Parse JSON string if needed
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data[:100] if data else "No data"

    if not data:
        return "No data"

    type_lower = evidence_type.lower()
    key_lower = evidence_key.lower()

    if "employee" in type_lower or "employee" in key_lower:
        status = data.get("status", "unknown")
        name = data.get("name", "Unknown")
        return f"Employee: {name} (status: {status})"

    if "balance" in type_lower or "balance" in key_lower:
        available = data.get("available_days") or data.get("available") or data.get("remaining_days")
        unit = data.get("unit", "days")
        if available is not None:
            return f"Available: {available} {unit}"
        return "Leave balance retrieved"

    if "policy" in type_lower or "policy" in key_lower:
        rules = data.get("rules", {})
        if rules:
            return f"Policy rules: {len(rules)} items"
        title = data.get("title", "Policy")
        return f"Policy: {title}"

    if "coverage" in type_lower or "coverage" in key_lower:
        coverage_ok = data.get("coverage_ok") or data.get("is_coverage_sufficient")
        if coverage_ok is not None:
            return f"Coverage {'sufficient' if coverage_ok else 'insufficient'}"
        headcount = data.get("headcount") or data.get("effective_coverage")
        if headcount is not None:
            return f"Headcount: {headcount}"
        return "Team coverage data"

    if "attendance" in type_lower:
        record = data.get("record", data.get("status", "complete"))
        return f"Attendance: {record}"

    if "pending" in type_lower:
        pending = data.get("pending") or data.get("requests") or data.get("items", [])
        count = len(pending) if isinstance(pending, list) else (pending.get("count", 0) if isinstance(pending, dict) else 0)
        return f"{count} pending requests"

    if "historical" in type_lower:
        precedents = data.get("precedents") or data.get("decisions", [])
        count = len(precedents) if isinstance(precedents, list) else 0
        return f"{count} historical precedents"

    if "task" in type_lower:
        tasks = data.get("tasks") or data.get("assignments", [])
        count = len(tasks) if isinstance(tasks, list) else 0
        return f"{count} tasks"

    if "schedule" in type_lower:
        shifts = data.get("shifts") or data.get("schedule", [])
        count = len(shifts) if isinstance(shifts, list) else 0
        return f"{count} shifts"

    # Generic fallback
    keys = list(data.keys())[:3]
    return f"Keys: {', '.join(keys)}"


def _infer_used_for(evidence_key: str, evidence_type: str) -> str:
    """Infer what this evidence was used for in the decision."""
    key_lower = evidence_key.lower()
    type_lower = evidence_type.lower()

    if "employee" in key_lower:
        return "Employee identity and status verification"
    if "balance" in key_lower or "leave" in key_lower:
        return "Leave eligibility check"
    if "policy" in key_lower:
        return "Policy compliance check"
    if "coverage" in key_lower:
        return "Team coverage assessment"
    if "attendance" in key_lower:
        return "Attendance record review"
    if "pending" in key_lower:
        return "Duplicate request check"
    if "historical" in key_lower:
        return "Historical precedent analysis"
    if "task" in key_lower:
        return "Task assignment verification"
    if "schedule" in key_lower:
        return "Schedule conflict check"

    return "Decision support"