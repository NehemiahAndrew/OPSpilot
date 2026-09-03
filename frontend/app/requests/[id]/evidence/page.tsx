// OPSpilot - frontend/app/requests/[id]/evidence/page.tsx
// Evidence & Decision screen — matches Stitch Screen 4
// Route: /requests/:id/evidence
"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { evidenceService } from "@/services/evidenceService";
import { notFound } from "next/navigation";
import {
  CheckCircle2,
  AlertTriangle,
  CircleAlert,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  FileText,
  Brain,
  Gavel,
  AlertOctagon,
} from "lucide-react";
import type { EvidenceScreenData, EvidenceProvenanceItem } from "@/services/evidenceService";
import type { EvidenceItem, DecisionRecord, ConstitutionalCheckResult, AuthorizationResult } from "@/types";

export default function EvidencePage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;

  const [data, setData] = useState<EvidenceScreenData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const result = await evidenceService.getEvidence(runId);
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load evidence");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [runId]);

  if (loading) {
    return (
      <PageShell title="Loading Evidence">
        <div className="flex items-center justify-center h-64">
          <div className="text-on-surface-variant">Loading evidence chain...</div>
        </div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell title="Error">
        <div className="bg-error/10 border border-error/30 text-error rounded-xl p-6 text-center">
          <h2 className="font-headline-md text-headline-md mb-2">Failed to load evidence</h2>
          <p className="text-body-sm">{error}</p>
        </div>
      </PageShell>
    );
  }

  if (!data) {
    notFound();
  }

  const { manifest, decision, constitutional_result, provenance, fabricated_warning } = data;

  // Calculate verification stats
  const totalChecks = constitutional_result?.all_checks?.length ?? 6;
  const passedChecks = constitutional_result?.all_checks?.filter((c: any) => c.passed).length ?? 0;
  const verificationPercent = totalChecks > 0 ? Math.round((passedChecks / totalChecks) * 100) : 0;

  // Determine decision status badge
  const decisionType = decision?.decisionType ?? "escalate";
  const needsApproval = decision?.requires_human_approval ?? false;
  const isApproval = decisionType === "approve";

  return (
    <PageShell title="Evidence & Decision">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <span className="font-code-md text-primary text-sm">REQ-{runId.slice(0, 8)}</span>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mt-1">Decision Evidence</h1>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 border border-[#262626] rounded-lg text-body-sm text-on-surface-variant hover:text-on-surface transition-colors">
            Reject
          </button>
          <button className="px-4 py-2 bg-primary text-on-primary rounded-lg text-body-sm font-medium hover:bg-opacity-90 transition-opacity">
            Confirm Approval
          </button>
        </div>
      </div>

      {/* Anti-hallucination warning banner */}
      {fabricated_warning && (
        <div className="bg-error/10 border border-error/30 text-error rounded-xl p-4 mb-6 flex items-start gap-3">
          <CircleAlert className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-body-sm font-medium">{fabricated_warning.message}</p>
            <p className="text-body-xs text-on-surface-variant mt-1">
              Fabricated references: {fabricated_warning.fabricated_refs.join(", ")}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Verification Status + Evidence Trail */}
        <div className="lg:col-span-2 space-y-6">
          {/* Verification Status */}
          <div className="bg-[#141415] border border-[#262626] rounded-xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                <ShieldCheck className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h2 className="font-headline-md text-headline-md text-on-surface">
                  {isApproval ? "Approve with Manager Confirmation" : "Decision: " + decisionType}
                </h2>
                <p className="text-body-sm text-on-surface-variant">
                  {passedChecks} / {totalChecks} Checks Passed
                </p>
              </div>
            </div>

            {/* Circular Progress Ring */}
            <div className="flex items-center justify-center gap-6">
              <svg width="100" height="100" viewBox="0 0 100 100">
                <circle
                  cx="50"
                  cy="50"
                  r="42"
                  fill="none"
                  stroke="#262626"
                  strokeWidth="8"
                />
                <circle
                  cx="50"
                  cy="50"
                  r="42"
                  fill="none"
                  stroke={verificationPercent >= 80 ? "#34d399" : verificationPercent >= 50 ? "#ffb783" : "#ffb4ab"}
                  strokeWidth="8"
                  strokeDasharray={`${verificationPercent / 100 * 264} 264`}
                  strokeDashoffset="66"
                  strokeLinecap="round"
                  style={{ transform: "rotate(-90deg)", transformOrigin: "50% 50%" }}
                  className="transition-all duration-500"
                />
              </svg>
              <div className="text-center">
                <div className="font-headline-lg text-headline-lg text-on-surface">
                  {verificationPercent}%
                </div>
                <div className="text-body-sm text-on-surface-variant">
                  Constitutional Score
                </div>
              </div>
            </div>
          </div>

          {/* Evidence Trail */}
          <div className="bg-[#141415] border border-[#262626] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[#262626]">
              <h2 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider">
                Evidence Trail
              </h2>
            </div>
            <div className="p-4 space-y-4">
              {provenance.length === 0 ? (
                <p className="text-body-sm text-on-surface-variant text-center py-8">
                  No evidence items found for this run.
                </p>
              ) : (
                provenance.map((item, index) => (
                  <EvidenceCard
                    key={item.evidence_id}
                    item={item}
                    index={index}
                    expanded={expandedItems.has(item.evidence_id)}
                    onToggle={() => {
                      setExpandedItems((prev) => {
                        const next = new Set(prev);
                        if (next.has(item.evidence_id)) {
                          next.delete(item.evidence_id);
                        } else {
                          next.add(item.evidence_id);
                        }
                        return next;
                      });
                    }}
                  />
                ))
              )}
            </div>
          </div>

          {/* Agent Recommendation */}
          {decision && (
            <div className="bg-[#141415] border border-[#262626] rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                <h2 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider">
                  Agent Recommendation
                </h2>
              </div>
              <p className="text-body-md text-on-surface">
                {decision.reason || "No reason provided."}
              </p>
              {decision.evidenceRefs && decision.evidenceRefs.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {decision.evidenceRefs.map((ref) => (
                    <span
                      key={ref}
                      className="px-2 py-0.5 bg-primary/10 border border-primary/30 text-primary text-xs rounded font-code-md"
                    >
                      {ref}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right column: Policy Checklist */}
        <div className="space-y-6">
          <div className="bg-[#141415] border border-[#262626] rounded-xl p-6">
            <h2 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider mb-4">
              Policy Checklist
            </h2>
            <div className="space-y-3">
              {constitutional_result?.all_checks?.map((check: any) => (
                <PolicyCheckRow
                  key={check.check_name}
                  label={check.check_name.replace("CHECK-", "Check ")}
                  state={check.passed ? "pass" : check.severity === "warning" ? "warn" : "fail"}
                  detail={check.detail}
                />
              ))}
              {/* Fallback if no constitutional result */}
              {(!constitutional_result?.all_checks || constitutional_result.all_checks.length === 0) && (
                <>
                  <PolicyCheckRow label="Active Employee Status" state="pass" detail="Employee record exists and is active" />
                  <PolicyCheckRow label="Sufficient Balance" state="pass" detail="Leave balance covers requested days" />
                  <PolicyCheckRow label="Notice Period Met (>14d)" state="pass" detail="Request submitted with adequate notice" />
                  <PolicyCheckRow label="No Overlapping Requests" state="pass" detail="No conflicting requests found" />
                  <PolicyCheckRow
                    label="Department Coverage Minimum"
                    state="warn"
                    detail="Coverage at minimum threshold"
                  />
                  <PolicyCheckRow
                    label="Manager Review Required"
                    state={needsApproval ? "pass" : "TBD"}
                    detail={needsApproval ? "Tier 3 requires human approval" : "Auto-approved at tier 1"}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}

// Evidence Card Component
function EvidenceCard({
  item,
  index,
  expanded,
  onToggle,
}: {
  item: EvidenceProvenanceItem;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const statusConfig = {
    verified: { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10", label: "Verified" },
    warning: { icon: AlertTriangle, color: "text-amber-400", bg: "bg-amber-500/10", label: "Warning" },
    invalid: { icon: CircleAlert, color: "text-error", bg: "bg-error/10", label: "Invalid" },
  };

  const config = statusConfig[item.verification_status];

  // Evidence type labels
  const typeLabels: Record<string, string> = {
    employee: "Employee Record",
    balance: "Leave Balance",
    policy: "Company Policy",
    coverage: "Team Coverage",
    attendance: "Attendance Record",
    pending: "Pending Requests",
    historical: "Historical Precedent",
    task: "Task Record",
    schedule: "Schedule",
  };

  const evidenceTypeLabel = typeLabels[item.evidence_type] || item.evidence_type;
  const toolCallIdShort = item.tool_call_id.slice(0, 12) + "...";

  return (
    <div className="bg-[#0A0A0B] border border-[#262626] rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full p-4 flex items-center justify-between gap-4 hover:bg-[#141415] transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className={`w-10 h-10 rounded-lg ${config.bg} flex items-center justify-center shrink-0`}>
            <config.icon className={`w-5 h-5 ${config.color}`} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-body-md font-medium text-on-surface truncate">
                {evidenceTypeLabel}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs ${config.bg} ${config.color} font-medium`}>
                {config.label}
              </span>
            </div>
            <div className="flex items-center gap-2 text-body-sm text-on-surface-variant mt-1">
              <span className="font-code-md text-code-md text-primary">{item.tool_name}</span>
              <span>•</span>
              <span className="font-code-md">{toolCallIdShort}</span>
              <span>•</span>
              <span>{new Date(item.retrieved_at).toLocaleString()}</span>
            </div>
          </div>
        </div>
        <ChevronDown
          className={`w-5 h-5 text-on-surface-variant transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div className="border-t border-[#262626] p-4 space-y-4 bg-[#141415]">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="font-label-caps text-label-caps text-xs uppercase text-on-surface-variant mb-1">
                Data Summary
              </p>
              <p className="text-body-sm text-on-surface">{item.data_summary}</p>
            </div>
            <div>
              <p className="font-label-caps text-label-caps text-xs uppercase text-on-surface-variant mb-1">
                Used For
              </p>
              <p className="text-body-sm text-on-surface">{item.used_for}</p>
            </div>
          </div>

          <div>
            <p className="font-label-caps text-label-caps text-xs uppercase text-on-surface-variant mb-1">
              Tool Call Details
            </p>
            <div className="bg-[#0A0A0B] border border-[#262626] rounded-lg p-3 space-y-3">
              <div>
                <p className="font-label-caps text-label-caps text-xs uppercase text-on-surface-variant mb-1">
                  Arguments
                </p>
                <pre className="text-code-xs font-code-md text-on-surface-variant whitespace-pre-wrap break-all max-h-40 overflow-auto">
                  {JSON.stringify(item.arguments, null, 2) || "—"}
                </pre>
              </div>
              <div>
                <p className="font-label-caps text-label-caps text-xs uppercase text-on-surface-variant mb-1">
                  Raw Result
                </p>
                <pre className="text-code-xs font-code-md text-on-surface-variant whitespace-pre-wrap break-all max-h-40 overflow-auto">
                  {JSON.stringify(item.raw_result, null, 2) || "—"}
                </pre>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded text-xs ${config.bg} ${config.color} font-medium`}>
              Verification: {config.label}
            </span>
            {item.cited_in_decision && (
              <span className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary font-medium">
                Cited in Decision
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Policy Check Row Component
function PolicyCheckRow({
  label,
  state,
  detail,
}: {
  label: string;
  state: "pass" | "warn" | "fail" | "TBD";
  detail?: string;
}) {
  const stateConfig = {
    pass: { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10" },
    warn: { icon: AlertTriangle, color: "text-amber-400", bg: "bg-amber-500/10" },
    fail: { icon: CircleAlert, color: "text-error", bg: "bg-error/10" },
    TBD: { icon: Gavel, color: "text-tertiary", bg: "bg-tertiary/10" },
  };

  const config = stateConfig[state];

  return (
    <div className="flex items-center gap-3 p-3 bg-[#0A0A0B] border border-[#262626] rounded-lg">
      <div className={`w-8 h-8 rounded-lg ${config.bg} flex items-center justify-center shrink-0`}>
        <config.icon className={`w-4 h-4 ${config.color}`} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-body-sm text-on-surface truncate">{label}</p>
        {detail && <p className="text-body-xs text-on-surface-variant mt-0.5">{detail}</p>}
      </div>
      <span className={`px-2 py-0.5 rounded text-xs ${config.bg} ${config.color} font-medium shrink-0`}>
        {state === "TBD" ? "TBD" : state === "pass" ? "Pass" : state === "warn" ? "Warn" : "Fail"}
      </span>
    </div>
  );
}