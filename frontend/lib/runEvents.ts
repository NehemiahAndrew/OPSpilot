// OPSpilot - frontend/lib/runEvents.ts
// Pure reducer: folds the real SSE event stream into a renderable
// RunViewState for the Live Execution screen. No timers, no mocking.
import type {
  RunStepView,
  RunToolCallView,
  RunViewState,
  SSEEvent,
} from "@/types";

export const WORKFLOW_STEPS: RunStepView[] = [
  { key: "parse", label: "Parse Request", status: "pending" },
  { key: "context", label: "Context Assembly", status: "pending" },
  { key: "evidence", label: "Evidence Assembly", status: "pending" },
  { key: "decision", label: "Decision", status: "pending" },
  { key: "verify", label: "Constitutional Check", status: "pending" },
  { key: "authorize", label: "Authorization Gate", status: "pending" },
  { key: "execute", label: "Action Execution", status: "pending" },
];

export const RUN_STEP_KEYS = new Set(WORKFLOW_STEPS.map((s) => s.key));

export function initialRunView(): RunViewState {
  return {
    status: "waiting",
    steps: WORKFLOW_STEPS.map((s) => ({ ...s })),
    toolCalls: [],
    evidenceCount: 0,
    violations: [],
  };
}

function setStep(
  state: RunViewState,
  key: string,
  status: RunStepView["status"]
): void {
  const step = state.steps.find((s) => s.key === key);
  if (!step) return;
  if (step.status === "complete" || step.status === "error") return;
  step.status = status;
}

function finishTool(
  state: RunViewState,
  pending: RunToolCallView[],
  meta: Record<string, unknown>,
  success: boolean
): void {
  const call = pending.pop();
  if (!call) return;
  const idx = state.toolCalls.findIndex((c) => c.key === call.key);
  if (idx === -1) return;
  state.toolCalls[idx].success = success;
  state.toolCalls[idx].durationMs = Number(meta.duration_ms ?? 0);
  state.toolCalls[idx].result = (meta.result ?? {}) as Record<string, unknown>;
}

export function reduceRunEvents(events: SSEEvent[]): RunViewState {
  const state = initialRunView();
  const pendingCalls: RunToolCallView[] = [];

  for (const evt of events) {
    const t = evt.event_type;
    const meta = evt.metadata ?? {};

    switch (t) {
      case "run.created":
      case "run.started":
        if (state.status === "waiting") state.status = "running";
        state.startedAt = state.startedAt ?? evt.timestamp;
        break;
      case "parsing.started":
        setStep(state, "parse", "active");
        break;
      case "parsing.completed":
        setStep(state, "parse", "complete");
        state.structured = {
          requestType: String(meta.request_type ?? "other"),
          confidence: Number(meta.confidence ?? 0),
        };
        break;
      case "clarification.needed":
        state.status = "blocked";
        state.error = "Request needs clarification";
        break;
      case "context.started":
        setStep(state, "context", "active");
        break;
      case "tool.calling": {
        const toolName = String(meta.tool_name ?? "unknown_tool");
        const call: RunToolCallView = {
          key: `${toolName}-${state.toolCalls.length}`,
          toolName,
          arguments: (meta.arguments ?? {}) as Record<string, unknown>,
          calledAt: evt.timestamp,
          success: undefined,
          durationMs: undefined,
          expanded: false,
        };
        pendingCalls.push(call);
        state.toolCalls.push(call);
        break;
      }
      case "tool.completed":
        finishTool(state, pendingCalls, meta, true);
        break;
      case "tool.failed":
        finishTool(state, pendingCalls, meta, false);
        break;
      case "evidence.assembled":
        setStep(state, "context", "complete");
        setStep(state, "evidence", "complete");
        const n = Number(meta.evidence_count);
        if (Number.isFinite(n) && n > 0) state.evidenceCount = n;
        break;
      case "decision.started":
        setStep(state, "decision", "active");
        break;
      case "decision.completed":
        setStep(state, "decision", "complete");
        state.decision = {
          type: String(meta.decision_type ?? "unknown"),
          confidence: Number(meta.confidence ?? 0),
        };
        break;
      case "verification.started":
        setStep(state, "verify", "active");
        break;
      case "verification.passed":
        setStep(state, "verify", "complete");
        state.verificationPassed = true;
        state.violations = [];
        break;
      case "verification.failed": {
        setStep(state, "verify", "error");
        state.verificationPassed = false;
        const v = meta.violations;
        state.violations = Array.isArray(v) ? v.map(String) : [];
        break;
      }
      case "authorization.evaluated":
        setStep(state, "authorize", "complete");
        state.authorizationTier = Number(
          meta.tier ?? state.authorizationTier ?? 1
        );
        break;
      case "approval.required": {
        setStep(state, "authorize", "complete");
        if (state.status !== "blocked") state.status = "awaiting_approval";
        state.approval = {
          id: meta.approval_id ? String(meta.approval_id) : undefined,
          reason:
            evt.message ||
            (meta.reason ? String(meta.reason) : undefined),
          riskLevel: meta.risk_level ? String(meta.risk_level) : undefined,
        };
        break;
      }
      case "action.executing":
        setStep(state, "execute", "active");
        if (state.status === "waiting") state.status = "running";
        break;
      case "action.completed":
        setStep(state, "execute", "complete");
        break;
      case "run.completed":
        setStep(state, "execute", "complete");
        state.status = "complete";
        state.finalResult =
          (meta.final_decision ? String(meta.final_decision) : undefined) ||
          evt.message ||
          "Run completed";
        state.completedAt = evt.timestamp;
        break;
      case "run.failed":
        state.status = "failed";
        state.error =
          evt.message || (meta.error ? String(meta.error) : "Run failed");
        state.completedAt = evt.timestamp;
        break;
      case "run.blocked":
        state.status = "blocked";
        state.completedAt = evt.timestamp;
        break;
      default:
        break;
    }
  }

  return state;
}