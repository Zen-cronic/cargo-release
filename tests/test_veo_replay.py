from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

from cargo_release.api import create_app
from cargo_release.models import MissionSnapshot, TruthMode
from cargo_release.veo_replay import (
    DEFAULT_VEO_MODEL,
    FixtureVeoReplay,
    VeoInvocation,
    VertexVeoReplay,
    parse_gcs_uri,
)
from tests.asgi_client import ASGITestClient


class FailingVeoReplay:
    enabled = True
    model_id = DEFAULT_VEO_MODEL
    location = "us-central1"
    truth_mode = TruthMode.NATIVE

    def generate(self, snapshot: MissionSnapshot) -> VeoInvocation:
        del snapshot
        raise TimeoutError("synthetic Veo timeout")


def released_snapshot(client: ASGITestClient) -> dict[str, object]:
    snapshot = client.post("/v1/missions/demo").json()
    mission_id = snapshot["mission"]["id"]
    snapshot = client.post(f"/v1/missions/{mission_id}:run").json()
    response = client.post(
        f"/v1/missions/{mission_id}/approvals/owner-bond:approve-and-resume",
        json={
            "expected_version": snapshot["mission"]["version"],
            "actor": "cargo-owner.demo",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_fixture_replay_runs_only_after_release_without_authority(tmp_path: Path) -> None:
    port = FixtureVeoReplay()
    client = ASGITestClient(create_app(str(tmp_path / "veo.db"), veo_replay=port))
    before = released_snapshot(client)
    mission_id = before["mission"]["id"]
    release_version = before["mission"]["version"]

    response = client.post(
        f"/v1/missions/{mission_id}/models/veo-replay:generate",
        json={"confirm_training_only": True, "actor": "operator.demo"},
    )

    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["mission"]["release_state"] == "RELEASED"
    assert snapshot["mission"]["version"] == release_version
    assert port.calls == 1
    receipt = snapshot["model_receipts"][0]
    assert receipt["kind"] == "VEO_POST_RELEASE_REPLAY"
    assert receipt["status"] == "COMPLETED"
    assert receipt["release_authority"] is False
    assert receipt["result"]["training_only"] is True
    assert receipt["result"]["generated_after_release"] is True
    assert receipt["result"]["evidence"] is False
    assert receipt["result"]["safety_filtered_count"] == 0

    repeated = client.post(
        f"/v1/missions/{mission_id}/models/veo-replay:generate",
        json={"confirm_training_only": True, "actor": "operator.demo"},
    )
    assert repeated.status_code == 200
    assert port.calls == 1
    assert len(repeated.json()["model_receipts"]) == 1


def test_replay_requires_confirmation_and_terminal_state(tmp_path: Path) -> None:
    port = FixtureVeoReplay()
    client = ASGITestClient(create_app(str(tmp_path / "guard.db"), veo_replay=port))
    snapshot = client.post("/v1/missions/demo").json()
    mission_id = snapshot["mission"]["id"]

    unconfirmed = client.post(
        f"/v1/missions/{mission_id}/models/veo-replay:generate",
        json={"confirm_training_only": False},
    )
    too_early = client.post(
        f"/v1/missions/{mission_id}/models/veo-replay:generate",
        json={"confirm_training_only": True},
    )

    assert unconfirmed.status_code == 409
    assert "not evidence or authority" in unconfirmed.json()["detail"]
    assert too_early.status_code == 409
    assert "committed RELEASED state" in too_early.json()["detail"]
    assert port.calls == 0


def test_veo_failure_is_visible_and_cannot_change_release(tmp_path: Path) -> None:
    client = ASGITestClient(
        create_app(
            str(tmp_path / "degraded.db"),
            veo_replay=FailingVeoReplay(),
        )
    )
    before = released_snapshot(client)
    mission_id = before["mission"]["id"]

    snapshot = client.post(
        f"/v1/missions/{mission_id}/models/veo-replay:generate",
        json={"confirm_training_only": True},
    ).json()

    assert snapshot["mission"]["release_state"] == "RELEASED"
    assert snapshot["mission"]["version"] == before["mission"]["version"]
    receipt = snapshot["model_receipts"][0]
    assert receipt["status"] == "DEGRADED"
    assert receipt["result"]["error_type"] == "TimeoutError"
    assert receipt["result"]["release_affected"] is False
    assert receipt["release_authority"] is False


def test_vertex_veo_launches_polls_and_digests_private_media(tmp_path: Path) -> None:
    snapshot = MissionSnapshot.model_validate(
        released_snapshot(ASGITestClient(create_app(str(tmp_path / "vertex.db"))))
    )
    requests: list[httpx.Request] = []
    media = b"synthetic-c2pa-veo-media"
    operation_name = (
        "projects/ata-2026-cargo/locations/us-central1/publishers/google/models/"
        "veo-3.1-fast-generate-001/operations/managed-veo-1"
    )

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=media, headers={"content-type": "video/mp4"})
        if request.url.path.endswith(":predictLongRunning"):
            return httpx.Response(200, json={"name": operation_name})
        return httpx.Response(
            200,
            json={
                "name": operation_name,
                "done": True,
                "response": {
                    "raiMediaFilteredCount": 0,
                    "videos": [
                        {
                            "gcsUri": (
                                "gs://cargo-runtime/post-release-media/mission-1/run-1/"
                                "sample_0.mp4"
                            ),
                            "mimeType": "video/mp4",
                        }
                    ],
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        invocation = VertexVeoReplay(
            "ata-2026-cargo",
            "gs://cargo-runtime/post-release-media/",
            client=http_client,
            token_provider=lambda: "ephemeral-test-token",
            poll_interval_seconds=0,
            sleeper=lambda _seconds: None,
        ).generate(snapshot)

    assert len(requests) == 3
    launch_body = json.loads(requests[0].content)
    assert "enhancePrompt" not in launch_body["parameters"]
    assert launch_body["parameters"] == {
        "storageUri": launch_body["parameters"]["storageUri"],
        "sampleCount": 1,
        "durationSeconds": 4,
        "aspectRatio": "16:9",
        "resolution": "720p",
        "generateAudio": False,
        "personGeneration": "dont_allow",
        "seed": 20260825,
    }
    assert launch_body["parameters"]["storageUri"].startswith(
        "gs://cargo-runtime/post-release-media/"
    )
    assert invocation.request_ref == operation_name
    assert invocation.result["asset_sha256"] == hashlib.sha256(media).hexdigest()
    assert invocation.result["safety_filtered_count"] == 0
    assert invocation.result["release_authority"] is False
    assert requests[-1].url.params["alt"] == "media"


def test_replay_media_uri_must_stay_inside_configured_prefix() -> None:
    bucket, object_name = parse_gcs_uri(
        "gs://cargo-runtime/post-release-media/mission/sample.mp4",
        "gs://cargo-runtime/post-release-media/",
    )
    assert bucket == "cargo-runtime"
    assert object_name == "post-release-media/mission/sample.mp4"

    try:
        parse_gcs_uri(
            "gs://other-bucket/private/sample.mp4",
            "gs://cargo-runtime/post-release-media/",
        )
    except Exception as error:
        assert "outside the configured output prefix" in str(error)
    else:
        raise AssertionError("out-of-prefix replay media should be rejected")
