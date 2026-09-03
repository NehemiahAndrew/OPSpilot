// OPSpilot - frontend/lib/utils.ts
// Utility helpers — formatting, class merging, date helpers
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { WorkflowStatus, type AuthorizationTier, type RiskLevel, type DecisionType } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTimestamp(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r > 0 ? `${m}m ${r}s` : `${m}m`;
}

export function getWorkflowStatusLabel(status: WorkflowStatus): string {
  const labels: Record<string, string> = {
    [WorkflowStatus.Pending]: "Pending", [WorkflowStatus.Parsed]: "Parsed",
    [WorkflowStatus.GatheringContext]: "Gathering Context", [WorkflowStatus.ManifestReady]: "Manifest Ready",
    [WorkflowStatus.Deciding]: "Deciding", [WorkflowStatus.ConstitutionalCheck]: "Constitutional Check",
    [WorkflowStatus.Authorization]: "Authorization", [WorkflowStatus.AutoExecuting]: "Auto-Executing",
    [WorkflowStatus.AwaitingApproval]: "Awaiting Approval", [WorkflowStatus.Blocked]: "Blocked",
    [WorkflowStatus.Tier3OverrideRequested]: "Tier 3 Override Requested",
    [WorkflowStatus.Executing]: "Executing", [WorkflowStatus.Completed]: "Completed",
    [WorkflowStatus.Aborted]: "Aborted", [WorkflowStatus.Failed]: "Failed",
  };
  return labels[status] ?? status;
}

export function getAuthorizationTierLabel(tier: AuthorizationTier): string { return `Tier ${tier}`; }

export function getRiskColor(risk: RiskLevel): string {
  const map: Record<RiskLevel, string> = {
    low: "text-emerald-400", medium: "text-tertiary", high: "text-tertiary", critical: "text-error",
  };
  return map[risk] ?? "text-on-surface-variant";
}

export function getRiskBadgeColor(risk: RiskLevel): string {
  const map: Record<RiskLevel, string> = {
    low: "bg-emerald-500/10 border-emerald-400/30 text-emerald-400",
    medium: "bg-tertiary/10 border-tertiary/30 text-tertiary",
    high: "bg-tertiary/10 border-tertiary/30 text-tertiary",
    critical: "bg-error/10 border-error/30 text-error",
  };
  return map[risk];
}

export function getDecisionColor(decision: DecisionType): string {
  const map: Record<DecisionType, string> = {
    approve: "text-emerald-400", reject: "text-error",
    escalate: "text-tertiary", information_only: "text-secondary", needs_clarification: "text-tertiary",
  };
  return map[decision];
}

export function calculatePercent(passed: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((passed / total) * 100);
}

export function getStrokeOffset(passed: number, total: number, radius = 7): number {
  const circumference = 2 * Math.PI * radius;
  const percent = calculatePercent(passed, total) / 100;
  return circumference * (1 - percent);
}

export function getCircumference(radius = 7): number {
  return 2 * Math.PI * radius;
}

export function getTimeBasedGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export const MATERIAL_ICONS = {
  Dashboard: "dashboard", Requests: "list_alt", AgentRuns: "smart_toy",
  Approvals: "verified_user", Evidence: "fact_check", Evaluations: "analytics",
  Improvement: "trending_up", AuditLog: "history", SystemStatus: "cloud_done",
  Search: "search", Notifications: "notifications", Settings: "settings", Menu: "menu",
  Warning: "warning", Shield: "shield", Timeline: "timeline", Error: "error", Check: "check",
  Psychology: "psychology", Terminal: "terminal", SendSpark: "send_spark",
  FolderOpen: "folder_open", Route: "route", StopCircle: "stop_circle", Play: "play_arrow",
  Memory: "memory", Rocket: "rocket_launch", Person: "person", ShieldPerson: "shield_person",
  CheckCircle: "check_circle", ExpandMore: "expand_more", ExpandLess: "expand_less",
  Article: "article", PriorityHigh: "priority_high", Code: "code", Login: "login",
  ZoomIn: "zoom_in", ZoomOut: "zoom_out", FitScreen: "fit_screen", VpnKey: "vpn_key",
  Api: "api", Database: "database", Domain: "domain", Info: "info", Policy: "policy",
  CalendarMonth: "calendar_month", Rule: "rule", Report: "report", Visibility: "visibility",
  PersonCancel: "person_cancel", ThumbUp: "thumb_up", PersonRemove: "person_remove",
  Inventory2: "inventory_2", LockOpen: "lock_open", Gavel: "gavel", ChevronRight: "chevron_right",
  HorizontalRule: "horizontal_rule", TrendingDown: "trending_down", Lightbulb: "lightbulb",
  ArrowUpward: "arrow_upward",
} as const;
