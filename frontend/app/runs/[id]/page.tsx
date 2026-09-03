// OPSpilot - frontend/app/runs/[id]/page.tsx
// Live Execution: renders the REAL backend SSE stream for a run.
// Everything shown derives from events received over
// GET /api/runs/{run_id}/stream — never faked or replayed from a mock.
"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { useAgentRunStream, runTrajectoryUrl } from "@/lib/sse";
import { reduceRunEvents } from "@/lib/runEvents";
import type { RunToolCallView, RunViewState, SSEEvent } from "@/types";

type StatusKey = RunViewState["status"];

const STATUS_META: Record<StatusKey, { label: string; className: string }> = {
  waiting: { label: "Pending", className: "bg-surface-variant text-on-surface-variant" },
  running: { label: "Running", className: "bg-tertiary/10 text-tertiary" },
  complete: { label: "Completed", className: "bg-emerald-500/10 text-emerald-400" },
  failed: { label: "Failed", className: "bg-error/10 text-error" },
  blocked: { label: "Blocked", className: "bg-error/10 text-error" },
  awaiting_approval: { label: "Awaiting Approval", className: "bg-amber-500/10 text-amber-400" },
};

function Spinner() {
  return (
    <span
      className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin align-middle"
      aria-hidden="true"
    />
  );
}

function StepIcon({ status }: { status: "pending" | "active" | "complete" | "error" }) {
  if (status === "complete") return <span className="text-emerald-400 text-sm font-bold">{"\u2713"}</span>;
  if (status === "error") return <span className="text-error text-sm font-bold">{"\u2715"}</span>;
  if (status === "active") {
    return (
      <span className="text-tertiary">
        <Spinner />
      </span>
    );
  }
  return <span className="text-on-surface-variant text-sm">{"\u2022"}</span>;
}

function StepTracker({ view }: { view: RunViewState }) {
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl flex flex-col">
      <div className="p-4 border-b border-[#262626]">
        <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider">
          Agent Pipeline
        </h3>
      </div>
      <ol className="p-4 space-y-3 flex-1">
        {view.steps.map((step) => (
          <li key={step.key} className="flex items-center gap-3">
            <span className="w-5 h-5 flex items-center justify-center">
              <StepIcon status={step.status} />
            </span>
            <span
              className={`text-body-sm ${
                step.status === "pending"
                  ? "text-on-surface-variant"
                  : step.status === "error"
                    ? "text-error"
                    : "text-on-surface"
              }`}
            >
              {step.label}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function prettyJSON(value: unknown): string {
  if (value === undefined) return "\u2014";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function ToolCallItem({ call, eventCount }: { call: RunToolCallView; eventCount: number }) {
  const [expanded, setExpanded] = useState(false);
  const isDone = call.success === true || call.success === false;
  const isError = call.success === false;

  return (
    <div className="bg-[#0A0A0B] border border-[#262626] rounded-lg p-3">
      <div className="flex flex-wrap justify-between items-center gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="font-code-md text-code-md text-on-surface hover:text-primary text-left"
        >
          {call.toolName}
          {call.arguments && Object.keys(call.arguments).length > 0 && (
            <span className="text-on-surface-variant text-xs ml-2">
              {Object.keys(call.arguments).join(", ")}
            </span>
          )}
        </button>
        <div className="flex items-center gap-2">
          {isDone && call.durationMs !== undefined && (
            <span className="text-body-sm text-on-surface-variant">{call.durationMs}ms</span>
          )}
          {isDone ? (
            <span
              className={`text-xs px-1.5 py-0.5 rounded ${
                isError ? "bg-error/10 text-error" : "bg-emerald-500/10 text-emerald-400"
              }`}
            >
              {isError ? "error" : "success"}
            </span>
          ) : (
            <span className="text-tertiary text-xs flex items-center gap-1.5">
              <Spinner /> calling...
            </span>
          )}
        </div>
      </div>
      {!isDone && call.calledAt && (
        <p className="text-body-sm text-on-surface-variant mt-1">
          Called at {new Date(call.calledAt).toLocaleTimeString()} (event {eventCount})
        </p>
      )}
      {expanded && (
        <div className="mt-2 space-y-2 border-t border-[#262626] pt-2">
          {call.arguments !== undefined && Object.keys(call.arguments).length > 0 && (
            <div>
              <p className="text-label-caps text-xs uppercase text-on-surface-variant mb-1">Arguments</p>
              <pre className="text-code-md font-code-md text-on-surface-variant whitespace-pre-wrap break-all">
                {prettyJSON(call.arguments)}
              </pre>
            </div>
          )}
          {isDone && (
            <div>
              <p className="text-label-caps text-xs uppercase text-on-surface-variant mb-1">Result</p>
              <pre className="text-code-md font-code-md text-on-surface-variant whitespace-pre-wrap break-all">
                {prettyJSON(call.result)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ToolTimeline({ calls, totalEvents }: { calls: RunToolCallView[]; totalEvents: number }) {
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl flex flex-col">
      <div className="p-4 border-b border-[#262626] flex items-center justify-between">
        <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider">Tool Calls</h3>
        <span className="text-body-sm text-on-surface-variant">{calls.length} called</span>
      </div>
      <div className="p-4 space-y-3 flex-1">
        {calls.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">Awaiting tool calls from the live stream...</p>
        ) : (
          calls.map((call, i) => <ToolCallItem key={call.key} call={call} eventCount={totalEvents} />)
        )}
      </div>
    </div>
  );
}

function ConfidenceMeter({ confidence }: { confidence: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(confidence * 100)));
  return (
    <div className="flex items-center gap-2">
      <div className="w-28 h-1.5 bg-surface-variant rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-body-sm text-on-surface-variant">{pct}%</span>
    </div>
  );
}

function DecisionPanel({ view }: { view: RunViewState }) {
  if (!view.decision) return null;
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
      <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider mb-3">AI Decision</h3>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-code-md text-code-md text-on-surface">{view.decision.type}</span>
        <ConfidenceMeter confidence={view.decision.confidence} />
      </div>
    </div>
  );
}

function VerificationPanel({ view }: { view: RunViewState }) {
  const verifyStep = view.steps.find((s) => s.key === "verify");
  if (view.verificationPassed === undefined && verifyStep?.status === "pending") {
    return null;
  }
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
      <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider mb-3">
        Constitutional Verification
      </h3>
      {view.verificationPassed === true ? (
        <p className="text-body-sm text-emerald-400">All checks passed.</p>
      ) : view.verificationPassed === false ? (
        view.violations.length > 0 ? (
          <ul className="space-y-1">
            {view.violations.map((v, i) => (
              <li key={i} className="text-body-sm text-error">
                {"\u2715"} {v}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-body-sm text-error">Verification failed.</p>
        )
      ) : (
        <p className="text-body-sm text-on-surface-variant">Checking plan against company policy...</p>
      )}
    </div>
  );
}

function AuthorizationPanel({ view }: { view: RunViewState }) {
  if (view.authorizationTier === undefined) return null;
  const tier = view.authorizationTier;
  const tierColor =
    tier <= 1
      ? "text-emerald-400 bg-emerald-500/10"
      : tier === 2
        ? "text-amber-400 bg-amber-500/10"
        : "text-error bg-error/10";
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
      <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider mb-3">Authorization Gate</h3>
      <div className="flex items-center gap-3">
        <span className={`px-2 py-0.5 rounded font-code-md text-code-md ${tierColor}`}>Tier {tier}</span>
        <span className="text-body-sm text-on-surface-variant">
          {tier === 3 ? "requiresHumanApproval" : tier === 2 ? "managerRequired" : "autoApproved"}
        </span>
      </div>
    </div>
  );
}

function ResultBanner({ view }: { view: RunViewState }) {
  if (view.status === "waiting" || view.status === "running") return null;
  const tone =
    view.status === "complete"
      ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/5"
      : view.status === "awaiting_approval"
        ? "text-amber-400 border-amber-500/30 bg-amber-500/5"
        : "text-error border-error/30 bg-error/5";
  const headline =
    view.status === "complete"
      ? "Request complete"
      : view.status === "awaiting_approval"
        ? "Human approval required"
        : view.status === "blocked"
          ? "Request blocked"
          : "Request failed";
  return (
    <div className={`border rounded-xl p-4 ${tone}`}>
      <p className="font-headline-md text-headline-md">{headline}</p>
      {view.finalResult && <p className="text-body-sm mt-1 opacity-80">{view.finalResult}</p>}
      {view.error && <p className="text-body-sm mt-1 opacity-80">{view.error}</p>}
    </div>
  );
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "\u2014";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function LiveEventFeed({ events }: { events: SSEEvent[] }) {
  const shown = events.filter((e) => e.event_type !== "connected");
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider">Raw Event Stream</h3>
        <span className="text-body-sm text-on-surface-variant">{shown.length} events</span>
      </div>
      {shown.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant">Waiting for the first event...</p>
      ) : (
        <ul className="space-y-1 max-h-64 overflow-y-auto">
          {shown.map((evt, i) => (
            <li key={i} className="flex gap-2 text-body-sm">
              <span className="font-code-md text-on-surface-variant shrink-0">
                {new Date(evt.timestamp).toLocaleTimeString()}
              </span>
              <span className="font-code-md text-primary">{evt.event_type}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { events, isConnected, error, reconnect, finished } = useAgentRunStream(id);
  const view = reduceRunEvents(events);

  const status = STATUS_META[view.status];
  const durationMs =
    view.completedAt && view.startedAt
      ? new Date(view.completedAt).getTime() - new Date(view.startedAt).getTime()
      : undefined;
  let evidenceMessage: string | undefined;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].event_type === "evidence.assembled") {
      evidenceMessage = events[i].message;
      break;
    }
  }

  return (
    <PageShell title={`Live Execution · ${id.slice(0, 8)}`}>
      <div className="bg-[#141415] border border-[#262626] rounded-xl p-4 mb-4">
        <div className="flex flex-wrap justify-between items-start gap-3">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h2 className="font-headline-md text-headline-md text-on-surface">
                Run <span className="font-code-md">{id}</span>
              </h2>
              <span className={`px-2 py-0.5 rounded text-xs ${status.className}`}>{status.label}</span>
              {isConnected && (
                <span className="text-xs text-emerald-400 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  live
                </span>
              )}
            </div>
            <p className="text-body-sm text-on-surface-variant">
              {view.structured
                ? `${view.structured.requestType} · confidence ${Math.round(view.structured.confidence * 100)}%`
                : "Awaiting structured request..."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {!finished && (
              <button
                type="button"
                onClick={reconnect}
                className="px-3 py-2 border border-[#262626] rounded-lg text-body-sm text-on-surface-variant hover:text-on-surface transition-colors"
              >
                Reconnect
              </button>
            )}
            <a
              href={`/requests/${id}/evidence`}
              className="px-4 py-2 bg-primary/10 border border-primary/30 text-primary rounded-lg text-body-sm hover:bg-primary/20 transition-colors"
            >
              View Evidence
            </a>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-body-sm text-on-surface-variant border-t border-[#262626] pt-3">
          <span>Duration: {formatDuration(durationMs ?? NaN)}</span>
          <span>Evidence: {view.evidenceCount} assembled</span>
          <span>Tool calls: {view.toolCalls.length}</span>
        </div>
      </div>

      {error && (
        <div className="bg-error/10 border border-error/30 text-error rounded-xl p-3 text-body-sm">{error}</div>
      )}

      {!error && !isConnected && view.status === "waiting" && (
        <div className="bg-[#141415] border border-[#262626] rounded-xl p-3 text-body-sm text-on-surface-variant flex items-center gap-2">
          <Spinner /> Connecting to the live run stream...
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <StepTracker view={view} />
        <ToolTimeline calls={view.toolCalls} totalEvents={events.length} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
          <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider mb-3">Evidence</h3>
          <p className="font-headline-md text-headline-md text-on-surface">
            {view.evidenceCount}
            <span className="text-body-sm text-on-surface-variant font-body"> items</span>
          </p>
          {evidenceMessage && <p className="text-body-sm text-on-surface-variant mt-1">{evidenceMessage}</p>}
        </div>
        <DecisionPanel view={view} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <VerificationPanel view={view} />
        <AuthorizationPanel view={view} />
      </div>

      {view.approval && (
        <div className="bg-amber-500/5 border border-amber-500/30 rounded-xl p-4">
          <h3 className="font-label-caps text-label-caps uppercase text-amber-400 tracking-wider mb-2">
            Approval Required
          </h3>
          <p className="text-body-sm text-on-surface-variant">
            {view.approval.reason ?? "This action is outside auto-approval tier."}
          </p>
          <a
            href="/approvals"
            className="inline-block mt-3 px-4 py-2 bg-amber-500/10 border border-amber-500/30 text-amber-400 rounded-lg text-body-sm hover:bg-amber-500/20 transition-colors"
          >
            Review in Approvals
          </a>
        </div>
      )}

      <ResultBanner view={view} />
      <LiveEventFeed events={events} />
    </PageShell>
  );
}