// OPSpilot - frontend/app/dashboard/RequiresAttention.tsx
import type { ApprovalRecord } from "@/types";

export function RequiresAttention({ approvals }: { approvals: ApprovalRecord[] }) {
  return (
    <div className="bg-[#141415] border border-[#262626] rounded-xl flex flex-col">
      <div className="p-4 border-b border-[#262626] flex justify-between items-center">
        <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px] text-primary">warning</span>
          Requires Attention
        </h3>
        <span className="bg-secondary-container text-on-secondary-container text-[10px] px-2 py-0.5 rounded-full font-bold">{approvals.length} PENDING</span>
      </div>
      <div className="p-4 space-y-4 flex-1">
        {approvals.slice(0, 2).map((a) => (
          <div key={a.id} className="bg-[#0A0A0B] border border-[#262626] rounded-lg p-3 hover:border-primary transition-colors cursor-pointer group">
            <div className="flex justify-between items-start mb-2">
              <div className="font-body-md font-medium text-on-surface">{a.employeeName}</div>
              <span className="bg-surface-variant text-on-surface-variant text-[10px] px-1.5 py-0.5 rounded font-code-md">{a.requestId}</span>
            </div>
            <button className="w-full py-1.5 bg-transparent border border-[#262626] text-[#94A3B8] rounded text-body-sm font-medium hover:text-white hover:border-[#6366F1] transition-all group-hover:bg-primary/10">Review Details</button>
          </div>
        ))}
      </div>
      <div className="p-3 border-t border-[#262626] text-center">
        <a href="/approvals" className="text-primary text-body-sm hover:underline">View all approvals</a>
      </div>
    </div>
  );
}