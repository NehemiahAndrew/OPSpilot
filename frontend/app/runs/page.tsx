// OPSpilot - frontend/app/runs/page.tsx
import { PageShell } from "@/components/layout/PageShell";
import { agentRunService } from "@/services/agentRunService";
import Link from "next/link";
import type { AgentRun } from "@/types";

export default async function RunsPage() {
  const runs: AgentRun[] = await agentRunService.getRuns();

  return (
    <PageShell title="Agent Runs">
      <div className="bg-[#141415] border border-[#262626] rounded-xl overflow-hidden">
        <table className="w-full text-body-sm">
          <thead className="bg-surface-container border-b border-[#262626]">
            <tr>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Run ID</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Status</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Agents</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Tool Calls</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Duration</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Actions</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => {
              const statusStr = String(run.status);
              const agents = run.agentsInvolved?.join(", ") ?? run.currentAgent ?? "ContextAssembly, Decision";
              return (
                <tr key={run.id} className="border-b border-[#262626] hover:bg-surface-container transition-colors">
                  <td className="p-4 font-code-md text-primary">{run.id}</td>
                  <td className="p-4">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      statusStr === "completed" ? "bg-emerald-500/10 text-emerald-400" :
                      statusStr === "running" || statusStr === "in_progress" ? "bg-tertiary/10 text-tertiary" :
                      statusStr === "failed" ? "bg-error/10 text-error" :
                      "bg-surface-variant text-on-surface-variant"
                    }`}>{statusStr}</span>
                  </td>
                  <td className="p-4 text-on-surface-variant">{agents}</td>
                  <td className="p-4 text-on-surface-variant">{run.totalToolCalls}</td>
                  <td className="p-4 text-on-surface-variant">{run.totalDurationMs ? `${Math.round(run.totalDurationMs / 1000)}s` : "—"}</td>
                  <td className="p-4">
                    <Link href={`/runs/${run.id}`} className="text-primary hover:underline">View</Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}
