from __future__ import annotations

from pathlib import Path

import pytest

from cargo_release.engine import CargoReleaseEngine
from cargo_release.models import ReceiptKind, TruthMode, VersionedAction
from cargo_release.partner_client import (
    CloudRunPartnerServices,
    LocalPartnerFixtures,
    build_partner_port,
)
from cargo_release.runtime import MissionOrchestrator
from cargo_release.store import SQLiteMissionStore


class NativePartnerProbe(LocalPartnerFixtures):
    """Deterministic signer used only to prove truth-mode propagation in tests."""

    truth_mode = TruthMode.NATIVE


def test_local_partner_port_is_the_fail_closed_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "K_SERVICE",
        "GOOGLE_CLOUD_PROJECT",
        "CARGO_RELEASE_INSURER_URL",
        "CARGO_RELEASE_ADJUSTER_URL",
        "CARGO_RELEASE_CARRIER_URL",
        "CARGO_RELEASE_INSURER_AUDIENCE",
        "CARGO_RELEASE_ADJUSTER_AUDIENCE",
        "CARGO_RELEASE_CARRIER_AUDIENCE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(build_partner_port(), LocalPartnerFixtures)


def test_cloud_run_partner_port_requires_runtime_identity_and_all_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("K_SERVICE", "cargo-release-controller")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "cargo-release-demo")
    monkeypatch.setenv("CARGO_RELEASE_INSURER_URL", "https://insurer.example")
    monkeypatch.setenv("CARGO_RELEASE_ADJUSTER_URL", "https://adjuster.example")
    assert isinstance(build_partner_port(), LocalPartnerFixtures)

    monkeypatch.setenv("CARGO_RELEASE_CARRIER_URL", "https://carrier.example")
    monkeypatch.setenv(
        "CARGO_RELEASE_INSURER_AUDIENCE", "https://insurer-audience.example"
    )
    partner_port = build_partner_port()
    assert isinstance(partner_port, CloudRunPartnerServices)
    assert partner_port.insurer_audience == "https://insurer-audience.example"
    assert partner_port.adjuster_audience == "https://adjuster.example"


def test_runtime_preserves_native_partner_provenance(tmp_path: Path) -> None:
    engine = CargoReleaseEngine(SQLiteMissionStore(str(tmp_path / "native-partners.db")))
    runtime = MissionOrchestrator(engine, partners=NativePartnerProbe())
    snapshot = engine.create_demo_mission()
    snapshot = runtime.run(snapshot.mission.id)
    snapshot = engine.approve_owner_bond(
        snapshot.mission.id,
        VersionedAction(
            expected_version=snapshot.mission.version,
            actor="cargo-owner.demo",
        ),
    )
    snapshot = runtime.run(snapshot.mission.id)

    receipt_traces = [
        trace for trace in snapshot.traces if trace.operation == "verify_partner_receipt"
    ]
    assert len(receipt_traces) == 5
    assert all(trace.truth_mode is TruthMode.NATIVE for trace in receipt_traces)
    assert {receipt.kind for receipt in snapshot.receipts} >= {
        ReceiptKind.ADJUSTER_ACCEPTANCE,
        ReceiptKind.CARRIER_RELEASE_READBACK,
    }
