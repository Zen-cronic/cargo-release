from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from cargo_release.api import create_app
from cargo_release.cloud_context import eventarc_truth_mode
from cargo_release.models import TruthMode
from tests.asgi_client import ASGITestClient


def test_demo_route_walk_releases_cargo_but_not_adjustment(tmp_path: Path) -> None:
    client = ASGITestClient(create_app(str(tmp_path / "api.db")))
    response = client.post("/v1/missions/demo")
    assert response.status_code == 200
    snapshot = response.json()
    mission_id = snapshot["mission"]["id"]

    def post(path: str, body: dict[str, object] | None = None) -> dict[str, Any]:
        result = client.post(path, json=body)
        assert result.status_code == 200, result.text
        return cast(dict[str, Any], result.json())

    snapshot = post(
        f"/v1/missions/{mission_id}:analyze",
        {"expected_version": snapshot["mission"]["version"], "actor": "operator.demo"},
    )
    snapshot = post(
        f"/v1/missions/{mission_id}/approvals/owner-bond",
        {"expected_version": snapshot["mission"]["version"], "actor": "cargo-owner.demo"},
    )
    snapshot = post(f"/v1/missions/{mission_id}/demo/insurer")
    snapshot = post(
        f"/v1/missions/{mission_id}:submit-security",
        {"expected_version": snapshot["mission"]["version"], "actor": "operator.demo"},
    )
    snapshot = post(f"/v1/missions/{mission_id}/demo/adjuster")
    assert snapshot["mission"]["release_state"] == "SECURITY_SUBMITTED"
    snapshot = post(
        f"/v1/missions/{mission_id}:correct-security",
        {"expected_version": snapshot["mission"]["version"], "actor": "operator.demo"},
    )
    snapshot = post(f"/v1/missions/{mission_id}/demo/adjuster")
    snapshot = post(f"/v1/missions/{mission_id}/demo/carrier-release")
    assert snapshot["mission"]["release_state"] == "SECURITY_ACCEPTED"
    snapshot = post(f"/v1/missions/{mission_id}/demo/carrier-readback")

    assert snapshot["mission"]["release_state"] == "RELEASED"
    assert snapshot["mission"]["adjustment_state"] == "OPEN"
    assert len(snapshot["receipts"]) == 5


def test_api_requires_current_version(tmp_path: Path) -> None:
    client = ASGITestClient(create_app(str(tmp_path / "conflict.db")))
    snapshot = client.post("/v1/missions/demo").json()
    mission_id = snapshot["mission"]["id"]
    response = client.post(
        f"/v1/missions/{mission_id}:analyze",
        json={"expected_version": 42, "actor": "stale"},
    )
    assert response.status_code == 409


def test_prepared_scan_media_is_digest_bound_and_not_a_public_upload(
    tmp_path: Path,
) -> None:
    client = ASGITestClient(create_app(str(tmp_path / "media.db")))
    snapshot = client.post("/v1/missions/demo").json()
    scan = next(
        item for item in snapshot["evidence"] if item["kind"] == "Adjuster rejection scan"
    )

    response = client.get(
        f"/v1/missions/{snapshot['mission']['id']}/evidence/{scan['id']}/media"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert hashlib.sha256(response.content).hexdigest() == scan["media_digest"]
    missing = client.get(
        f"/v1/missions/{snapshot['mission']['id']}/evidence/ev-arbitrary/media"
    )
    assert missing.status_code == 409


def test_api_one_start_and_one_human_gate_complete_release(tmp_path: Path) -> None:
    client = ASGITestClient(create_app(str(tmp_path / "runtime.db")))
    snapshot = client.post("/v1/missions/demo").json()
    mission_id = snapshot["mission"]["id"]

    response = client.post(f"/v1/missions/{mission_id}:run")
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["mission"]["release_state"] == "READY_FOR_SIGNATURE"
    assert snapshot["runs"][-1]["status"] == "WAITING_HUMAN"

    response = client.post(
        f"/v1/missions/{mission_id}/approvals/owner-bond:approve-and-resume",
        json={
            "expected_version": snapshot["mission"]["version"],
            "actor": "cargo-owner.demo",
        },
    )
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["mission"]["release_state"] == "RELEASED"
    assert snapshot["mission"]["adjustment_state"] == "OPEN"
    assert snapshot["runs"][-1]["status"] == "COMPLETED"
    assert len(snapshot["artifacts"]) == 3


def test_cloudevent_ingress_is_idempotent_and_stops_at_human_gate(tmp_path: Path) -> None:
    client = ASGITestClient(create_app(str(tmp_path / "eventarc.db")))
    headers = {
        "ce-id": "evt-casualty-0819",
        "ce-source": "//pubsub.googleapis.com/projects/demo/topics/casualties",
        "ce-type": "com.cargorelease.casualty.declared.v1",
        "x-cloud-trace-context": "trace-demo/1;o=1",
    }
    casualty_data = base64.b64encode(
        json.dumps(
            {
                "source_ref": "GA/NST/0819",
                "vessel": "MV Northstar",
                "container_ref": "TCLU-482019-7",
            }
        ).encode()
    ).decode()
    envelope = {
        "message": {
            "data": casualty_data,
            "messageId": "pubsub-message-0819",
            "attributes": {"schema": "casualty-declared-v1"},
        },
        "subscription": "projects/demo/subscriptions/eventarc-us-central1-cargo",
    }
    first = client.post(
        "/v1/events/casualty",
        headers=headers,
        json=envelope,
    )
    assert first.status_code == 200, first.text
    snapshot = first.json()
    assert snapshot["mission"]["release_state"] == "READY_FOR_SIGNATURE"
    assert snapshot["mission"]["truth_mode"] == "FIXTURE"
    assert snapshot["events"][0]["payload"]["cloud_event_id"] == "evt-casualty-0819"
    assert len(snapshot["runs"]) == 1

    second = client.post(
        "/v1/events/casualty",
        headers=headers,
        json=envelope,
    )
    assert second.status_code == 200
    assert len(second.json()["runs"]) == 1


def test_cloudevent_rejects_invalid_pubsub_data(tmp_path: Path) -> None:
    client = ASGITestClient(create_app(str(tmp_path / "invalid-eventarc.db")))
    response = client.post(
        "/v1/events/casualty",
        headers={
            "ce-id": "evt-invalid",
            "ce-source": "//pubsub.googleapis.com/projects/demo/topics/casualties",
        },
        json={"message": {"data": "not-base64"}},
    )
    assert response.status_code == 409
    assert "base64-encoded casualty JSON" in response.json()["detail"]


def test_eventarc_native_label_requires_cloud_run_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("K_SERVICE", "cargo-release-controller")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    assert (
        eventarc_truth_mode(
            event_id="evt-1",
            event_source="//pubsub.googleapis.com/projects/demo-project/topics/casualties",
            trace_context="0123456789abcdef0123456789abcdef/1;o=1",
        )
        is TruthMode.NATIVE
    )
    assert (
        eventarc_truth_mode(
            event_id="evt-unsampled",
            event_source="//pubsub.googleapis.com/projects/demo-project/topics/casualties",
            trace_context="fedcba98765432100123456789abcdef/3784152388714607850",
        )
        is TruthMode.NATIVE
    )
    assert (
        eventarc_truth_mode(
            event_id="evt-1", event_source="//pubsub.googleapis.com", trace_context=None
        )
        is TruthMode.FIXTURE
    )
    assert (
        eventarc_truth_mode(
            event_id="evt-malformed-trace",
            event_source="//pubsub.googleapis.com/projects/demo-project/topics/casualties",
            trace_context="fedcba98765432100123456789abcde/decimal-span",
        )
        is TruthMode.FIXTURE
    )
    assert (
        eventarc_truth_mode(
            event_id="evt-synthetic",
            event_source="//cargo-release.local/phase3-concurrency-proof",
            trace_context="0123456789abcdef0123456789abcdef/1;o=1",
        )
        is TruthMode.FIXTURE
    )
