from __future__ import annotations

from pathlib import Path
from typing import Any

from cargo_release.api import create_app
from cargo_release.case_retrieval import FixtureCaseRetrieval
from cargo_release.gemma_critic import FixtureGemmaCritic
from cargo_release.veo_replay import FixtureVeoReplay
from scripts.probe_managed_bonus_models import validate_human_gate, validate_veo_replay
from tests.asgi_client import ASGITestClient


def release_fixture(client: ASGITestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    created = client.post("/v1/missions/demo").json()
    mission_id = created["mission"]["id"]
    held = client.post(f"/v1/missions/{mission_id}:run").json()
    released = client.post(
        f"/v1/missions/{mission_id}/approvals/owner-bond:approve-and-resume",
        json={
            "expected_version": held["mission"]["version"],
            "actor": "cargo-owner.probe-test",
        },
    ).json()
    return held, released


def test_combined_probe_validates_fixture_equivalent_boundaries(tmp_path: Path) -> None:
    client = ASGITestClient(
        create_app(
            str(tmp_path / "combined-probe.db"),
            gemma_critic=FixtureGemmaCritic(),
            case_retrieval=FixtureCaseRetrieval(),
            veo_replay=FixtureVeoReplay(),
        )
    )
    held, released = release_fixture(client)

    validate_human_gate(
        held,
        truth_mode="FIXTURE",
        gemma_location="fixture",
        embedding_location="fixture",
        require_gemma_tool_marker=False,
    )
    replayed = client.post(
        f"/v1/missions/{released['mission']['id']}/models/veo-replay:generate",
        json={"confirm_training_only": True, "actor": "operator.probe-test"},
    ).json()
    receipt = validate_veo_replay(
        released,
        replayed,
        truth_mode="FIXTURE",
        location="fixture",
        asset_prefix="fixture://veo-replay/",
    )

    assert receipt["result"]["asset_uri"].startswith("fixture://veo-replay/")


def test_combined_probe_rejects_degraded_receipt() -> None:
    snapshot = {
        "mission": {"release_state": "READY_FOR_SIGNATURE", "version": 1},
        "approvals": [],
        "receipts": [],
        "model_receipts": [
            {
                "kind": "GEMMA_RELEASE_CRITIC",
                "model_id": "google/gemma-4-26b-a4b-it-maas",
                "location": "global",
                "status": "DEGRADED",
                "truth_mode": "NATIVE",
                "release_authority": False,
                "request_ref": "gemma-error",
                "input_digest": "a" * 64,
                "output_digest": "b" * 64,
                "result": {"tool_calls_exposed": False},
            }
        ],
    }

    try:
        validate_human_gate(snapshot)
    except RuntimeError as error:
        assert "common boundary" in str(error)
    else:
        raise AssertionError("A degraded managed model receipt must fail the proof")
