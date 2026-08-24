from __future__ import annotations

from uuid import uuid4

from cargo_release.engine import CargoReleaseEngine, DomainError
from cargo_release.memory import ReviewedMemoryPort, build_memory_port
from cargo_release.models import (
    MissionSnapshot,
    ReceiptKind,
    ReleaseState,
    RunStatus,
    VersionedAction,
)
from cargo_release.partner_client import PartnerPort, build_partner_port


class RunBusyError(DomainError):
    pass


class StepLimitError(DomainError):
    pass


class MissionOrchestrator:
    """Bounded local runtime that yields only at a legally meaningful human gate."""

    def __init__(
        self,
        engine: CargoReleaseEngine,
        max_steps: int = 12,
        memory: ReviewedMemoryPort | None = None,
        partners: PartnerPort | None = None,
    ) -> None:
        self.engine = engine
        self.store = engine.store
        self.max_steps = max_steps
        self.memory = memory or build_memory_port(self.store)
        self.partners = partners or build_partner_port()

    @staticmethod
    def _has_receipt(snapshot: MissionSnapshot, kind: ReceiptKind) -> bool:
        return any(item.kind is kind for item in snapshot.receipts)

    @staticmethod
    def _has_event(snapshot: MissionSnapshot, event_type: str) -> bool:
        return any(item.event_type == event_type for item in snapshot.events)

    def run(self, mission_id: str) -> MissionSnapshot:
        owner = f"runtime-{uuid4().hex[:12]}"
        if not self.store.acquire_lease(mission_id, owner):
            raise RunBusyError("Mission already has an active runtime lease")
        run = self.store.start_run(mission_id)
        steps = 0
        try:
            while steps < self.max_steps:
                snapshot = self.store.snapshot(mission_id)
                state = snapshot.mission.release_state
                if state is ReleaseState.EVIDENCE_BLOCKED:
                    self.engine.analyze_evidence(
                        mission_id,
                        VersionedAction(
                            expected_version=snapshot.mission.version,
                            actor="agent:mission-coordinator@1.0.0",
                        ),
                    )
                elif state is ReleaseState.READY_FOR_SIGNATURE:
                    if not snapshot.approvals:
                        self.store.finish_run(
                            run.id,
                            RunStatus.WAITING_HUMAN,
                            "OWNER_BOND_APPROVAL_REQUIRED",
                            steps,
                        )
                        return self.store.snapshot(mission_id)
                    if not self._has_receipt(snapshot, ReceiptKind.INSURER_GUARANTEE):
                        receipt = self.partners.insurer_guarantee(snapshot)
                        self.engine.apply_partner_receipt(
                            receipt,
                            "partner:insurer",
                            self.partners.truth_mode,
                        )
                    else:
                        self.engine.submit_security(
                            mission_id,
                            VersionedAction(
                                expected_version=snapshot.mission.version,
                                actor="agent:security-pack@1.0.0",
                            ),
                        )
                elif state is ReleaseState.SECURITY_SUBMITTED:
                    if not self._has_receipt(snapshot, ReceiptKind.ADJUSTER_REJECTION):
                        receipt = self.partners.adjuster_review(snapshot, corrected=False)
                        self.engine.apply_partner_receipt(
                            receipt,
                            "partner:adjuster",
                            self.partners.truth_mode,
                        )
                    elif not self._has_event(snapshot, "SECURITY_PACK_CORRECTED"):
                        self.engine.correct_security(
                            mission_id,
                            VersionedAction(
                                expected_version=snapshot.mission.version,
                                actor="agent:security-pack@1.0.0",
                            ),
                        )
                    else:
                        receipt = self.partners.adjuster_review(snapshot, corrected=True)
                        self.engine.apply_partner_receipt(
                            receipt,
                            "partner:adjuster",
                            self.partners.truth_mode,
                        )
                elif state is ReleaseState.SECURITY_ACCEPTED:
                    if not self._has_receipt(snapshot, ReceiptKind.CARRIER_RELEASE_ORDER):
                        receipt = self.partners.carrier_release(snapshot)
                        self.engine.apply_partner_receipt(
                            receipt,
                            "partner:carrier",
                            self.partners.truth_mode,
                        )
                    elif not self._has_receipt(snapshot, ReceiptKind.CARRIER_RELEASE_READBACK):
                        release = next(
                            item
                            for item in snapshot.receipts
                            if item.kind is ReceiptKind.CARRIER_RELEASE_ORDER
                        )
                        receipt = self.partners.carrier_readback(snapshot, release.external_id)
                        self.engine.apply_partner_receipt(
                            receipt,
                            "partner:carrier",
                            self.partners.truth_mode,
                        )
                elif state is ReleaseState.RELEASED:
                    try:
                        memory_ref = self.memory.remember_release_context(snapshot)
                        self.store.record_trace(
                            mission_id,
                            "adjustment-monitor@1.0.0",
                            "persist_reviewed_release_context",
                            snapshot.mission.truth_mode,
                            "STORED",
                            {"memory_ref": memory_ref, "authority": "reviewed-facts-only"},
                        )
                    except Exception as error:
                        self.store.record_trace(
                            mission_id,
                            "adjustment-monitor@1.0.0",
                            "persist_reviewed_release_context",
                            snapshot.mission.truth_mode,
                            "DEGRADED",
                            {"error": type(error).__name__, "release_affected": False},
                        )
                    self.store.finish_run(
                        run.id, RunStatus.COMPLETED, "CARRIER_READBACK_VERIFIED", steps
                    )
                    return self.store.snapshot(mission_id)
                else:
                    raise DomainError(f"Runtime cannot continue from {state}")
                steps += 1
            self.store.finish_run(run.id, RunStatus.FAILED, "BOUNDED_STEP_LIMIT_EXCEEDED", steps)
            raise StepLimitError(f"Mission exceeded the {self.max_steps}-step runtime cap")
        except Exception:
            latest = self.store.snapshot(mission_id).runs[-1]
            if latest.status is RunStatus.RUNNING:
                self.store.finish_run(run.id, RunStatus.FAILED, "RUNTIME_ERROR", steps)
            raise
        finally:
            self.store.release_lease(mission_id, owner)
