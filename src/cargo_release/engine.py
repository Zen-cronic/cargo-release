from __future__ import annotations

from uuid import uuid4

from cargo_release.models import (
    ArtifactStatus,
    EvidenceStatus,
    MissionSnapshot,
    PartnerReceipt,
    ReceiptKind,
    ReleaseState,
    TruthMode,
    VersionedAction,
)
from cargo_release.partners import PARTNER_SECRETS
from cargo_release.security import verify_receipt
from cargo_release.store import InvalidTransition, SQLiteMissionStore


class DomainError(RuntimeError):
    pass


class IdentityError(DomainError):
    pass


class CargoReleaseEngine:
    def __init__(self, store: SQLiteMissionStore) -> None:
        self.store = store

    def create_demo_mission(self) -> MissionSnapshot:
        return self.store.create_demo_mission(f"mission-{uuid4().hex[:12]}")

    def analyze_evidence(self, mission_id: str, action: VersionedAction) -> MissionSnapshot:
        snapshot = self.store.snapshot(mission_id)
        if snapshot.mission.release_state is not ReleaseState.EVIDENCE_BLOCKED:
            raise InvalidTransition("Evidence analysis is only allowed while evidence is blocked")
        self.store.record_trace(
            mission_id,
            "manifest-evidence@1.0.0",
            "reconcile_identifiers",
            TruthMode.FIXTURE,
            "PROPOSAL_ACCEPTED",
            {
                "bill_container": "TCLU-482019-1",
                "invoice_container": "TCLU-482019-7",
                "resolution": "carrier manifest confirms check digit 7",
            },
        )
        self.store.record_trace(
            mission_id,
            "model-armor@local",
            "scan_untrusted_evidence",
            TruthMode.ADAPTER,
            "BLOCKED",
            {"evidence_kind": "Broker email", "rule": "prompt-injection-in-evidence"},
        )
        snapshot = self.store.mutate(
            mission_id,
            action.expected_version,
            event_type="EVIDENCE_RECONCILED",
            actor="agent:manifest-evidence@1.0.0",
            payload={
                "container_ref": "TCLU-482019-7",
                "model_output": "proposal-only",
                "quarantined": ["Broker email"],
            },
            allowed_states={ReleaseState.EVIDENCE_BLOCKED},
            target_state=ReleaseState.READY_FOR_SIGNATURE,
            evidence_updates={
                "Bill of lading": (
                    EvidenceStatus.VERIFIED,
                    "Carrier manifest confirms the invoice container check digit.",
                    {
                        "bill_ref": "BL-8814",
                        "container": "TCLU-482019-7",
                        "resolution_source": "synthetic carrier manifest",
                    },
                ),
                "Broker email": (
                    EvidenceStatus.QUARANTINED,
                    "Model-addressed instruction quarantined; no mission fact accepted.",
                    {"guard": "prompt-injection-in-evidence", "accepted_as_fact": False},
                ),
            },
        )
        if self.store.latest_artifact(mission_id, "OWNER_BOND") is None:
            self.store.save_artifact(
                mission_id,
                "OWNER_BOND",
                ArtifactStatus.DRAFT,
                {
                    "case_ref": snapshot.mission.case_ref,
                    "cargo_owner": "North Harbor Imports Ltd",
                    "container_ref": snapshot.mission.container_ref,
                    "security_amount": "USD 128,400",
                    "instrument": "General Average bond",
                    "authority": "cargo owner",
                    "coverage_decision": "NOT_MADE",
                },
            )
        return self.store.snapshot(mission_id)

    def approve_owner_bond(self, mission_id: str, action: VersionedAction) -> MissionSnapshot:
        artifact = self.store.latest_artifact(mission_id, "OWNER_BOND")
        if artifact is None:
            raise DomainError("Owner bond artifact has not been generated")
        snapshot = self.store.mutate(
            mission_id,
            action.expected_version,
            event_type="OWNER_BOND_APPROVED",
            actor=action.actor,
            payload={"authority": "human", "signature_mode": "synthetic-attestation"},
            allowed_states={ReleaseState.READY_FOR_SIGNATURE},
            approval=("OWNER_BOND", f"artifact://{artifact.id}@{artifact.digest[:12]}"),
        )
        self.store.set_artifact_status(artifact.id, ArtifactStatus.APPROVED)
        return self.store.snapshot(snapshot.mission.id)

    def submit_security(self, mission_id: str, action: VersionedAction) -> MissionSnapshot:
        snapshot = self.store.snapshot(mission_id)
        if not any(item.kind == "OWNER_BOND" for item in snapshot.approvals):
            raise DomainError("Human owner-bond approval is required")
        if not any(item.kind is ReceiptKind.INSURER_GUARANTEE for item in snapshot.receipts):
            raise DomainError("Verified insurer guarantee receipt is required")
        snapshot = self.store.mutate(
            mission_id,
            action.expected_version,
            event_type="SECURITY_SUBMITTED",
            actor=action.actor,
            payload={"pack": "owner bond + insurer guarantee", "delivery": "sandbox-adjuster"},
            allowed_states={ReleaseState.READY_FOR_SIGNATURE},
            target_state=ReleaseState.SECURITY_SUBMITTED,
        )
        if self.store.latest_artifact(mission_id, "SECURITY_PACK") is None:
            guarantee = next(
                item for item in snapshot.receipts if item.kind is ReceiptKind.INSURER_GUARANTEE
            )
            approval = next(item for item in snapshot.approvals if item.kind == "OWNER_BOND")
            self.store.save_artifact(
                mission_id,
                "SECURITY_PACK",
                ArtifactStatus.SUBMITTED,
                {
                    "case_ref": snapshot.mission.case_ref,
                    "owner_bond_ref": approval.artifact_ref,
                    "insurer_guarantee_ref": guarantee.external_id,
                    "declaration_reference": None,
                    "delivery": "sandbox-adjuster",
                },
            )
        return self.store.snapshot(mission_id)

    def correct_security(self, mission_id: str, action: VersionedAction) -> MissionSnapshot:
        snapshot = self.store.snapshot(mission_id)
        if not any(item.kind is ReceiptKind.ADJUSTER_REJECTION for item in snapshot.receipts):
            raise DomainError("An adjuster correction receipt is required")
        pack = self.store.latest_artifact(mission_id, "SECURITY_PACK")
        if pack is None:
            raise DomainError("Security pack artifact has not been generated")
        snapshot = self.store.mutate(
            mission_id,
            action.expected_version,
            event_type="SECURITY_PACK_CORRECTED",
            actor=action.actor,
            payload={"field": "declaration reference", "value": snapshot.mission.case_ref},
            allowed_states={ReleaseState.SECURITY_SUBMITTED},
        )
        self.store.save_artifact(
            mission_id,
            "SECURITY_PACK",
            ArtifactStatus.SUBMITTED,
            {
                **pack.content,
                "declaration_reference": snapshot.mission.case_ref,
                "supersedes_digest": pack.digest,
                "correction": "adjuster rejection preserved",
            },
        )
        return self.store.snapshot(mission_id)

    def apply_partner_receipt(
        self,
        receipt: PartnerReceipt,
        partner_identity: str,
        truth_mode: TruthMode = TruthMode.FIXTURE,
    ) -> tuple[MissionSnapshot, bool]:
        expected_identity = f"partner:{receipt.issuer}"
        if partner_identity != expected_identity:
            raise IdentityError(
                f"Receipt issuer {receipt.issuer} requires identity {expected_identity}"
            )
        secret = PARTNER_SECRETS.get(receipt.issuer)
        if secret is None:
            raise IdentityError(f"Unknown partner issuer: {receipt.issuer}")
        digest = verify_receipt(receipt, secret)
        policy: dict[
            ReceiptKind, tuple[set[ReleaseState], ReleaseState | None, ReceiptKind | None]
        ] = {
            ReceiptKind.INSURER_GUARANTEE: (
                {ReleaseState.READY_FOR_SIGNATURE},
                None,
                None,
            ),
            ReceiptKind.ADJUSTER_REJECTION: (
                {ReleaseState.SECURITY_SUBMITTED},
                None,
                None,
            ),
            ReceiptKind.ADJUSTER_ACCEPTANCE: (
                {ReleaseState.SECURITY_SUBMITTED},
                ReleaseState.SECURITY_ACCEPTED,
                None,
            ),
            ReceiptKind.CARRIER_RELEASE_ORDER: (
                {ReleaseState.SECURITY_ACCEPTED},
                None,
                ReceiptKind.ADJUSTER_ACCEPTANCE,
            ),
            ReceiptKind.CARRIER_RELEASE_READBACK: (
                {ReleaseState.SECURITY_ACCEPTED},
                ReleaseState.RELEASED,
                ReceiptKind.CARRIER_RELEASE_ORDER,
            ),
        }
        allowed, target, required = policy[receipt.kind]
        snapshot, created = self.store.record_receipt(
            receipt,
            digest,
            allowed_states=allowed,
            target_state=target,
            required_receipt=required,
        )
        if created:
            self.store.record_trace(
                receipt.mission_id,
                f"{receipt.issuer}-liaison@1.0.0",
                "verify_partner_receipt",
                truth_mode,
                "VERIFIED",
                {"kind": receipt.kind, "external_id": receipt.external_id, "digest": digest},
            )
            snapshot = self.store.snapshot(receipt.mission_id)
        return snapshot, created
