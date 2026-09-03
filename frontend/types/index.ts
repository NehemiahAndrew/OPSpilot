// OPSpilot - frontend/types/index.ts
// Shared TypeScript types for the OPSpilot frontend application.

export enum WorkflowStatus {
  Pending = "pending",
  Parsed = "parsed",
  GatheringContext = "gathering_context",
  ManifestReady = "manifest_ready",
  Deciding = "deciding",
  ConstitutionalCheck = "constitutional_check",
  Authorization = "authorization",
  AutoExecuting = "auto_executing",
  AwaitingApproval = "awaiting_approval",
  Blocked = "blocked",
  Tier3OverrideRequested = "tier3_override_requested",
  Executing = "executing",
  Completed = "completed",
  Aborted = "aborted",
  Failed = "failed",
  Running = "running",
  Escalated = "escalated",
}

export type AuthorizationTier = 1 | 2 | 3;

export type DecisionType =
  | "approve"
  | "reject"
  | "escalate"
  | "information_only"
  | "needs_clarification";

export type RiskLevel = "low" | "medium" | "high" | "critical";

export type ApprovalStatus = "pending" | "approved" | "rejected" | "escalated";

export type CaseDifficulty = "easy" | "medium" | "hard" | "simple" | "edge_case" | "adversarial";

export type RequestType =
  | "leave_request"
  | "policy_query"
  | "task_reassignment"
  | "employee_status"
  | "schedule_lookup"
  | "disciplinary_action"
  | "suspension"
  | "other";

export type EvidenceType =
  | "employee_record"
  | "leave_balance"
  | "company_policy"
  | "schedule"
  | "team_coverage"
  | "task_record"
  | "attendance"
  | "historical_precedent"
  | string;

export interface Employee {
  id: string;
  employeeId: string;
  name: string;
  role: string;
  department: string;
  status: "active" | "inactive" | "on_leave";
  managerId?: string;
  hireDate: string;
  avatarUrl?: string;
}

export interface Department {
  id: string;
  name: string;
  minimumCoverageHeadcount: number;
}

export interface LeaveBalance {
  id: string;
  employeeId: string;
  leaveType: "annual" | "sick" | "unpaid" | "personal";
  availableDays: number;
  usedDays: number;
  year: number;
  updatedAt: string;
}

export interface Schedule {
  id: string;
  employeeId: string;
  shiftDate: string;
  shiftStart: string;
  shiftEnd: string;
  shiftType: "primary" | "backup" | "off";
}

export interface Policy {
  id: string;
  businessId: string;
  category: string;
  title: string;
  content: string;
  rules: Record<string, unknown>;
  version: number;
  isActive: boolean;
  departmentId?: string;
  createdAt: string;
}

export interface Task {
  id: string;
  businessId: string;
  assignedTo: string;
  title: string;
  description: string;
  priority: "low" | "medium" | "high" | "critical";
  dueDate: string;
  status: "pending" | "in_progress" | "blocked" | "completed";
  createdAt: string;
}

export interface AgentRequest {
  id: string;
  businessId?: string;
  submittedByUserId?: string;
  rawInput?: string;
  structuredRequest: {
    requestType: RequestType;
    intent: string;
    employeeHint?: string;
    employeeId?: string | null;
    dates?: string[];
    claims?: string[];
    confidence: number;
  };
  requestType: RequestType;
  employeeId?: string;
  employeeName?: string;
  title?: string;
  description?: string;
  status: "pending" | "in_progress" | "awaiting_approval" | "approved" | "rejected" | "escalated" | "completed" | "failed" | "running";
  riskLevel?: RiskLevel;
  verificationScore?: { passed: number; total: number };
  createdAt: string;
  resolvedAt?: string;
}

export interface AgentRun {
  id: string;
  requestId: string;
  businessId?: string;
  startedAt: string;
  completedAt?: string;
  status: WorkflowStatus | "pending" | "running" | "completed" | "failed" | "awaiting_approval" | "escalated";
  currentStage?: string;
  currentAgent?: string;
  agentsInvolved?: string[];
  finalDecision?: DecisionType | { decisionType: DecisionType | string; authorizationTier?: AuthorizationTier | number; needsApproval?: boolean };
  decisionType?: DecisionType | string;
  authorizationTier?: AuthorizationTier | number;
  needsApproval?: boolean;
  confidence?: number;
  totalToolCalls: number;
  totalDurationMs?: number;
  elapsedMs?: number;
  llmTokensUsed?: number;
  llmCostUsd?: number;
  error?: string;
}

export interface AgentStep {
  id: string;
  runId: string;
  stepNumber: number;
  agentName: string;
  agentRole?: "context_assembly" | "decision" | "orchestrator";
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  inputPayload?: Record<string, unknown>;
  outputPayload?: Record<string, unknown>;
  status: "pending" | "running" | "completed" | "failed";
  retryCount?: number;
  retryReason?: string;
  startedAt: string;
  completedAt?: string;
  durationMs?: number;
  error?: string;
}

export interface ToolCall {
  id: string;
  runId?: string | null;
  stepId?: string;
  toolName: string;
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  success?: boolean;
  status?: "success" | "error";
  errorMessage?: string;
  error?: string;
  durationMs: number;
  calledAt?: string;
}

export interface AgentLogLine {
  timestamp: string;
  source: string;
  message: string;
  level: "info" | "warn" | "error" | "success";
  iconType?: "error" | "default";
  referenceId?: string;
  className?: string;
}

export interface EvidenceItem {
  id: string;
  runId?: string;
  toolCallId?: string;
  evidenceType?: EvidenceType | string;
  type?: EvidenceType | string;
  evidenceKey?: string;
  title?: string;
  description?: string;
  source?: string;
  content?: Record<string, unknown>;
  queryParameters?: Record<string, unknown>;
  status?: "pass" | "warning" | "fail";
  riskLevel?: RiskLevel;
  verificationScore?: { passed: number; total: number };
  evidenceRefs?: string[];
  evidenceIds?: string[];
  toolName?: string;
  toolArgs?: string;
  inputPayload?: Record<string, unknown>;
  outputPayload?: Record<string, unknown> | string;
  sourceSystem?: string;
  payloadHash?: string;
  retrievedAt?: string;
  extractedAt?: string;
  hash?: string;
  usedInDecision?: boolean;
  citedInReason?: boolean;
  isDemo?: boolean;
  expanded?: boolean;
}

export interface EvidenceManifest {
  runId: string;
  requestId: string;
  items: EvidenceItem[];
  totalEvidence: number;
  totalToolCalls: number;
  hashChainRoot: string;
}

export interface ConstitutionalCheckResult {
  policyRef?: string;
  passed: boolean;
  needsReview?: boolean;
  details?: string;
  violations?: string[];
  all_checks?: Array<{
    check_name: string;
    passed: boolean;
    severity: "error" | "warning" | "info";
    detail: string;
  }>;
}

export interface AuthorizationResult {
  approved?: boolean;
  tier: AuthorizationTier | number;
  approvalRequired?: boolean;
  reason?: string;
  blocked?: boolean;
  overrideRequested?: boolean;
  conditions: string[];
}

export interface DecisionRecord {
  id: string;
  runId: string;
  requestId?: string;
  decisionType: DecisionType | string;
  recommendedAction?: string;
  reason: string;
  evidenceRefs?: string[];
  evidenceIds?: string[];
  policyRefs?: string[];
  conflictsIdentified?: string[];
  authorizationTier: AuthorizationTier | number;
  needsApproval?: boolean;
  requires_human_approval?: boolean;
  confidence: number;
  verificationPassed?: boolean;
  verificationFailures?: string[];
  constitutionalCheck?: ConstitutionalCheckResult;
  authorizationResult?: AuthorizationResult;
  createdAt?: string;
  timestamp?: string;
}

export interface PolicyCheck {
  id: string;
  label: string;
  status: "pass" | "fail" | "pending" | "needs_review";
  icon: "check" | "warning" | "close";
  detail?: string;
  isHighlighted?: boolean;
}

export interface ApprovalRecord {
  id: string;
  requestId: string;
  runId?: string | null;
  employeeName: string;
  employeeId?: string | null;
  employeeAvatar?: string;
  requestType?: string;
  requestTitle: string;
  description?: string;
  recommendation: "approve" | "reject" | "needs_clarification" | "escalate" | string;
  actionType?: "approve" | "reject" | "needs_clarification" | "escalate" | string;
  authorizationTier: AuthorizationTier | number;
  riskLevel: RiskLevel;
  riskLabel?: string;
  verificationScore?: { passed: number; total: number };
  confidencePercent?: number;
  confidence?: number;
  evidenceCount: number;
  flagReason?: string;
  proposedAction?: string;
  blockedReason?: string | null;
  blocked?: boolean;
  constitutionalCheck?: ConstitutionalCheckResult;
  authorizationResult?: AuthorizationResult;
  status: ApprovalStatus | "pending" | "approved" | "rejected" | "escalated";
  createdAt: string;
  completedAt?: string;
  decidedAt?: string;
  decidedBy?: string;
  notes?: string;
}

export interface AuditLog {
  id: string;
  businessId: string;
  runId?: string;
  actor: string;
  action: string;
  targetType: string;
  targetId: string;
  riskLevel: RiskLevel;
  authorizationTier: AuthorizationTier;
  approvedBy?: string;
  result: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface EvaluationCase {
  id: string;
  caseNumber?: string;
  title?: string;
  name?: string;
  description?: string;
  category?: string;
  difficulty: CaseDifficulty | "simple" | "medium" | "edge_case" | "adversarial" | string;
  rawInput?: string;
  inputPayload?: Record<string, unknown>;
  expectedDecision?: string;
  expectedDecisionType?: string;
  expectedTier?: AuthorizationTier | number;
  expectedAuthorizationTier?: AuthorizationTier;
  expectedApprovalRequired?: boolean;
  expectedEvidenceKeys?: string[];
  expectedPolicyApplied?: string[];
  tags?: string[];
  isEdgeCase?: boolean;
  adversarial?: boolean;
  notes?: string;
}

export interface PerformanceDimension {
  name: string;
  opspilotScore: number;
  baselineScore: number;
  delta: string;
  deltaColor: "emerald" | "red" | "tertiary";
}

export interface EvaluationMetrics {
  verifiedTaskAccuracy: { opspilot: number; baseline: number; delta: string };
  timeToResolution: string;
  humanTouchpoints: string;
  performanceDimensions: PerformanceDimension[];
  safetyMetrics: {
    unsupportedClaims: { value: number; total: number };
    evidenceGrounding: number;
    unsafeAutonomousActions: { value: number; total: number };
    approvalGateAccuracy: number;
  };
}

export interface EvaluationResult {
  id: string;
  caseId: string;
  decisionCorrect: boolean;
  decisionScore: number;
  evidenceValid: boolean;
  evidenceScore: number;
  policyApplied: boolean;
  policyScore: number;
  authorizationCorrect: boolean;
  authorizationScore: number;
  approvalGateCorrect: boolean;
  approvalGateScore: number;
  weightedScore: number;
  hallucinationDetected: boolean;
  unsafeActionAttempted: boolean;
  resolutionTimeMs: number;
  llmCostUsd: number;
  failureReason?: string;
  evaluatorNotes?: string;
  evaluatedAt: string;
}

export interface EvaluationReport {
  id?: string;
  systemVersion?: string;
  startedAt?: string;
  completedAt?: string;
  generatedAt?: string;
  status?: "pending" | "running" | "completed" | "failed";
  totalCases: number;
  passed?: number;
  failed?: number;
  overallScore?: number;
  metrics?: EvaluationMetrics;
  results?: EvaluationResult[];
  keyFinding?: string;
  opspilot?: {
    systemName?: string;
    totalCases?: number;
    correctDecisions?: number;
    correctTier?: number;
    hallucinationRate?: number;
    avgConfidence?: number;
    passRate?: number;
    accuracyPercent?: number;
    avgResolutionTimeMs?: number;
    escalationRatePercent?: number;
    evidenceQualityPercent?: number;
  };
  baseline?: {
    systemName?: string;
    totalCases?: number;
    correctDecisions?: number;
    correctTier?: number;
    hallucinationRate?: number;
    avgConfidence?: number;
    passRate?: number;
    accuracyPercent?: number;
    avgResolutionTimeMs?: number;
    escalationRatePercent?: number;
    evidenceQualityPercent?: number;
  };
  perCaseResults?: Array<{
    caseId: string;
    category?: string;
    difficulty?: "simple" | "medium" | "edge_case" | "adversarial" | string;
    expectedDecision?: string;
    opspilotDecision: string;
    baselineDecision: string;
    match: boolean;
    confidence?: number;
    executionTimeMs?: number;
  }>;
}

export type WorkflowEventType =
  | "run.created"
  | "run.started"
  | "parsing.started"
  | "parsing.completed"
  | "clarification.needed"
  | "context.started"
  | "tool.calling"
  | "tool.completed"
  | "tool.failed"
  | "evidence.assembled"
  | "decision.started"
  | "decision.completed"
  | "verification.started"
  | "verification.passed"
  | "verification.failed"
  | "authorization.evaluated"
  | "approval.required"
  | "action.executing"
  | "action.completed"
  | "audit.created"
  | "run.completed"
  | "run.failed"
  | "run.blocked"
  | "connected"
  | "stream_end";

/** A single event delivered by the backend SSE stream (`/api/runs/{id}/stream`). */
export interface SSEEvent {
  /** Synthetic client-side event id; backend events carry their own. */
  event_id?: string;
  run_id: string;
  timestamp: string;
  event_type: WorkflowEventType;
  step_number?: number;
  agent?: string;
  status?: string;
  message?: string;
  metadata?: Record<string, unknown>;
  /** Set for synthetic client events ("connected" / "stream_end"). */
  data?: Record<string, unknown>;
}

/** Live execution view state derived from the real SSE event stream. */
export interface RunStepView {
  key: string;
  label: string;
  status: "pending" | "active" | "complete" | "error";
}

export interface RunToolCallView {
  key: string;
  toolName: string;
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  success?: boolean;
  durationMs?: number;
  calledAt?: string;
  expanded?: boolean;
}

export interface RunViewState {
  status: "waiting" | "running" | "complete" | "failed" | "blocked" | "awaiting_approval";
  startedAt?: string;
  completedAt?: string;
  structured?: { requestType: string; confidence: number };
  steps: RunStepView[];
  toolCalls: RunToolCallView[];
  evidenceCount: number;
  decision?: { type: string; confidence: number };
  verificationPassed?: boolean;
  violations: string[];
  authorizationTier?: number;
  approval?: { id?: string; reason?: string; riskLevel?: string };
  finalResult?: string;
  error?: string;
}

export interface SessionContext {
  user: { id: string; name: string; avatarUrl: string };
  tenant: { id: string; name: string };
  mode: "live" | "demo";
}

export interface RequestTemplate {
  id: string;
  icon: string;
  label: string;
  description: string;
}
