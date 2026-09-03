// OPSpilot - frontend/app/dashboard/Metrics.tsx
export function DashboardMetrics({ requests, completed, awaiting, escalated }: {
  requests: number; completed: number; awaiting: number; escalated: number;
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      <MetricCard label="Requests Processed" value={requests.toString()} subtitle="+12%" subtitleColor="text-emerald-400" />
      <MetricCard label="Verified Resolutions" value={completed.toString()} subtitle="75% yield" subtitleColor="text-on-surface-variant" />
      <MetricCard label="Awaiting Approval" value={awaiting.toString()} highlight />
      <MetricCard label="Escalated" value={escalated.toString()} variant="error" />
      <MetricCard label="Avg Resolution Time" value="2m 14s" subtitle="-15s" subtitleColor="text-emerald-400" className="col-span-2 md:col-span-1" />
    </div>
  );
}

function MetricCard({ label, value, subtitle, subtitleColor = "text-on-surface-variant", highlight, variant, className }: {
  label: string; value: string; subtitle?: string; subtitleColor?: string;
  highlight?: boolean; variant?: "error"; className?: string;
}) {
  return (
    <div className={`bg-[#141415] border border-[#262626] rounded-xl p-4 flex flex-col justify-between relative overflow-hidden ${className ?? ""}`}>
      {highlight && <div className="absolute inset-0 bg-secondary-container/10"></div>}
      {variant === "error" && <div className="absolute inset-0 bg-error/5"></div>}
      <span className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider mb-2 block relative z-10">{label}</span>
      <div className="flex items-baseline gap-2 relative z-10">
        <span className={`font-display text-display ${variant === "error" ? "text-error" : highlight ? "text-primary" : "text-on-surface"}`}>{value}</span>
        {subtitle && <span className={`text-body-sm ${subtitleColor}`}>{subtitle}</span>}
      </div>
    </div>
  );
}