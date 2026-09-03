// OPSpilot - frontend/services/requestService.ts
// MOCK — replace with real API calls in Prompt 8+
// Interface + mock implementation for agent request operations
import type { AgentRequest } from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface RequestServiceInterface {
  getRequests(): Promise<AgentRequest[]>;
  getRequest(id: string): Promise<AgentRequest>;
  createRequest(input: string): Promise<AgentRequest>;
}

// MOCK data — replace with real API call in Prompt 8+
const MOCK_REQUESTS: AgentRequest[] = [
  {
    id: "REQ-1048",
    businessId: "biz_001",
    submittedByUserId: "usr_001",
    rawInput: "Sarah needs Friday off. Check whether she can take the day and handle the request.",
    structuredRequest: {
      requestType: "leave_request",
      intent: "FAMILY_EVENT",
      employeeHint: "Sarah Mitchell",
      employeeId: "emp_102",
      dates: ["NEXT_FRIDAY"],
      claims: ["Family event"],
      confidence: 0.95,
    },
    requestType: "leave_request",
    employeeId: "emp_102",
    employeeName: "Sarah Mitchell",
    title: "Time Off Request",
    description: "Sarah needs Friday off for a family event.",
    status: "completed",
    riskLevel: "low",
    verificationScore: { passed: 5, total: 6 },
    createdAt: "2024-01-15T14:30:00Z",
    resolvedAt: "2024-01-15T14:33:00Z",
  },
  {
    id: "REQ-1049",
    businessId: "biz_001",
    submittedByUserId: "usr_001",
    rawInput: "Sarah needs Friday off. Check whether she can take the day and handle the request.",
    structuredRequest: {
      requestType: "leave_request",
      intent: "FAMILY_EVENT",
      employeeHint: "Sarah Mitchell",
      employeeId: "emp_102",
      dates: ["NEXT_FRIDAY"],
      claims: ["Family event"],
      confidence: 0.92,
    },
    requestType: "leave_request",
    employeeId: "emp_102",
    employeeName: "Sarah Mitchell",
    title: "Leave Request Review",
    description: "Sarah needs Friday off for a family event.",
    status: "running",
    riskLevel: "medium",
    verificationScore: { passed: 5, total: 6 },
    createdAt: "2024-01-15T15:00:00Z",
  },
  {
    id: "REQ-1047",
    businessId: "biz_001",
    submittedByUserId: "usr_002",
    rawInput: "Please reassign the inventory audit to David Chen.",
    structuredRequest: {
      requestType: "task_reassignment",
      intent: "TASK_REASSIGNMENT",
      employeeHint: "David Chen",
      confidence: 0.88,
    },
    requestType: "task_reassignment",
    employeeName: "Inventory Audit Task",
    title: "Task Reassignment",
    description: "Reassign inventory audit to David Chen.",
    status: "completed",
    riskLevel: "low",
    verificationScore: { passed: 6, total: 6 },
    createdAt: "2024-01-15T14:25:00Z",
    resolvedAt: "2024-01-15T14:28:00Z",
  },
  {
    id: "REQ-1046",
    businessId: "biz_001",
    submittedByUserId: "usr_003",
    rawInput: "Upload the quarterly compliance report.",
    structuredRequest: {
      requestType: "other",
      intent: "DOCUMENT_UPLOAD",
      confidence: 0.75,
    },
    requestType: "other",
    title: "Compliance Report Upload",
    description: "Upload quarterly compliance report.",
    status: "failed",
    riskLevel: "high",
    verificationScore: { passed: 0, total: 5 },
    createdAt: "2024-01-15T14:20:00Z",
  },
  {
    id: "INV-882",
    businessId: "biz_001",
    submittedByUserId: "usr_004",
    rawInput: "Approve the cloud provider invoice.",
    structuredRequest: {
      requestType: "other",
      intent: "INVOICE_APPROVAL",
      confidence: 0.82,
    },
    requestType: "other",
    title: "Cloud Provider Invoice Approval",
    description: "Approve cloud provider invoice.",
    status: "running",
    riskLevel: "medium",
    verificationScore: { passed: 4, total: 5 },
    createdAt: "2024-01-15T14:45:00Z",
  },
];

// MOCK delay — replace with real fetch in Prompt 8+
const MOCK_DELAY = 200;

export class MockRequestService implements RequestServiceInterface {
  async getRequests(): Promise<AgentRequest[]> {
    // MOCK — replace with real API call in Prompt 8+
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY));
    return MOCK_REQUESTS;
  }

  async getRequest(id: string): Promise<AgentRequest> {
    // MOCK — replace with real API call in Prompt 8+
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY));
    const request = MOCK_REQUESTS.find((r) => r.id === id);
    if (!request) throw new Error(`Request ${id} not found`);
    return request;
  }

  async createRequest(input: string): Promise<AgentRequest> {
    const res = await fetch(`${API_BASE}/api/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_input: input }),
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`Failed to create request (HTTP ${res.status})`);
    }
    const data = (await res.json()) as { request_id: string; run_id: string };
    return {
      id: data.run_id,
      businessId: "biz_001",
      submittedByUserId: "USER-001",
      rawInput: input,
      structuredRequest: { requestType: "other", intent: "unknown", confidence: 0 },
      requestType: "other",
      title: "New Request",
      description: input,
      status: "pending",
      riskLevel: "low",
      verificationScore: { passed: 0, total: 0 },
      createdAt: new Date().toISOString(),
    };
  }
}

export const requestService = new MockRequestService();
