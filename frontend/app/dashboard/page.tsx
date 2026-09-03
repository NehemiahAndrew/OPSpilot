// OPSpilot - frontend/app/dashboard/page.tsx
import { PageShell } from "@/components/layout/PageShell";
import { getTimeBasedGreeting } from "@/lib/utils";
import { requestService } from "@/services/requestService";
import { agentRunService } from "@/services/agentRunService";
import { approvalService } from "@/services/approvalService";
import { DashboardMetrics } from "./Metrics";
import { RequiresAttention } from "./RequiresAttention";
import { AgentActivity } from "./AgentActivity";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [requests, runs, approvals] = await Promise.all([
    requestService.getRequests(),
    agentRunService.getRuns(),
    approvalService.getApprovals(),
  ]);

  const completedRuns = runs.filter((r) => r.status === "completed").length;
  const awaitingApproval = approvals.filter((a) => a.status === "pending").length;
  const escalatedRequests = requests.filter((r) => r.status === "escalated").length;

  return (
    <PageShell>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="font-headline-lg text-headline-lg text-on-surface">{getTimeBasedGreeting()}, Alex</h2>
          <p className="text-on-surface-variant mt-1">Here&apos;s what&apos;s happening across your workforce operations.</p>
        </div>
        <div className="flex items-center gap-2 text-label-caps font-label-caps text-on-surface-variant bg-surface-container px-3 py-1.5 rounded-full border border-[#262626]">
          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
          Live Data Mode
        </div>
      </div>

      <DashboardMetrics requests={requests.length} completed={completedRuns} awaiting={awaitingApproval} escalated={escalatedRequests} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <RequiresAttention approvals={approvals.filter((a) => a.status === "pending")} />
        <AgentActivity runs={runs} />
      </div>
    </PageShell>
  );
}
