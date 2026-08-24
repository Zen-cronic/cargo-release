export type TruthMode = "FIXTURE" | "ADAPTER" | "NATIVE";
export type ReleaseState =
  | "DECLARED"
  | "EVIDENCE_BLOCKED"
  | "READY_FOR_SIGNATURE"
  | "SECURITY_SUBMITTED"
  | "SECURITY_ACCEPTED"
  | "RELEASED";

export interface Mission {
  id: string;
  case_ref: string;
  vessel: string;
  container_ref: string;
  release_state: ReleaseState;
  adjustment_state: "OPEN" | "SETTLED" | "CLOSED";
  version: number;
  truth_mode: TruthMode;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  id: string;
  kind: string;
  filename: string;
  sha256: string;
  status: "VERIFIED" | "NEEDS_REVIEW" | "QUARANTINED";
  summary: string;
  facts: Record<string, unknown>;
}

export interface Approval {
  id: string;
  kind: string;
  actor: string;
  artifact_ref: string;
  approved_at: string;
}

export type ReceiptKind =
  | "INSURER_GUARANTEE"
  | "ADJUSTER_REJECTION"
  | "ADJUSTER_ACCEPTANCE"
  | "CARRIER_RELEASE_ORDER"
  | "CARRIER_RELEASE_READBACK";

export interface Receipt {
  id: string;
  kind: ReceiptKind;
  issuer: string;
  external_id: string;
  subject_ref: string;
  status: string;
  issued_at: string;
  payload: Record<string, unknown>;
  verified: boolean;
  digest: string;
}

export interface MissionEvent {
  seq: number;
  event_type: string;
  actor: string;
  payload: Record<string, unknown>;
  event_hash: string;
  created_at: string;
}

export interface TraceSpan {
  id: string;
  agent: string;
  operation: string;
  truth_mode: TruthMode;
  status: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface MissionArtifact {
  id: string;
  kind: string;
  revision: number;
  status: "DRAFT" | "APPROVED" | "SUBMITTED";
  content: Record<string, unknown>;
  digest: string;
  created_at: string;
}

export interface MissionRun {
  id: string;
  status: "RUNNING" | "WAITING_HUMAN" | "COMPLETED" | "FAILED";
  reason: string;
  steps: number;
  started_at: string;
  updated_at: string;
}

export interface MissionSnapshot {
  mission: Mission;
  evidence: Evidence[];
  approvals: Approval[];
  receipts: Receipt[];
  events: MissionEvent[];
  traces: TraceSpan[];
  artifacts: MissionArtifact[];
  runs: MissionRun[];
}

const API_BASE =
  process.env.NEXT_PUBLIC_AGENT_URL ??
  (process.env.NODE_ENV === "production" ? "/api/cargo" : "http://127.0.0.1:8095");

async function request(path: string, init?: RequestInit): Promise<MissionSnapshot> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Mission API returned ${response.status}`);
  }
  return (await response.json()) as MissionSnapshot;
}

export function createDemoMission(): Promise<MissionSnapshot> {
  return request("/v1/missions/demo", { method: "POST" });
}

export function postMissionAction(
  missionId: string,
  path: string,
  expectedVersion?: number,
  actor = "operator.demo",
): Promise<MissionSnapshot> {
  return request(`/v1/missions/${missionId}${path}`, {
    method: "POST",
    body:
      expectedVersion === undefined
        ? undefined
        : JSON.stringify({ expected_version: expectedVersion, actor }),
  });
}
