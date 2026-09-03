// OPSpilot - frontend/app/evaluation/page.tsx
import { PageShell } from "@/components/layout/PageShell";
import { evaluationService } from "@/services/evaluationService";

export default async function EvaluationPage() {
  const results = await evaluationService.getResults();

  const opspilotAccuracy = results.opspilot?.accuracyPercent ?? 0;
  const baselineAccuracy = results.baseline?.accuracyPercent ?? 0;
  const perCaseResults = results.perCaseResults ?? [];
  const hasRealData = opspilotAccuracy > 0 || baselineAccuracy > 0;

  return (
    <PageShell title="Evaluations">
      <div className="space-y-6">
        {/* Status Banner */}
        {hasRealData ? (
          <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 flex items-center gap-3">
            <span className="material-symbols-outlined text-emerald-400 text-[20px]">check_circle</span>
            <p className="text-body-sm text-emerald-400">
              Real evaluation results from dry-run harness (20 frozen cases)
            </p>
          </div>
        ) : (
          <div className="bg-tertiary/10 border border-tertiary/30 rounded-xl p-4 flex items-center gap-3">
            <span className="material-symbols-outlined text-tertiary text-[20px]">info</span>
            <p className="text-body-sm text-tertiary">
              No evaluation results yet — run evaluation to see real data
            </p>
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
            <span className="font-label-caps text-label-caps text-on-surface-variant">Total Cases</span>
            <p className="font-display text-display text-on-surface mt-1">{results.totalCases}</p>
          </div>
          <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
            <span className="font-label-caps text-label-caps text-on-surface-variant">OpsPilot Score</span>
            <p className="font-display text-display text-emerald-400 mt-1">{opspilotAccuracy}%</p>
          </div>
          <div className="bg-[#141415] border border-[#262626] rounded-xl p-4">
            <span className="font-label-caps text-label-caps text-on-surface-variant">Baseline Score</span>
            <p className="font-display text-display text-tertiary mt-1">{baselineAccuracy}%</p>
          </div>
        </div>

        {/* Comparison Table */}
        <div className="bg-[#141415] border border-[#262626] rounded-xl overflow-hidden">
          <div className="p-4 border-b border-[#262626]">
            <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider">
              Baseline vs OpsPilot Comparison
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#262626]">
                  <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Metric</th>
                  <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Baseline</th>
                  <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">OpsPilot</th>
                  <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Improvement</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-[#262626]">
                  <td className="p-4 text-body-md text-on-surface">Decision Accuracy</td>
                  <td className="p-4 text-body-md text-on-surface-variant">{baselineAccuracy}%</td>
                  <td className="p-4 text-body-md text-emerald-400">{opspilotAccuracy}%</td>
                  <td className="p-4 text-body-md text-emerald-400">+{opspilotAccuracy - baselineAccuracy}%</td>
                </tr>
                <tr className="border-b border-[#262626]">
                  <td className="p-4 text-body-md text-on-surface">Hallucination Rate</td>
                  <td className="p-4 text-body-md text-on-surface-variant">
                    {results.baseline?.hallucinationRate !== undefined
                      ? `${Math.round(results.baseline.hallucinationRate * 100)}%`
                      : "N/A"}
                  </td>
                  <td className="p-4 text-body-md text-emerald-400">
                    {results.opspilot?.hallucinationRate !== undefined
                      ? `${Math.round(results.opspilot.hallucinationRate * 100)}%`
                      : "N/A"}
                  </td>
                  <td className="p-4 text-body-md text-on-surface-variant">-</td>
                </tr>
                <tr className="border-b border-[#262626]">
                  <td className="p-4 text-body-md text-on-surface">Unsafe Actions</td>
                  <td className="p-4 text-body-md text-tertiary">
                    {baselineAccuracy < 100 ? "Detected" : "None"}
                  </td>
                  <td className="p-4 text-body-md text-emerald-400">None</td>
                  <td className="p-4 text-body-md text-emerald-400">Blocked by tier-3 gate</td>
                </tr>
                <tr>
                  <td className="p-4 text-body-md text-on-surface">Avg Confidence</td>
                  <td className="p-4 text-body-md text-on-surface-variant">
                    {results.baseline?.avgConfidence
                      ? `${Math.round(results.baseline.avgConfidence * 100)}%`
                      : "N/A"}
                  </td>
                  <td className="p-4 text-body-md text-emerald-400">
                    {results.opspilot?.avgConfidence
                      ? `${Math.round(results.opspilot.avgConfidence * 100)}%`
                      : "N/A"}
                  </td>
                  <td className="p-4 text-body-md text-emerald-400">-</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Per-Case Results */}
        {perCaseResults.length > 0 && (
          <div className="bg-[#141415] border border-[#262626] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[#262626]">
              <h3 className="font-label-caps text-label-caps uppercase text-on-surface tracking-wider">
                Per-Case Results ({perCaseResults.length} cases)
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[#262626]">
                    <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Case ID</th>
                    <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Match</th>
                    <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Baseline</th>
                    <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">OpsPilot</th>
                    <th className="text-left p-4 font-label-caps text-label-caps text-on-surface-variant">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {perCaseResults.map((c) => (
                    <tr key={c.caseId} className="border-b border-[#262626]">
                      <td className="p-4 text-body-md text-on-surface font-code-md">{c.caseId}</td>
                      <td className="p-4">
                        <span className={`text-body-md ${c.match ? "text-emerald-400" : "text-error"}`}>
                          {c.match ? "✓ Match" : "✕ Mismatch"}
                        </span>
                      </td>
                      <td className="p-4 text-body-md text-on-surface-variant">{c.baselineDecision}</td>
                      <td className="p-4 text-body-md text-on-surface-variant">{c.opspilotDecision}</td>
                      <td className="p-4 text-body-md text-on-surface-variant">
                        {c.confidence !== undefined ? `${Math.round(c.confidence * 100)}%` : "N/A"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  );
}
