from __future__ import annotations

from uuid import uuid4

from cargo_release.engine import CargoReleaseEngine, DomainError
from cargo_release.models import (
    MissionSnapshot,
    ReceiptKind,
    ReleaseState,
    RunStatus,
    VersionedAction,
)
from cargo_release.partners import (
    issue_adjuster_review,
    issue_carrier_readback,
    issue_carrier_release,
    issue_insurer_guarantee,
)


class RunBusyError(DomainError):
    pass


class StepLimitError(DomainError):
    pass


class MissionOrchestrator:
    """Bounded local runtime that yields only at a legally meaningful human gate."""

    def __init__(self, engine: CargoReleaseEngine, max_steps: int = 12) -> None:
        self.engine = engine
        self.store = engine.store
        self.max_steps = max_steps

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
                        receipt = issue_insurer_guarantee(mission_id, snapshot.mission.case_ref)
                        self.engine.apply_partner_receipt(receipt, "partner:insurer")
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
                        receipt = issue_adjuster_review(
                            mission_id,
                            snapshot.mission.case_ref,
                            declaration_reference_present=False,
                        )
                        self.engine.apply_partner_receipt(receipt, "partner:adjuster")
                    elif not self._has_event(snapshot, "SECURITY_PACK_CORRECTED"):
                        self.engine.correct_security(
                            mission_id,
                            VersionedAction(
                                expected_version=snapshot.mission.version,
                                actor="agent:security-pack@1.0.0",
                            ),
                        )
                    else:
                        receipt = issue_adjuster_review(
                            mission_id,
                            snapshot.mission.case_ref,
                            declaration_reference_present=True,
                        )
                        self.engine.apply_partner_receipt(receipt, "partner:adjuster")
                elif state is ReleaseState.SECURITY_ACCEPTED:
                    if not self._has_receipt(snapshot, ReceiptKind.CARRIER_RELEASE_ORDER):
                        receipt = issue_carrier_release(mission_id, snapshot.mission.container_ref)
                        self.engine.apply_partner_receipt(receipt, "partner:carrier")
                    elif not self._has_receipt(snapshot, ReceiptKind.CARRIER_RELEASE_READBACK):
                        release = next(
                            item
                            for item in snapshot.receipts
                            if item.kind is ReceiptKind.CARRIER_RELEASE_ORDER
                        )
                        receipt = issue_carrier_readback(
                            mission_id,
                            snapshot.mission.container_ref,
                            release.external_id,
                        )
                        self.engine.apply_partner_receipt(receipt, "partner:carrier")
                elif state is ReleaseState.RELEASED:
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
