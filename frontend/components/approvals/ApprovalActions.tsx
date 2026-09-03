// OPSpilot - frontend/components/approvals/ApprovalActions.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { approvalService } from "@/services/approvalService";

export function ApprovalActions({ approvalId }: { approvalId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const review = async (action: "approve" | "reject") => {
    setError(null);
    const notes = window.prompt(
      action === "approve"
        ? `Add a note for approving ${approvalId}:`
        : `Reason for rejecting ${approvalId}:`
    );
    if (notes === null) return;
    setPending(action);
    try {
      if (action === "approve") {
        await approvalService.approveRequest(approvalId, notes);
      } else {
        await approvalService.rejectRequest(approvalId, notes);
      }
      router.refresh();
      router.push("/approvals");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => review("approve")}
        disabled={pending !== null}
        className="px-3 py-1.5 bg-emerald-500/10 border border-emerald-400/30 text-emerald-400 rounded text-body-sm font-medium hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
      >
        {pending === "approve" ? "Approving…" : "Approve"}
      </button>
      <button
        onClick={() => review("reject")}
        disabled={pending !== null}
        className="px-3 py-1.5 bg-error/10 border border-error/30 text-error rounded text-body-sm font-medium hover:bg-error/20 transition-colors disabled:opacity-50"
      >
        {pending === "reject" ? "Rejecting…" : "Reject"}
      </button>
      {error && <span className="text-body-sm text-error">{error}</span>}
    </div>
  );
}