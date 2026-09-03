"""OpsPilot — Evaluation API routes.

Provides endpoints for running evaluations and viewing results.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.app.evaluation.harness import EvaluationHarness, load_cases
from backend.app.models.evaluation import EvaluationRun, EvaluationSummary

logger = logging.getLogger(__name__)

router = APIRouter()

# Path to store results
RESULTS_PATH = Path(__file__).parent.parent.parent.parent / "evaluation" / "results"

# In-memory store for running evaluations
_running_evaluations: dict[str, EvaluationRun] = {}


# ======================================================================
# Request/Response models
# ======================================================================
class RunEvaluationRequest(BaseModel):
    system: Literal["baseline", "opspilot"]
    dry_run: bool = False


class RunEvaluationResponse(BaseModel):
    evaluation_run_id: str
    status: str
    message: str


class EvaluationStatusResponse(BaseModel):
    run_id: str
    system: str
    status: str
    total_cases: int
    completed_cases: int
    progress_percent: float


# ======================================================================
# Endpoints
# ======================================================================
@router.post("/run", response_model=RunEvaluationResponse)
async def run_evaluation(
    request: RunEvaluationRequest,
    background_tasks: BackgroundTasks,
):
    """Start an evaluation run asynchronously.

    POST /api/evaluation/run
    body: { system: "baseline" | "opspilot" }

    Returns { evaluation_run_id } immediately.
    The run executes in the background.
    """
    harness = EvaluationHarness()
    eval_run = EvaluationRun(system=request.system)
    _running_evaluations[eval_run.run_id] = eval_run

    async def _run_in_background():
        try:
            result = await harness.run_evaluation(request.system, dry_run=request.dry_run)
            _running_evaluations[eval_run.run_id] = result
        except Exception as exc:
            logger.exception("Evaluation failed: %s", exc)
            eval_run.status = "failed"
            _running_evaluations[eval_run.run_id] = eval_run

    background_tasks.add_task(_run_in_background)

    return RunEvaluationResponse(
        evaluation_run_id=eval_run.run_id,
        status="started",
        message=f"Evaluation for {request.system} started in background",
    )


@router.get("/runs/{run_id}/status", response_model=EvaluationStatusResponse)
async def get_evaluation_status(run_id: str):
    """Get the status of an evaluation run.

    GET /api/evaluation/runs/{id}/status
    Returns progress and partial results.
    """
    eval_run = _running_evaluations.get(run_id)
    if not eval_run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    progress = (
        (eval_run.completed_cases / eval_run.total_cases * 100)
        if eval_run.total_cases > 0
        else 0
    )

    return EvaluationStatusResponse(
        run_id=eval_run.run_id,
        system=eval_run.system,
        status=eval_run.status,
        total_cases=eval_run.total_cases,
        completed_cases=eval_run.completed_cases,
        progress_percent=round(progress, 1),
    )


@router.get("/runs/{run_id}/results")
async def get_evaluation_results(run_id: str):
    """Get the complete results of an evaluation run.

    GET /api/evaluation/runs/{id}/results
    Returns complete scored results.
    """
    eval_run = _running_evaluations.get(run_id)
    if not eval_run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    return eval_run.model_dump(mode="json")


@router.get("/comparison")
async def get_comparison():
    """Get a side-by-side comparison of baseline vs OpsPilot.

    GET /api/evaluation/comparison
    Returns both system results for comparison.
    """
    baseline = _load_stored_results("baseline")
    opspilot = _load_stored_results("opspilot")

    summary = EvaluationSummary(
        baseline=baseline,
        opspilot=opspilot,
    )

    return summary.model_dump(mode="json")


@router.get("/cases")
async def get_cases():
    """Get all evaluation cases.

    GET /api/evaluation/cases
    Returns the frozen evaluation cases.
    """
    cases = load_cases()
    return [c.model_dump() for c in cases]


@router.get("/results")
async def get_all_results():
    """Get the latest results for both systems.

    GET /api/evaluation/results
    Returns stored baseline and opspilot results.
    """
    baseline = _load_stored_results("baseline")
    opspilot = _load_stored_results("opspilot")

    return {
        "baseline": baseline.model_dump(mode="json") if baseline else None,
        "opspilot": opspilot.model_dump(mode="json") if opspilot else None,
    }


def _load_stored_results(system: str) -> Optional[EvaluationRun]:
    """Load stored results from disk."""
    filepath = RESULTS_PATH / f"{system}_results.json"
    if not filepath.exists():
        return None

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
        return EvaluationRun(**data)
    except Exception as exc:
        logger.warning("Failed to load %s results: %s", system, exc)
        return None
