// OPSpilot - frontend/app/dashboard/AgentActivity.tsx
import type { AgentRun } from "@/types";

export function AgentActivity({ runs }: { runs: AgentRun[] }) {
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl flex flex-col lg:col-span-2">
      <div className="p-4 border-b border-[#262626] flex justify-between items-center">
        <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px]">timeline</span>
          Live Agent Activity
        </h3>
        <div className="flex items-center gap-2 text-body-sm text-on-surface-variant">
          Filter by: <span className="text-on-surface bg-surface-container px-2 py-0.5 rounded cursor-pointer border border-[#262626]">All Agents</span>
        </div>
      </div>
      <div className="p-0 flex-1 bg-[#000000] rounded-b-xl overflow-hidden font-code-md text-code-md text-on-surface-variant relative">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black pointer-events-none z-10"></div>
        <div className="p-4 space-y-2 h-full overflow-y-auto">
          {runs.slice(0, 5).map((run, idx) => (
            <div key={run.id} className="flex gap-4 p-1 hover:bg-[#141415] rounded transition-colors">
              <span className="text-[#6366F1] opacity-70 w-20 shrink-0">14:32:0{idx + 1}</span>
              <div className="flex-1">
                <span className="text-on-surface">[{run.currentAgent ?? "Orchestrator"}]</span>{" "}
                <span className="text-on-surface-variant">{run.status === "completed" ? "Completed" : "Processing"} request {run.requestId}</span>
              </div>
              <span className={`text-xs ${run.status === "completed" ? "text-emerald-400" : run.status === "failed" ? "text-error" : "text-tertiary"}`}>{run.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}