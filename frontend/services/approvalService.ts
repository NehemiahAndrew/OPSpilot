// OPSpilot - frontend/services/approvalService.ts
import type { ApprovalRecord } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface ApprovalServiceInterface {
  getApprovals(status?: string): Promise<ApprovalRecord[]>;
  getApproval(id: string): Promise<ApprovalRecord>;
  approveRequest(id: string, notes: string): Promise<void>;
  rejectRequest(id: string, notes: string): Promise<void>;
}

interface ApprovalItem {
  id: string;
  request_id?: string | null;
  run_id?: string | null;
  approval_reason?: string | null;
  authorization_tier?: number;
  risk_level?: string;
  status?: string;
  decision_id?: string | null;
  employee_id?: string | null;
  employee_name?: string | null;
  request_type?: string | null;
  created_at?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  decision?: Record<string, unknown> | null;
  constitutional_check?: Record<string, unknown> | null;
  evidence_manifest?: Record<string, unknown> | null;
  trajectory?: Array<Record<string, unknown>>;
}

const riskLevelFromTier = (tier?: number): ApprovalRecord["riskLevel"] => {
  if (tier === 3) return "high";
  if (tier === 2) return "medium";
  return "low";
};

const toTitle = (requestType?: string | null): string => {
  if (!requestType) return "Approval Required";
  return `${requestType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())} Request`;
};

function mapApproval(item: ApprovalItem): ApprovalRecord {
  const decision = (item.decision ?? {}) as {
    decision_type?: string;
    confidence?: number;
  };
  const decisionType = decision.decision_type ?? "escalate";
  const recommendation: ApprovalRecord["recommendation"] =
    decisionType === "approve" || decisionType === "reject"
      ? decisionType
      : "escalate";

  const decisionConfidence = decision.confidence ?? 0;
  const evidenceCount = Array.isArray(item.evidence_manifest)
    ? item.evidence_manifest.length
    : Array.isArray((item.evidence_manifest ?? {})["items"])
    ? ((item.evidence_manifest as { items: unknown[] })["items"] as unknown[]).length
    : 0;

  const tier = item.authorization_tier ?? 1;

  return {
    id: item.id,
    requestId: item.request_id ?? "",
    runId: item.run_id ?? null,
    employeeName: item.employee_name ?? "Unknown Employee",
    employeeId: item.employee_id ?? null,
    requestType: item.request_type ?? "other",
    requestTitle: toTitle(item.request_type),
    description: item.approval_reason ?? "",
    recommendation,
    authorizationTier: tier,
    riskLevel: (item.risk_level as ApprovalRecord["riskLevel"]) ?? riskLevelFromTier(tier),
    confidencePercent: Math.round(decisionConfidence * 100),
    confidence: decisionConfidence,
    evidenceCount,
    blockedReason: null,
    constitutionalCheck: {
      passed: Boolean(
        (item.constitutional_check ?? {})["passed"] !== false &&
          (item.constitutional_check ?? {})["passed"] !== undefined
      ),
      violations: Array.isArray((item.constitutional_check ?? {})["violations"])
        ? ((item.constitutional_check ?? {})["violations"] as string[])
        : [],
    },
    authorizationResult: {
      approved: decisionType === "approve",
      tier,
      conditions: [],
    },
    status: (item.status as ApprovalRecord["status"]) ?? "pending",
    createdAt: item.created_at ?? new Date().toISOString(),
    notes: item.review_notes ?? undefined,
    decidedAt: item.reviewed_at ?? undefined,
  };
}

// ---------------------------------------------------------------------------
// Mock approval data — used when the backend (PostgreSQL / Supabase) is not
// reachable, so the interface renders during local development BEFORE the
// database connection and LLM API key are wired up (see docs/REPRODUCTION.md,
// "Quick Start (No Database)"). Once the backend is online,
// `ApiApprovalService` transparently serves real data instead.
// ---------------------------------------------------------------------------
const MOCK_APPROVALS: ApprovalRecord[] = [
  {
    id: "APPROVAL-001",
    requestId: "REQ-1049",
    runId: "RUN-82A92",
    employeeName: "Sarah Mitchell",
    employeeId: "emp_102",
    requestType: "leave_request",
    requestTitle: "Leave Request Review",
    description: "Sarah Mitchell requests Friday off for a family event. Coverage on the requested date drops to minimum staffing.",
    recommendation: "escalate",
    actionType: "escalate",
    authorizationTier: 2,
    riskLevel: "medium",
    verificationScore: { passed: 5, total: 6 },
    confidencePercent: 89,
    confidence: 0.89,
    evidenceCount: 6,
    flagReason: "Team coverage drops to minimum on requested date",
    blockedReason: null,
    constitutionalCheck: { passed: true, violations: [] },
    authorizationResult: { approved: false, tier: 2, conditions: ["Confirm coverage plan"] },
    status: "pending",
    createdAt: "2024-01-15T15:00:00Z",
  },
  {
    id: "APPROVAL-002",
    requestId: "INV-882",
    runId: "RUN-82A90",
    employeeName: "Finance Team",
    requestType: "other",
    requestTitle: "Invoice Approval",
    description: "Cloud provider invoice ($2,384.50) awaits authorization above the $1,000 auto-approval threshold.",
    recommendation: "approve",
    authorizationTier: 2,
    riskLevel: "medium",
    verificationScore: { passed: 4, total: 5 },
    confidencePercent: 82,
    confidence: 0.82,
    evidenceCount: 5,
    constitutionalCheck: { passed: true, violations: [] },
    authorizationResult: { approved: false, tier: 2, conditions: [] },
    status: "pending",
    createdAt: "2024-01-15T14:45:00Z",
  },
  {
    id: "APPROVAL-003",
    requestId: "REQ-1046",
    runId: "RUN-82A94",
    employeeName: "Compliance Team",
    requestType: "other",
    requestTitle: "Compliance Report Upload",
    description: "Upload quarterly compliance report — flagged as high risk (tier 3).",
    recommendation: "escalate",
    authorizationTier: 3,
    riskLevel: "high",
    verificationScore: { passed: 0, total: 5 },
    confidencePercent: 45,
    confidence: 0.45,
    evidenceCount: 7,
    constitutionalCheck: { passed: false, violations: ["CHECK-001: insufficient evidence", "CHECK-004: balance conflict"] },
    authorizationResult: { approved: false, tier: 3, conditions: [] },
    status: "escalated",
    createdAt: "2024-01-15T14:20:00Z",
  },
  {
    id: "APPROVAL-004",
    requestId: "REQ-1047",
    runId: "RUN-82A93",
    employeeName: "Inventory Audit Task",
    requestType: "task_reassignment",
    requestTitle: "Task Reassignment",
    description: "Reassign inventory audit to David Chen — reviewed and approved.",
    recommendation: "approve",
    authorizationTier: 1,
    riskLevel: "low",
    verificationScore: { passed: 6, total: 6 },
    confidencePercent: 97,
    confidence: 0.97,
    evidenceCount: 4,
    constitutionalCheck: { passed: true, violations: [] },
    authorizationResult: { approved: true, tier: 1, conditions: [] },
    status: "approved",
    createdAt: "2024-01-15T14:25:00Z",
    decidedAt: "2024-01-15T14:28:00Z",
  },
];

export class MockApprovalService implements ApprovalServiceInterface {
  findById(id: string): ApprovalRecord | undefined {
    return MOCK_APPROVALS.find((a) => a.id === id);
  }
  async getApprovals(_status = "pending"): Promise<ApprovalRecord[]> {
    await new Promise((resolve) => setTimeout(resolve, 200));
    return MOCK_APPROVALS.filter((a) => a.status === "pending");
  }
  async getApproval(id: string): Promise<ApprovalRecord> {
    await new Promise((resolve) => setTimeout(resolve, 200));
    const found = this.findById(id);
    if (!found) throw new Error(`Approval ${id} not found`);
    return found;
  }
  async approveRequest(): Promise<void> {}
  async rejectRequest(): Promise<void> {}
}

export const mockApprovalService = new MockApprovalService();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export class ApiApprovalService implements ApprovalServiceInterface {
    async getApprovals(status = "pending"): Promise<ApprovalRecord[]> {
    try {
      const data = await request<{ approvals: ApprovalItem[] }>(
        `/api/approvals?status=${encodeURIComponent(status)}`
      );
      return (data.approvals ?? []).map(mapApproval);
    } catch {
      // Backend (Supabase / DB) not connected yet — fall back to mock data
      // so the interface stays viewable before wiring is complete.
      return mockApprovalService.getApprovals(status);
    }
  }

    async getApproval(id: string): Promise<ApprovalRecord> {
    try {
      const data = await request<ApprovalItem>(`/api/approvals/${id}`);
      return mapApproval(data);
    } catch {
      // Backend not connected — fall back to mock data.
      const found = mockApprovalService.findById(id);
      if (!found) throw new Error(`Approval ${id} not found`);
      return found;
    }
  }

  async approveRequest(id: string, notes: string): Promise<void> {
    await request(`/api/approvals/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes }),
    });
  }

  async rejectRequest(id: string, notes: string): Promise<void> {
    await request(`/api/approvals/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes }),
    });
  }
}

/**
 * Preview mode toggle. While Supabase + the LLM API key are not yet
 * connected, the frontend uses mock data so the interface renders with
 * representative content (consistent with the other mock services).
 *
 * Set NEXT_PUBLIC_DEMO_MODE=false in frontend/.env.local once the backend
 * is live to read real data from the API.
 */
const __DEMO_MODE = (process.env.NEXT_PUBLIC_DEMO_MODE ?? "true") !== "false";
export const approvalService: ApprovalServiceInterface = __DEMO_MODE
  ? new MockApprovalService()
  : new ApiApprovalService();