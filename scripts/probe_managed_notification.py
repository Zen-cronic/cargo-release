from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from typing import Any

import httpx


def identity_token() -> str:
    result = subprocess.run(
        ["gcloud", "auth", "print-identity-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one managed fixture mission and prove marked Slack delivery."
    )
    parser.add_argument(
        "--controller-url",
        default="https://cargo-release-controller-1015646664425.us-central1.run.app",
    )
    parser.add_argument("--event-id", required=True)
    args = parser.parse_args()

    token = identity_token()
    headers = {"authorization": f"Bearer {token}"}
    casualty = {
        "source_ref": "SYNTHETIC/PHASE4/OPERATOR-NOTIFICATION",
        "vessel": "MV Northstar",
        "container_ref": "TCLU-482019-7",
    }
    envelope = {
        "message": {
            "data": base64.b64encode(json.dumps(casualty).encode()).decode(),
            "messageId": "synthetic-notification-proof",
            "attributes": {"schema": "casualty-declared-v1", "synthetic": "true"},
        },
        "subscription": "synthetic://phase4/operator-notification-proof",
    }
    cloud_event_headers = {
        **headers,
        "content-type": "application/json",
        "ce-id": args.event_id,
        "ce-source": "//cargo-release.local/phase4-operator-notification-proof",
        "ce-type": "com.cargorelease.synthetic.operator-notification.v1",
        "x-cloud-trace-context": "1123456789abcdef0123456789abcdef/1;o=1",
    }

    with httpx.Client(base_url=args.controller_url.rstrip("/"), timeout=120) as client:
        held_response = client.post(
            "/v1/events/casualty",
            headers=cloud_event_headers,
            json=envelope,
        )
        held_response.raise_for_status()
        held = held_response.json()
        mission_id = held["mission"]["id"]
        expected_id = f"mission-{hashlib.sha256(args.event_id.encode()).hexdigest()[:12]}"
        if mission_id != expected_id or held["mission"]["release_state"] != "READY_FOR_SIGNATURE":
            raise RuntimeError("Managed mission did not stop at the human owner-bond gate")

        release_response = client.post(
            f"/v1/missions/{mission_id}/approvals/owner-bond:approve-and-resume",
            headers={**headers, "content-type": "application/json"},
            json={
                "expected_version": held["mission"]["version"],
                "actor": "cargo-owner.synthetic-notification-proof",
            },
        )
        release_response.raise_for_status()
        released: dict[str, Any] = release_response.json()

        retry_response = client.post(
            f"/v1/missions/{mission_id}/notifications/release",
            headers={**headers, "content-type": "application/json"},
            json={
                "confirm_synthetic": True,
                "actor": "operator.synthetic-notification-retry-proof",
            },
        )
        retry_response.raise_for_status()
        retry = retry_response.json()

    notifications = released["notifications"]
    delivery_events = [
        item
        for item in released["events"]
        if item["event_type"] == "SYNTHETIC_NOTIFICATION_DELIVERED"
    ]
    delivery_traces = [
        item
        for item in released["traces"]
        if item["operation"] == "deliver_marked_synthetic_release_notice"
    ]
    if (
        released["mission"]["release_state"] != "RELEASED"
        or released["mission"]["adjustment_state"] != "OPEN"
        or released["mission"]["truth_mode"] != "FIXTURE"
        or len(notifications) != 1
        or notifications[0]["truth_mode"] != "ADAPTER"
        or len(delivery_events) != 1
        or len(delivery_traces) != 1
        or retry["created"] is not False
    ):
        raise RuntimeError("Managed notification acceptance invariants failed")

    notification = notifications[0]
    print(
        json.dumps(
            {
                "adjustment_state": released["mission"]["adjustment_state"],
                "delivery_event_hash": delivery_events[0]["event_hash"],
                "endpoint_label": notification["endpoint_label"],
                "event_id": args.event_id,
                "mission_id": mission_id,
                "payload_digest": notification["payload_digest"],
                "provider_ref": notification["provider_ref"],
                "release_state": released["mission"]["release_state"],
                "retry_created": retry["created"],
                "status": notification["status"],
                "truth_mode": released["mission"]["truth_mode"],
                "notification_truth_mode": notification["truth_mode"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
