// OPSpilot - frontend/services/agentRunService.ts
// MOCK — replace with real API calls in Prompt 8+
// Interface + mock implementation for agent run operations
import type { AgentRun, AgentStep, ToolCall, SSEEvent } from "@/types";

export interface AgentRunServiceInterface {
  getRuns(): Promise<AgentRun[]>;
  getRun(id: string): Promise<AgentRun>;
  getRunSteps(runId: string): Promise<AgentStep[]>;
  getRunToolCalls(runId: string): Promise<ToolCall[]>;
}

// MOCK data — replace with real API call in Prompt 8+
const MOCK_RUNS: AgentRun[] = [
  {
    id: "RUN-82A91", requestId: "REQ-1048", businessId: "biz_001",
    startedAt: "2024-01-15T14:31:59Z", completedAt: "2024-01-15T14:38:15Z",
    status: "completed",
    finalDecision: { decisionType: "approve", authorizationTier: 2, needsApproval: true },
    authorizationTier: 2, confidence: 0.89, totalToolCalls: 5, totalDurationMs: 49000,
    agentsInvolved: ["ParserAgent", "ContextAgent", "DecisionAgent"],
    llmTokensUsed: 4523, llmCostUsd: 0.042,
  },
  {
    id: "RUN-82A92", requestId: "REQ-1049", businessId: "biz_001",
    startedAt: "2024-01-15T15:00:00Z", status: "running",
    authorizationTier: 2, confidence: 0.85, totalToolCalls: 3, totalDurationMs: 12000,
    agentsInvolved: ["ParserAgent", "ContextAgent", "DecisionAgent"],
    llmTokensUsed: 3800, llmCostUsd: 0.035,
    currentAgent: "DecisionAgent", elapsedMs: 12000,
  },
  {
    id: "RUN-82A93", requestId: "REQ-1047", businessId: "biz_001",
    startedAt: "2024-01-15T14:25:00Z", completedAt: "2024-01-15T14:28:30Z",
    status: "completed",
    finalDecision: { decisionType: "approve", authorizationTier: 1, needsApproval: false },
    authorizationTier: 1, confidence: 0.97, totalToolCalls: 2, totalDurationMs: 210000,
    agentsInvolved: ["ParserAgent", "ContextAgent", "DecisionAgent"],
    llmTokensUsed: 2980, llmCostUsd: 0.028,
  },
  {
    id: "RUN-82A94", requestId: "REQ-1046", businessId: "biz_001",
    startedAt: "2024-01-15T14:20:00Z", completedAt: "2024-01-15T14:32:00Z",
    status: "failed",
    finalDecision: { decisionType: "escalate", authorizationTier: 3, needsApproval: true },
    authorizationTier: 3, confidence: 0.45, totalToolCalls: 7, totalDurationMs: 720000,
    agentsInvolved: ["ParserAgent", "ContextAgent", "DecisionAgent"],
    llmTokensUsed: 6120, llmCostUsd: 0.065,
  },
];

// MOCK steps for RUN-82A91
const MOCK_STEPS: Record<string, AgentStep[]> = {
  "RUN-82A91": [
    { id: "step-001", runId: "RUN-82A91", stepNumber: 1, agentName: "ParserAgent",
      input: { raw: "Sarah needs Friday off..." },
      output: { type: "leave_request", intent: "FAMILY_EVENT", confidence: 0.95 },
      status: "completed", startedAt: "2024-01-15T14:31:59Z", durationMs: 1200 },
    { id: "step-002", runId: "RUN-82A91", stepNumber: 2, agentName: "ContextAgent",
      input: { request: "Leave for Sarah Mitchell on Friday" },
      output: { employee: "Sarah Mitchell", balance: 6, conflicts: 1 },
      status: "completed", startedAt: "2024-01-15T14:32:00Z", durationMs: 4000 },
    { id: "step-003", runId: "RUN-82A91", stepNumber: 3, agentName: "DecisionAgent",
      input: { evidence: "manifest ready" },
      output: { decision: "approve_with_conditions", reason: "Coverage gap on Friday" },
      status: "running", startedAt: "2024-01-15T14:32:04Z", durationMs: 5000 },
  ],
  "RUN-82A92": [
    { id: "step-001", runId: "RUN-82A92", stepNumber: 1, agentName: "ParserAgent",
      input: { raw: "Sarah needs Friday off..." },
      output: { type: "leave_request", intent: "FAMILY_EVENT", confidence: 0.92 },
      status: "completed", startedAt: "2024-01-15T15:00:00Z", durationMs: 800 },
    { id: "step-002", runId: "RUN-82A92", stepNumber: 2, agentName: "ContextAgent",
      input: { request: "Leave for Sarah Mitchell on Friday" },
      output: { employee: "Sarah Mitchell", balance: 6, conflicts: 1 },
      status: "running", startedAt: "2024-01-15T15:00:02Z", durationMs: 0 },
  ],
};

const MOCK_TOOL_CALLS: Record<string, ToolCall[]> = {
  "RUN-82A91": [
    { id: "tc-001", runId: "RUN-82A91", stepId: "step-001", toolName: "parse_request",
      arguments: { text: "Sarah needs Friday off..." },
      result: { type: "leave_request", confidence: 0.95 },
      success: true, durationMs: 1200, calledAt: "2024-01-15T14:31:59Z" },
    { id: "tc-002", runId: "RUN-82A91", stepId: "step-002", toolName: "get_leave_balance",
      arguments: { userId: "emp_102" },
      result: { status: "success", balance: 6, unit: "days" },
      success: true, durationMs: 85, calledAt: "2024-01-15T14:32:01Z" },
    { id: "tc-003", runId: "RUN-82A91", stepId: "step-002", toolName: "get_team_calendar",
      arguments: { team: "Engineering", date: "Next Friday" },
      result: { conflicts: 1, details: "John Doe also on leave." },
      success: true, durationMs: 215, calledAt: "2024-01-15T14:32:01Z" },
    { id: "tc-004", runId: "RUN-82A91", stepId: "step-002", toolName: "check_policy_db",
      arguments: { category: "leave_policy" },
      result: { rules: { notice_required: 3 } },
      success: true, durationMs: 340, calledAt: "2024-01-15T14:32:03Z" },
    { id: "tc-005", runId: "RUN-82A91", stepId: "step-002", toolName: "fetch_calendar",
      arguments: {},
      result: { schedule: [] },
      success: true, durationMs: 85, calledAt: "2024-01-15T14:32:03Z" },
  ],
};

const MOCK_DELAY = 200;

export class MockAgentRunService implements AgentRunServiceInterface {
  async getRuns(): Promise<AgentRun[]> {
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY));
    return MOCK_RUNS;
  }
  async getRun(id: string): Promise<AgentRun> {
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY));
    const run = MOCK_RUNS.find((r) => r.id === id);
    if (!run) throw new Error(`Run ${id} not found`);
    return run;
  }
  async getRunSteps(runId: string): Promise<AgentStep[]> {
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY));
    return MOCK_STEPS[runId] ?? [];
  }
  async getRunToolCalls(runId: string): Promise<ToolCall[]> {
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY));
    return MOCK_TOOL_CALLS[runId] ?? [];
  }
}

export const agentRunService = new MockAgentRunService();
