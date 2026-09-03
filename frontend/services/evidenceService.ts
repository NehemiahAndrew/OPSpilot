// OPSpilot - frontend/services/evidenceService.ts
import type { EvidenceManifest, EvidenceItem, DecisionRecord, ConstitutionalCheckResult, AuthorizationResult } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface EvidenceProvenanceItem {
  evidence_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  raw_result: Record<string, unknown>;
  retrieved_at: string;
  cited_in_decision: boolean;
  verification_status: "verified" | "invalid" | "warning";
  evidence_type: string;
  evidence_key: string;
  data_summary: string;
  used_for: string;
}

export interface FabricatedWarning {
  message: string;
  fabricated_refs: string[];
}

export interface EvidenceScreenData {
  manifest: EvidenceManifest;
  decision: DecisionRecord | null;
  constitutional_result: ConstitutionalCheckResult | null;
  provenance: EvidenceProvenanceItem[];
  fabricated_warning: FabricatedWarning | null;
}

export interface EvidenceServiceInterface {
  getEvidence(runId: string): Promise<EvidenceScreenData>;
}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export class ApiEvidenceService implements EvidenceServiceInterface {
  async getEvidence(runId: string): Promise<EvidenceScreenData> {
    return request<EvidenceScreenData>(`/api/runs/${runId}/evidence`);
  }
}

export const evidenceService = new ApiEvidenceService();