from __future__ import annotations

from pathlib import Path

import pytest

from cargo_release.engine import CargoReleaseEngine, DomainError, IdentityError
from cargo_release.models import (
    ArtifactStatus,
    EvidenceStatus,
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
from cargo_release.runtime import MissionOrchestrator, StepLimitError
from cargo_release.security import ReceiptSecurityError
from cargo_release.store import InvalidTransition, SQLiteMissionStore, VersionConflict


@pytest.fixture
def engine(tmp_path: Path) -> CargoReleaseEngine:
    return CargoReleaseEngine(SQLiteMissionStore(str(tmp_path / "mission.db")))


def action(snapshot: object, actor: str = "operator.demo") -> VersionedAction:
    version = snapshot.mission.version  # type: ignore[attr-defined]
    return VersionedAction(expected_version=version, actor=actor)


def ready_mission(engine: CargoReleaseEngine):  # type: ignore[no-untyped-def]
    snapshot = engine.create_demo_mission()
    return engine.analyze_evidence(snapshot.mission.id, action(snapshot))


def submitted_mission(engine: CargoReleaseEngine):  # type: ignore[no-untyped-def]
    snapshot = ready_mission(engine)
    snapshot = engine.approve_owner_bond(snapshot.mission.id, action(snapshot))
    guarantee = issue_insurer_guarantee(snapshot.mission.id, snapshot.mission.case_ref)
    snapshot, created = engine.apply_partner_receipt(guarantee, "partner:insurer")
    assert created
    return engine.submit_security(snapshot.mission.id, action(snapshot))


def test_full_release_requires_independent_receipts(engine: CargoReleaseEngine) -> None:
    snapshot = submitted_mission(engine)
    rejected = issue_adjuster_review(
        snapshot.mission.id,
        snapshot.mission.case_ref,
        declaration_reference_present=False,
    )
    snapshot, _ = engine.apply_partner_receipt(rejected, "partner:adjuster")
    assert snapshot.mission.release_state is ReleaseState.SECURITY_SUBMITTED

    snapshot = engine.correct_security(snapshot.mission.id, action(snapshot))
    accepted = issue_adjuster_review(
        snapshot.mission.id,
        snapshot.mission.case_ref,
        declaration_reference_present=True,
    )
    snapshot, _ = engine.apply_partner_receipt(accepted, "partner:adjuster")
    assert snapshot.mission.release_state is ReleaseState.SECURITY_ACCEPTED

    order = issue_carrier_release(snapshot.mission.id, snapshot.mission.container_ref)
    snapshot, _ = engine.apply_partner_receipt(order, "partner:carrier")
    assert snapshot.mission.release_state is ReleaseState.SECURITY_ACCEPTED

    readback = issue_carrier_readback(
        snapshot.mission.id, snapshot.mission.container_ref, order.external_id
    )
    snapshot, _ = engine.apply_partner_receipt(readback, "partner:carrier")
    assert snapshot.mission.release_state is ReleaseState.RELEASED
    assert snapshot.mission.adjustment_state == "OPEN"
    assert {receipt.kind for receipt in snapshot.receipts} >= {
        ReceiptKind.INSURER_GUARANTEE,
        ReceiptKind.ADJUSTER_REJECTION,
        ReceiptKind.ADJUSTER_ACCEPTANCE,
        ReceiptKind.CARRIER_RELEASE_ORDER,
        ReceiptKind.CARRIER_RELEASE_READBACK,
    }


def test_analysis_quarantines_prompt_injection(engine: CargoReleaseEngine) -> None:
    snapshot = ready_mission(engine)
    email = next(item for item in snapshot.evidence if item.kind == "Broker email")
    assert email.status is EvidenceStatus.QUARANTINED
    assert email.facts["accepted_as_fact"] is False
    assert any(trace.status == "BLOCKED" for trace in snapshot.traces)
    bond = next(item for item in snapshot.artifacts if item.kind == "OWNER_BOND")
    assert bond.status is ArtifactStatus.DRAFT
    assert bond.content["coverage_decision"] == "NOT_MADE"


def test_security_cannot_submit_without_human_approval(engine: CargoReleaseEngine) -> None:
    snapshot = ready_mission(engine)
    guarantee = issue_insurer_guarantee(snapshot.mission.id, snapshot.mission.case_ref)
    snapshot, _ = engine.apply_partner_receipt(guarantee, "partner:insurer")
    with pytest.raises(DomainError, match="owner-bond"):
        engine.submit_security(snapshot.mission.id, action(snapshot))


def test_duplicate_partner_receipt_is_idempotent(engine: CargoReleaseEngine) -> None:
    snapshot = ready_mission(engine)
    snapshot = engine.approve_owner_bond(snapshot.mission.id, action(snapshot))
    receipt = issue_insurer_guarantee(snapshot.mission.id, snapshot.mission.case_ref)
    first, created = engine.apply_partner_receipt(receipt, "partner:insurer")
    assert created
    second, created = engine.apply_partner_receipt(receipt, "partner:insurer")
    assert not created
    assert second.mission.version == first.mission.version
    assert len(second.receipts) == 1


def test_wrong_identity_and_tampered_receipt_fail_closed(engine: CargoReleaseEngine) -> None:
    snapshot = ready_mission(engine)
    receipt = issue_insurer_guarantee(snapshot.mission.id, snapshot.mission.case_ref)
    with pytest.raises(IdentityError):
        engine.apply_partner_receipt(receipt, "partner:carrier")
    tampered = receipt.model_copy(update={"status": "ACCEPTED_BY_MAGIC"})
    with pytest.raises(ReceiptSecurityError):
        engine.apply_partner_receipt(tampered, "partner:insurer")


def test_version_conflict_fails_closed(engine: CargoReleaseEngine) -> None:
    snapshot = engine.create_demo_mission()
    with pytest.raises(VersionConflict):
        engine.analyze_evidence(
            snapshot.mission.id,
            VersionedAction(expected_version=99, actor="stale-operator"),
        )


def test_readback_cannot_replace_release_order(engine: CargoReleaseEngine) -> None:
    snapshot = submitted_mission(engine)
    accepted = issue_adjuster_review(
        snapshot.mission.id,
        snapshot.mission.case_ref,
        declaration_reference_present=True,
    )
    snapshot, _ = engine.apply_partner_receipt(accepted, "partner:adjuster")
    readback = issue_carrier_readback(
        snapshot.mission.id, snapshot.mission.container_ref, "missing-order"
    )
    with pytest.raises(InvalidTransition, match="CARRIER_RELEASE_ORDER"):
        engine.apply_partner_receipt(readback, "partner:carrier")


def test_bounded_runtime_yields_once_then_completes_release(
    engine: CargoReleaseEngine,
) -> None:
    runtime = MissionOrchestrator(engine)
    snapshot = engine.create_demo_mission()
    snapshot = runtime.run(snapshot.mission.id)
    assert snapshot.mission.release_state is ReleaseState.READY_FOR_SIGNATURE
    assert snapshot.runs[-1].status is RunStatus.WAITING_HUMAN
    assert snapshot.runs[-1].reason == "OWNER_BOND_APPROVAL_REQUIRED"

    snapshot = engine.approve_owner_bond(snapshot.mission.id, action(snapshot, "cargo-owner.demo"))
    snapshot = runtime.run(snapshot.mission.id)
    assert snapshot.mission.release_state is ReleaseState.RELEASED
    assert snapshot.runs[-1].status is RunStatus.COMPLETED
    assert snapshot.runs[-1].steps == 7
    assert len(snapshot.receipts) == 5
    packs = [item for item in snapshot.artifacts if item.kind == "SECURITY_PACK"]
    assert [item.revision for item in packs] == [1, 2]
    assert packs[-1].content["declaration_reference"] == snapshot.mission.case_ref
    memory = engine.store.reviewed_memory(snapshot.mission.id, "verified-release-context-v1")
    assert memory is not None
    assert memory["value"]["adjustment_state"] == "OPEN"
    assert memory["reviewed_by"] == "policy:release-readback-v1"


def test_runtime_step_cap_fails_closed(engine: CargoReleaseEngine) -> None:
    snapshot = engine.create_demo_mission()
    runtime = MissionOrchestrator(engine, max_steps=1)
    with pytest.raises(StepLimitError):
        runtime.run(snapshot.mission.id)
    snapshot = engine.store.snapshot(snapshot.mission.id)
    assert snapshot.mission.release_state is ReleaseState.READY_FOR_SIGNATURE
    assert snapshot.runs[-1].status is RunStatus.FAILED
