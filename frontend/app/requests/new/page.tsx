// OPSpilot - frontend/app/requests/new/page.tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { requestService } from "@/services/requestService";

const SUGGESTED_ACTIONS = [
  "Sarah needs Friday off. Check whether she can take the day and handle the request.",
  "Reassign the inventory audit task to David Chen.",
  "Upload the quarterly compliance report.",
  "Check if Marcus has enough PTO for a 2-week vacation.",
];

export default function NewRequestPage() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!input.trim()) return;
    setIsSubmitting(true);
    try {
      const request = await requestService.createRequest(input);
      router.push(`/runs/${request.id}`);
    } catch {
      setIsSubmitting(false);
    }
  };

  return (
    <PageShell title="New Request">
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="bg-[#141415] border border-[#262626] rounded-xl p-6">
          <label className="block font-label-caps text-label-caps text-on-surface-variant mb-3">Describe your request</label>
          <textarea
            className="w-full h-32 bg-[#0A0A0B] border border-[#262626] rounded-lg p-4 text-body-md text-on-surface placeholder:text-on-surface-variant focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] outline-none transition-all resize-none"
            placeholder="Describe what you need in plain language..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />

          <div className="mt-4">
            <p className="font-label-caps text-label-caps text-on-surface-variant mb-2">Suggested actions</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_ACTIONS.map((action) => (
                <button
                  key={action}
                  onClick={() => setInput(action)}
                  className="px-3 py-1.5 bg-surface-container border border-[#262626] rounded-full text-body-sm text-on-surface-variant hover:border-primary hover:text-primary transition-colors"
                >
                  {action.length > 50 ? action.slice(0, 50) + "..." : action}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 flex justify-end">
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || isSubmitting}
              className="px-6 py-2 bg-primary text-on-primary rounded-lg font-medium hover:bg-opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? "Submitting..." : "Submit Request"}
            </button>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
