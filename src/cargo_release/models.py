from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class TruthMode(StrEnum):
    FIXTURE = "FIXTURE"
    ADAPTER = "ADAPTER"
    NATIVE = "NATIVE"


class ReleaseState(StrEnum):
    DECLARED = "DECLARED"
    EVIDENCE_BLOCKED = "EVIDENCE_BLOCKED"
    READY_FOR_SIGNATURE = "READY_FOR_SIGNATURE"
    SECURITY_SUBMITTED = "SECURITY_SUBMITTED"
    SECURITY_ACCEPTED = "SECURITY_ACCEPTED"
    RELEASED = "RELEASED"


class AdjustmentState(StrEnum):
    OPEN = "OPEN"
    SETTLED = "SETTLED"
    CLOSED = "CLOSED"


class EvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    QUARANTINED = "QUARANTINED"


class ArtifactStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReceiptKind(StrEnum):
    INSURER_GUARANTEE = "INSURER_GUARANTEE"
    ADJUSTER_REJECTION = "ADJUSTER_REJECTION"
    ADJUSTER_ACCEPTANCE = "ADJUSTER_ACCEPTANCE"
    CARRIER_RELEASE_ORDER = "CARRIER_RELEASE_ORDER"
    CARRIER_RELEASE_READBACK = "CARRIER_RELEASE_READBACK"


class Mission(BaseModel):
    id: str
    case_ref: str
    vessel: str
    container_ref: str
    release_state: ReleaseState
    adjustment_state: AdjustmentState
    version: int
    truth_mode: TruthMode
    created_at: str
    updated_at: str


class Evidence(BaseModel):
    id: str
    mission_id: str
    kind: str
    filename: str
    sha256: str
    status: EvidenceStatus
    summary: str
    facts: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class Approval(BaseModel):
    id: str
    mission_id: str
    kind: str
    actor: str
    artifact_ref: str
    approved_at: str


class PartnerReceipt(BaseModel):
    mission_id: str
    kind: ReceiptKind
    issuer: str
    external_id: str
    subject_ref: str
    status: str
    issued_at: str
    payload: dict[str, Any] = Field(default_factory=dict)
    signature: str = ""

    def unsigned(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"signature"})


class StoredReceipt(PartnerReceipt):
    id: str
    verified: bool
    digest: str


class MissionEvent(BaseModel):
    seq: int
    mission_id: str
    event_type: str
    actor: str
    payload: dict[str, Any]
    prev_hash: str
    event_hash: str
    created_at: str


class TraceSpan(BaseModel):
    id: str
    mission_id: str
    agent: str
    operation: str
    truth_mode: TruthMode
    status: str
    detail: dict[str, Any]
    created_at: str


class MissionArtifact(BaseModel):
    id: str
    mission_id: str
    kind: str
    revision: int
    status: ArtifactStatus
    content: dict[str, Any]
    digest: str
    created_at: str


class MissionRun(BaseModel):
    id: str
    mission_id: str
    status: RunStatus
    reason: str
    steps: int
    started_at: str
    updated_at: str


class NotificationDelivery(BaseModel):
    id: str
    mission_id: str
    kind: str
    endpoint_label: str
    provider_ref: str
    payload_digest: str
    truth_mode: TruthMode
    status: str
    delivered_at: str


class MissionSnapshot(BaseModel):
    mission: Mission
    evidence: list[Evidence]
    approvals: list[Approval]
    receipts: list[StoredReceipt]
    events: list[MissionEvent]
    traces: list[TraceSpan]
    artifacts: list[MissionArtifact]
    runs: list[MissionRun]
    notifications: list[NotificationDelivery]


class VersionedAction(BaseModel):
    expected_version: int
    actor: str = "operator.demo"


class SyntheticNotificationAction(BaseModel):
    confirm_synthetic: bool = False
    actor: str = "operator.demo"


class ReceiptEnvelope(BaseModel):
    receipt: PartnerReceipt


class CasualtyEvent(BaseModel):
    vessel: str = "MV Northstar"
    container_ref: str = "TCLU-482019-7"
    source_ref: str = "GA/NST/0819"


class PubSubMessage(BaseModel):
    data: str
    message_id: str | None = Field(default=None, alias="messageId")
    attributes: dict[str, str] = Field(default_factory=dict)


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str | None = None
