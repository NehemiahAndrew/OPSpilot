// OPSpilot - frontend/app/approvals/page.tsx
import { PageShell } from "@/components/layout/PageShell";
import { ApprovalActions } from "@/components/approvals/ApprovalActions";
import { approvalService } from "@/services/approvalService";
import { getRiskBadgeColor } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function ApprovalsPage() {
  const approvals = await approvalService.getApprovals();

  return (
    <PageShell title="Approvals">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="font-headline-md text-headline-md text-on-surface">Pending Approvals</h2>
          <span className="bg-secondary-container text-on-secondary-container text-[10px] px-2 py-0.5 rounded-full font-bold">
            {approvals.filter((a) => a.status === "pending").length} PENDING
          </span>
        </div>

        <div className="space-y-3">
          {approvals.map((approval) => (
            <div
              key={approval.id}
              className="bg-[#141415] border border-[#262626] rounded-xl p-4"
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="font-body-md font-medium text-on-surface">{approval.employeeName}</span>
                    <span className="bg-surface-variant text-on-surface-variant text-[10px] px-1.5 py-0.5 rounded font-code-md">
                      {approval.id}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getRiskBadgeColor(approval.riskLevel)}`}>
                      {approval.riskLevel.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-body-sm text-on-surface-variant mb-2">{approval.requestTitle}</p>
                  <div className="flex items-center gap-4 text-body-sm text-on-surface-variant">
                    <span>Recommendation: <span className="text-on-surface">{approval.recommendation}</span></span>
                    <span>•</span>
                    <span>Confidence: <span className="text-on-surface">{approval.confidencePercent}%</span></span>
                    <span>•</span>
                    <span>Evidence: <span className="text-on-surface">{approval.evidenceCount} items</span></span>
                    <span>•</span>
                    <span>Tier: <span className="text-on-surface">{approval.authorizationTier}</span></span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {approval.status === "pending" ? (
                    <ApprovalActions approvalId={approval.id} />
                  ) : (
                    <span className="text-body-sm text-on-surface-variant">
                      {approval.status === "approved" ? "✓ Approved" : "✗ Rejected"}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {approvals.length === 0 && (
          <p className="text-body-sm text-on-surface-variant">No pending approvals.</p>
        )}
      </div>
    </PageShell>
  );
}
