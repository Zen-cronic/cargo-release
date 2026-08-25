from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from cargo_release.api import create_app
from cargo_release.models import MissionSnapshot, TruthMode, utc_now
from cargo_release.notification import (
    SYNTHETIC_BANNER,
    NotificationError,
    OutboundNotificationReceipt,
    SlackWebhookNotification,
)
from tests.asgi_client import ASGITestClient


class RecordingNotificationPort:
    enabled = True

    def __init__(self) -> None:
        self.calls: list[MissionSnapshot] = []

    def deliver_release(self, snapshot: MissionSnapshot) -> OutboundNotificationReceipt:
        self.calls.append(snapshot)
        return OutboundNotificationReceipt(
            endpoint_label="operator-owned Slack #cargo-release-demo",
            provider_ref="slack-test-receipt",
            payload_digest="a" * 64,
            truth_mode=TruthMode.FIXTURE,
            status="DELIVERED",
            delivered_at=utc_now(),
        )


def release_mission(client: ASGITestClient) -> MissionSnapshot:
    snapshot = client.post("/v1/missions/demo").json()
    mission_id = snapshot["mission"]["id"]
    held = client.post(f"/v1/missions/{mission_id}:run").json()
    response = client.post(
        f"/v1/missions/{mission_id}/approvals/owner-bond:approve-and-resume",
        json={
            "expected_version": held["mission"]["version"],
            "actor": "cargo-owner.test",
        },
    )
    assert response.status_code == 200
    return MissionSnapshot.model_validate(response.json())


def test_release_notification_is_post_readback_marked_and_idempotent(tmp_path: Path) -> None:
    port = RecordingNotificationPort()
    client = ASGITestClient(
        create_app(str(tmp_path / "notification.db"), notification_port=port)
    )

    snapshot = release_mission(client)

    assert snapshot.mission.release_state == "RELEASED"
    assert len(port.calls) == 1
    assert any(receipt.kind == "CARRIER_RELEASE_READBACK" for receipt in port.calls[0].receipts)
    assert [item.kind for item in snapshot.notifications] == ["RELEASE_OPERATOR_NOTICE"]
    assert snapshot.notifications[0].endpoint_label == "operator-owned Slack #cargo-release-demo"
    assert snapshot.notifications[0].truth_mode is TruthMode.FIXTURE
    event = next(
        item for item in snapshot.events if item.event_type == "SYNTHETIC_NOTIFICATION_DELIVERED"
    )
    assert event.payload["truth_mode"] == "FIXTURE"
    trace = next(
        item
        for item in snapshot.traces
        if item.operation == "deliver_marked_synthetic_release_notice"
    )
    assert trace.truth_mode is TruthMode.FIXTURE
    assert trace.detail["synthetic"] is True
    assert trace.detail["release_authority"] is False

    repeated = client.post(
        f"/v1/missions/{snapshot.mission.id}/notifications/release",
        json={"confirm_synthetic": True, "actor": "operator.retry"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert len(port.calls) == 1


def test_notification_fails_closed_before_release_or_without_confirmation(tmp_path: Path) -> None:
    port = RecordingNotificationPort()
    client = ASGITestClient(create_app(str(tmp_path / "guard.db"), notification_port=port))
    snapshot = client.post("/v1/missions/demo").json()
    path = f"/v1/missions/{snapshot['mission']['id']}/notifications/release"

    missing_confirmation = client.post(path, json={"confirm_synthetic": False})
    assert missing_confirmation.status_code == 409
    assert "confirm_synthetic=true" in missing_confirmation.json()["detail"]

    before_release = client.post(path, json={"confirm_synthetic": True})
    assert before_release.status_code == 409
    assert "read-back is required" in before_release.json()["detail"]
    assert port.calls == []


def test_slack_payload_is_prominently_synthetic_and_retains_no_webhook(
    tmp_path: Path,
) -> None:
    snapshot = release_mission(ASGITestClient(create_app(str(tmp_path / "payload.db"))))
    requests: list[httpx.Request] = []

    def acknowledge(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    with httpx.Client(transport=httpx.MockTransport(acknowledge)) as client:
        port = SlackWebhookNotification(
            "https://hooks.slack.com/services/T000/B000/secret",
            "operator-owned Slack #cargo-release-demo",
            public_base_url="https://cargo-release.example",
            client=client,
        )
        receipt = port.deliver_release(snapshot)

    assert receipt.status == "DELIVERED"
    assert receipt.truth_mode is TruthMode.ADAPTER
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    rendered = json.dumps(payload, ensure_ascii=False)
    assert SYNTHETIC_BANNER in rendered
    assert "did not release real cargo" in rendered
    assert snapshot.mission.id in rendered
    assert "hooks.slack.com" not in rendered


def test_slack_webhook_host_is_allowlisted() -> None:
    with pytest.raises(NotificationError, match="hooks.slack.com"):
        SlackWebhookNotification(
            "https://webhook.attacker.example/capture",
            "operator channel",
        )
