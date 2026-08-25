from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlparse
from uuid import uuid4

import httpx

from cargo_release.engine import DomainError
from cargo_release.models import MissionSnapshot, ReceiptKind, ReleaseState, TruthMode, utc_now
from cargo_release.store import MissionStore

SYNTHETIC_BANNER = "SYNTHETIC DEMO — NO REAL CARGO ACTION"
RELEASE_NOTICE_KIND = "RELEASE_OPERATOR_NOTICE"
SLACK_WEBHOOK_HOSTS = frozenset({"hooks.slack.com", "hooks.slack-gov.com"})


class NotificationError(DomainError):
    pass


@dataclass(frozen=True)
class OutboundNotificationReceipt:
    endpoint_label: str
    provider_ref: str
    payload_digest: str
    truth_mode: TruthMode
    status: str
    delivered_at: str


class OperatorNotificationPort(Protocol):
    enabled: bool

    def deliver_release(self, snapshot: MissionSnapshot) -> OutboundNotificationReceipt: ...


class DisabledOperatorNotification:
    enabled = False

    def deliver_release(self, snapshot: MissionSnapshot) -> OutboundNotificationReceipt:
        del snapshot
        raise NotificationError("Synthetic operator notification is not configured")


class SlackWebhookNotification:
    enabled = True

    def __init__(
        self,
        webhook_url: str,
        endpoint_label: str,
        *,
        public_base_url: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        parsed = urlparse(webhook_url)
        if parsed.scheme != "https" or parsed.hostname not in SLACK_WEBHOOK_HOSTS:
            raise NotificationError(
                "Slack webhook must use HTTPS on hooks.slack.com or hooks.slack-gov.com"
            )
        if not endpoint_label.strip():
            raise NotificationError("CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL is required")
        self._webhook_url = webhook_url
        self.endpoint_label = endpoint_label.strip()
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self._client = client

    def _payload(self, snapshot: MissionSnapshot, delivery_ref: str) -> dict[str, object]:
        readback = next(
            item for item in snapshot.receipts if item.kind is ReceiptKind.CARRIER_RELEASE_READBACK
        )
        mission_url = (
            f"{self.public_base_url}/?mission={quote(snapshot.mission.id)}"
            if self.public_base_url
            else None
        )
        lines = [
            f"🧪 *{SYNTHETIC_BANNER}*",
            "Cargo Release verified a synthetic carrier read-back.",
            f"• Mission: `{snapshot.mission.id}`",
            f"• Case: `{snapshot.mission.case_ref}`",
            f"• Container: `{snapshot.mission.container_ref}`",
            f"• Carrier read-back: `{readback.external_id}`",
            f"• Cargo state: *{snapshot.mission.release_state}*",
            f"• Adjustment state: *{snapshot.mission.adjustment_state}*",
            f"• Delivery reference: `{delivery_ref}`",
        ]
        if mission_url:
            lines.append(f"• Mission room: {mission_url}")
        lines.append("This is hackathon demo traffic. It did not release real cargo.")
        return {
            "text": f"{SYNTHETIC_BANNER}: {snapshot.mission.case_ref}",
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(lines)},
                }
            ],
            "unfurl_links": False,
            "unfurl_media": False,
        }

    def deliver_release(self, snapshot: MissionSnapshot) -> OutboundNotificationReceipt:
        delivery_ref = f"slack-{uuid4().hex[:16]}"
        payload = self._payload(snapshot, delivery_ref)
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload_digest = hashlib.sha256(payload_json.encode()).hexdigest()
        if self._client is None:
            with httpx.Client(timeout=15) as client:
                response = client.post(self._webhook_url, json=payload)
        else:
            response = self._client.post(self._webhook_url, json=payload)
        response.raise_for_status()
        if response.text.strip().lower() != "ok":
            raise NotificationError("Slack did not acknowledge the synthetic notification")
        return OutboundNotificationReceipt(
            endpoint_label=self.endpoint_label,
            provider_ref=delivery_ref,
            payload_digest=payload_digest,
            truth_mode=TruthMode.ADAPTER,
            status="DELIVERED",
            delivered_at=utc_now(),
        )


class MissionNotificationService:
    def __init__(self, store: MissionStore, port: OperatorNotificationPort) -> None:
        self.store = store
        self.port = port

    @staticmethod
    def _existing(snapshot: MissionSnapshot) -> bool:
        return any(item.kind == RELEASE_NOTICE_KIND for item in snapshot.notifications)

    def maybe_deliver_release(
        self, mission_id: str, *, actor: str = "system:release-notifier@1.0.0"
    ) -> MissionSnapshot:
        snapshot = self.store.snapshot(mission_id)
        if not self.port.enabled or snapshot.mission.release_state is not ReleaseState.RELEASED:
            return snapshot
        return self.deliver_release(mission_id, confirm_synthetic=True, actor=actor)[0]

    def deliver_release(
        self,
        mission_id: str,
        *,
        confirm_synthetic: bool,
        actor: str,
    ) -> tuple[MissionSnapshot, bool]:
        if not confirm_synthetic:
            raise NotificationError(
                "confirm_synthetic=true is required; real cargo notifications are out of scope"
            )
        if not self.port.enabled:
            raise NotificationError("Synthetic operator notification is not configured")

        snapshot = self.store.snapshot(mission_id)
        if self._existing(snapshot):
            return snapshot, False
        if snapshot.mission.release_state is not ReleaseState.RELEASED:
            raise NotificationError("Carrier release read-back is required before notification")
        if not any(item.kind is ReceiptKind.CARRIER_RELEASE_READBACK for item in snapshot.receipts):
            raise NotificationError("Verified carrier release read-back receipt is missing")

        lease_owner = f"notification-{uuid4().hex[:12]}"
        if not self.store.acquire_lease(mission_id, lease_owner, ttl_seconds=30):
            raise NotificationError("Mission has an active operation; retry notification")
        try:
            snapshot = self.store.snapshot(mission_id)
            if self._existing(snapshot):
                return snapshot, False
            receipt = self.port.deliver_release(snapshot)
            snapshot, created = self.store.record_notification_delivery(
                mission_id,
                kind=RELEASE_NOTICE_KIND,
                endpoint_label=receipt.endpoint_label,
                provider_ref=receipt.provider_ref,
                payload_digest=receipt.payload_digest,
                truth_mode=receipt.truth_mode,
                status=receipt.status,
                delivered_at=receipt.delivered_at,
                actor=actor,
            )
            if created:
                self.store.record_trace(
                    mission_id,
                    "release-notifier@1.0.0",
                    "deliver_marked_synthetic_release_notice",
                    receipt.truth_mode,
                    "DELIVERED",
                    {
                        "endpoint_label": receipt.endpoint_label,
                        "provider_ref": receipt.provider_ref,
                        "payload_digest": receipt.payload_digest,
                        "truth_mode": receipt.truth_mode,
                        "synthetic": True,
                        "release_authority": False,
                    },
                )
                snapshot = self.store.snapshot(mission_id)
            return snapshot, created
        finally:
            self.store.release_lease(mission_id, lease_owner)


def build_notification_port() -> OperatorNotificationPort:
    if os.getenv("CARGO_RELEASE_SYNTHETIC_NOTIFICATION_ENABLED") != "1":
        return DisabledOperatorNotification()
    webhook_url = os.getenv("CARGO_RELEASE_NOTIFICATION_WEBHOOK_URL")
    endpoint_label = os.getenv("CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL")
    if not webhook_url or not endpoint_label:
        raise NotificationError(
            "Synthetic notifications require webhook URL and non-secret endpoint label"
        )
    return SlackWebhookNotification(
        webhook_url,
        endpoint_label,
        public_base_url=os.getenv("CARGO_RELEASE_PUBLIC_BASE_URL"),
    )
