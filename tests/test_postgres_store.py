from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from cargo_release.engine import CargoReleaseEngine
from cargo_release.models import VersionedAction
from cargo_release.partners import issue_insurer_guarantee
from cargo_release.store import PostgreSQLMissionStore


def connection_url() -> str:
    value = os.getenv("CARGO_RELEASE_TEST_DATABASE_URL")
    if not value:
        pytest.skip("CARGO_RELEASE_TEST_DATABASE_URL is required for PostgreSQL acceptance tests")
    return value


def new_store() -> PostgreSQLMissionStore:
    return PostgreSQLMissionStore(connection_url(), connect_timeout=10)


def mission_id(label: str) -> str:
    return f"mission-pg-{label}-{uuid4().hex[:8]}"


def test_postgres_restart_preserves_mission_authority() -> None:
    current_mission_id = mission_id("restart")
    first = new_store()
    snapshot, _ = first.create_or_load_demo_mission(current_mission_id)
    snapshot = CargoReleaseEngine(first).analyze_evidence(
        current_mission_id,
        VersionedAction(expected_version=snapshot.mission.version, actor="restart-proof"),
    )

    restarted = new_store().snapshot(current_mission_id)

    assert restarted.mission.version == snapshot.mission.version
    assert restarted.mission.release_state == "READY_FOR_SIGNATURE"
    assert [event.event_hash for event in restarted.events] == [
        event.event_hash for event in snapshot.events
    ]


def test_postgres_duplicate_event_converges_under_concurrency() -> None:
    current_mission_id = mission_id("duplicate-event")
    stores = (new_store(), new_store())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda store: store.create_or_load_demo_mission(
                    current_mission_id,
                    trigger_context={"cloud_event_id": "evt-pg-duplicate"},
                ),
                stores,
            )
        )

    assert sorted(created for _, created in results) == [False, True]
    snapshot = new_store().snapshot(current_mission_id)
    assert len(snapshot.events) == 1
    assert len(snapshot.evidence) == 4
    assert snapshot.events[0].payload["cloud_event_id"] == "evt-pg-duplicate"


def test_postgres_only_one_concurrent_runtime_lease_wins() -> None:
    current_mission_id = mission_id("lease")
    first = new_store()
    first.create_or_load_demo_mission(current_mission_id)
    stores = (first, new_store())
    owners = ("runtime-one", "runtime-two")

    with ThreadPoolExecutor(max_workers=2) as executor:
        acquired = list(
            executor.map(
                lambda pair: pair[0].acquire_lease(current_mission_id, pair[1], ttl_seconds=30),
                zip(stores, owners, strict=True),
            )
        )

    assert sorted(acquired) == [False, True]
    winner = owners[acquired.index(True)]
    new_store().release_lease(current_mission_id, winner)


def test_postgres_duplicate_receipt_mutates_once_under_concurrency() -> None:
    current_mission_id = mission_id("duplicate-receipt")
    initial_store = new_store()
    snapshot, _ = initial_store.create_or_load_demo_mission(current_mission_id)
    engine = CargoReleaseEngine(initial_store)
    snapshot = engine.analyze_evidence(
        current_mission_id,
        VersionedAction(expected_version=snapshot.mission.version, actor="receipt-proof"),
    )
    snapshot = engine.approve_owner_bond(
        current_mission_id,
        VersionedAction(expected_version=snapshot.mission.version, actor="cargo-owner.proof"),
    )
    receipt = issue_insurer_guarantee(current_mission_id, snapshot.mission.case_ref)
    engines = (CargoReleaseEngine(new_store()), CargoReleaseEngine(new_store()))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda current: current.apply_partner_receipt(receipt, "partner:insurer"),
                engines,
            )
        )

    assert sorted(created for _, created in results) == [False, True]
    stored = new_store().snapshot(current_mission_id)
    assert len(stored.receipts) == 1
    receipt_events = [
        event for event in stored.events if event.event_type == "RECEIPT_INSURER_GUARANTEE"
    ]
    assert len(receipt_events) == 1
