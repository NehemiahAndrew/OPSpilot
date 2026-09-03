// OPSpilot - frontend/app/requests/page.tsx
import { PageShell } from "@/components/layout/PageShell";
import { requestService } from "@/services/requestService";
import Link from "next/link";

export default async function RequestsPage() {
  const requests = await requestService.getRequests();

  return (
    <PageShell title="Requests">
      <div className="flex justify-between items-center mb-4">
        <div className="flex gap-2">
          <button className="px-3 py-1.5 bg-surface-container border border-[#262626] rounded text-body-sm text-on-surface">All Types</button>
          <button className="px-3 py-1.5 bg-transparent border border-[#262626] rounded text-body-sm text-on-surface-variant">Leave</button>
          <button className="px-3 py-1.5 bg-transparent border border-[#262626] rounded text-body-sm text-on-surface-variant">Task</button>
        </div>
        <Link href="/requests/new" className="px-4 py-2 bg-primary text-on-primary rounded-lg text-body-sm font-medium hover:bg-opacity-90 transition-opacity">
          New Request
        </Link>
      </div>

      <div className="bg-[#141415] border border-[#262626] rounded-xl overflow-hidden">
        <table className="w-full text-body-sm">
          <thead className="bg-surface-container border-b border-[#262626]">
            <tr>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Request ID</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Type</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Status</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Confidence</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Employee</th>
              <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Date</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((req) => (
              <tr key={req.id} className="border-b border-[#262626] hover:bg-surface-container transition-colors">
                <td className="p-4 font-code-md text-primary">{req.id}</td>
                <td className="p-4 text-on-surface">{req.requestType.replace("_", " ")}</td>
                <td className="p-4">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    req.status === "completed" ? "bg-emerald-500/10 text-emerald-400" :
                    req.status === "awaiting_approval" ? "bg-tertiary/10 text-tertiary" :
                    req.status === "escalated" ? "bg-error/10 text-error" :
                    "bg-surface-variant text-on-surface-variant"
                  }`}>{req.status.replace("_", " ")}</span>
                </td>
                <td className="p-4 text-on-surface-variant">{req.structuredRequest.confidence ? `${Math.round(req.structuredRequest.confidence * 100)}%` : "—"}</td>
                <td className="p-4 text-on-surface">{req.employeeName ?? "—"}</td>
                <td className="p-4 text-on-surface-variant">{new Date(req.createdAt).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}
