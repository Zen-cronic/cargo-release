from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from cargo_release.models import (
    ArtifactStatus,
    EvidenceStatus,
    MissionSnapshot,
    ModelReceiptStatus,
    PartnerReceipt,
    ReceiptKind,
    ReleaseState,
    TruthMode,
    VersionedAction,
)
from cargo_release.multimodal import (
    EXTRACTION_SCHEMA_VERSION,
    MULTIMODAL_EXTRACTION_KIND,
    MultimodalExtractionPort,
    build_multimodal_extractor,
    validate_extraction,
)
from cargo_release.partners import PARTNER_SECRETS
from cargo_release.security import verify_receipt
from cargo_release.store import InvalidTransition, MissionStore


class DomainError(RuntimeError):
    pass


class IdentityError(DomainError):
    pass


class CargoReleaseEngine:
    def __init__(
        self,
        store: MissionStore,
        multimodal_extractor: MultimodalExtractionPort | None = None,
    ) -> None:
        self.store = store
        self.multimodal_extractor = multimodal_extractor or build_multimodal_extractor()

    def create_demo_mission(self) -> MissionSnapshot:
        return self.store.create_demo_mission(f"mission-{uuid4().hex[:12]}")

    def analyze_evidence(self, mission_id: str, action: VersionedAction) -> MissionSnapshot:
        snapshot = self.store.snapshot(mission_id)
        if snapshot.mission.release_state is not ReleaseState.EVIDENCE_BLOCKED:
            raise InvalidTransition("Evidence analysis is only allowed while evidence is blocked")
        scan = next(
            (item for item in snapshot.evidence if item.kind == "Adjuster rejection scan"),
            None,
        )
        if scan is None:
            raise DomainError("Prepared adjuster rejection scan is missing from mission intake")
        source_path = Path(__file__).with_name("assets") / scan.filename
        media = source_path.read_bytes()
        source_ref = f"evidence://{scan.id}@{scan.media_digest[:16]}"
        expected_case_reference = next(
            (
                str(item.facts.get("adjuster_ref"))
                for item in snapshot.evidence
                if item.kind == "Casualty notice" and item.facts.get("adjuster_ref")
            ),
            "",
        )
        extraction: dict[str, object] = {}
        confidence = 0.0
        validation_outcome = "MODEL_OUTPUT_INVALID"
        try:
            invocation = self.multimodal_extractor.extract(media, scan.media_digest)
            extracted = invocation.extraction
            extraction = extracted.model_dump(mode="json")
            confidence = extracted.confidence
            accepted, validation_outcome = validate_extraction(
                extracted,
                expected_case_reference=expected_case_reference,
                expected_container_ref=snapshot.mission.container_ref,
            )
            model_status = ModelReceiptStatus.COMPLETED
            request_ref = invocation.request_ref
            input_digest = invocation.input_digest
            output_digest = invocation.output_digest
        except Exception as error:
            accepted = False
            model_status = ModelReceiptStatus.DEGRADED
            request_ref = f"multimodal-error-{uuid4().hex[:12]}"
            input_digest = scan.media_digest
            extraction = {
                "error_type": type(error).__name__,
                "error_code": str(
                    getattr(error, "code", "UNCLASSIFIED_MULTIMODAL_ERROR")
                ),
                "retryable": True,
                "release_affected": False,
            }
            output_digest = hashlib.sha256(
                json.dumps(extraction, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()

        self.store.record_model_receipt(
            mission_id,
            kind=MULTIMODAL_EXTRACTION_KIND,
            model_id=self.multimodal_extractor.model_id,
            location=self.multimodal_extractor.location,
            request_ref=request_ref,
            input_digest=input_digest,
            output_digest=output_digest,
            status=model_status,
            truth_mode=self.multimodal_extractor.truth_mode,
            result={
                "extraction": extraction,
                "confidence": confidence,
                "validation_outcome": validation_outcome,
                "release_authority": False,
                "raw_reasoning_exposed": False,
            },
            actor="system:multimodal-intake@1.0.0",
            source_artifact_ref=source_ref,
            extraction_schema_version=EXTRACTION_SCHEMA_VERSION,
            validation_outcome=validation_outcome,
        )
        self.store.record_evidence_extraction(
            mission_id,
            scan.id,
            extraction=extraction,
            confidence=confidence,
            status=EvidenceStatus.VERIFIED if accepted else EvidenceStatus.NEEDS_REVIEW,
            summary=(
                "Validated scan identifies the declaration reference required for revision 2."
                if accepted
                else "Multimodal extraction failed closed; operator review is required."
            ),
            validation_outcome=validation_outcome,
            actor="policy:multimodal-evidence-v1",
        )
        self.store.record_trace(
            mission_id,
            "gemini-multimodal-intake@1.0.0",
            "extract_adjuster_rejection_scan",
            self.multimodal_extractor.truth_mode,
            "VALIDATED" if accepted else "REJECTED",
            {
                "evidence_id": scan.id,
                "source_digest": scan.media_digest,
                "schema_version": EXTRACTION_SCHEMA_VERSION,
                "validation_outcome": validation_outcome,
                "confidence": confidence,
                "release_authority": False,
            },
        )
        if not accepted:
            raise DomainError(
                f"Multimodal evidence failed closed ({validation_outcome}); review is required"
            )
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
                "Adjuster rejection scan": (
                    EvidenceStatus.VERIFIED,
                    "Validated scan identifies the declaration reference required for revision 2.",
                    {
                        "checked_defect": extraction["checked_defect"],
                        "missing_field": extraction["missing_field"],
                        "case_reference": extraction["case_reference"],
                        "validation_outcome": validation_outcome,
                    },
                ),
            },
        )
        self.store.record_event(
            mission_id,
            "EVIDENCE_QUARANTINED",
            "policy:model-armor-boundary-v1",
            {
                "evidence_kind": "Broker email",
                "accepted_as_fact": False,
                "trusted_state_mutation": False,
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
        scan = next(
            (item for item in snapshot.evidence if item.kind == "Adjuster rejection scan"),
            None,
        )
        if (
            scan is None
            or scan.status is not EvidenceStatus.VERIFIED
            or scan.confidence is None
            or scan.confidence < 0.85
            or scan.structured_extraction.get("missing_field") != "declaration_reference"
        ):
            raise DomainError("Validated adjuster scan is required to select the correction")
        declaration_reference = str(scan.structured_extraction.get("case_reference", ""))
        if not declaration_reference:
            raise DomainError("Validated adjuster scan contains no declaration reference")
        snapshot = self.store.mutate(
            mission_id,
            action.expected_version,
            event_type="SECURITY_PACK_CORRECTED",
            actor=action.actor,
            payload={
                "field": "declaration_reference",
                "value": declaration_reference,
                "caused_by": f"evidence://{scan.id}@{scan.media_digest[:16]}",
                "validation_outcome": "ACCEPTED",
            },
            allowed_states={ReleaseState.SECURITY_SUBMITTED},
        )
        self.store.save_artifact(
            mission_id,
            "SECURITY_PACK",
            ArtifactStatus.SUBMITTED,
            {
                **pack.content,
                "declaration_reference": declaration_reference,
                "supersedes_digest": pack.digest,
                "correction": "validated adjuster scan selected the missing field",
                "correction_evidence_ref": f"evidence://{scan.id}@{scan.media_digest[:16]}",
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
