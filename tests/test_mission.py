from __future__ import annotations

from pathlib import Path

import pytest

from cargo_release.engine import CargoReleaseEngine, DomainError, IdentityError
from cargo_release.models import EvidenceStatus, ReceiptKind, ReleaseState, VersionedAction
from cargo_release.partners import (
    issue_adjuster_review,
    issue_carrier_readback,
    issue_carrier_release,
    issue_insurer_guarantee,
)
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
