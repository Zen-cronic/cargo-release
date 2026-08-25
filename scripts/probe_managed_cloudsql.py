from __future__ import annotations

import argparse
import base64
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
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
        description="Prove managed duplicate-CloudEvent safety against Cloud SQL."
    )
    parser.add_argument(
        "--controller-url",
        default="https://cargo-release-controller-1015646664425.us-central1.run.app",
    )
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--deliveries", type=int, default=6)
    args = parser.parse_args()

    token = identity_token()
    casualty = {
        "source_ref": "SYNTHETIC/PHASE3/DUPLICATE",
        "vessel": "MV Northstar",
        "container_ref": "TCLU-482019-7",
    }
    envelope = {
        "message": {
            "data": base64.b64encode(json.dumps(casualty).encode()).decode(),
            "messageId": "synthetic-duplicate-proof",
            "attributes": {"schema": "casualty-declared-v1", "synthetic": "true"},
        },
        "subscription": "synthetic://phase3/cloudsql-concurrency-proof",
    }
    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "ce-id": args.event_id,
        "ce-source": "//cargo-release.local/phase3-concurrency-proof",
        "ce-type": "com.cargorelease.synthetic.duplicate-proof.v1",
        "x-cloud-trace-context": "0123456789abcdef0123456789abcdef/1;o=1",
    }

    def deliver(_index: int) -> tuple[int, dict[str, Any]]:
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{args.controller_url.rstrip('/')}/v1/events/casualty",
                headers=headers,
                json=envelope,
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=args.deliveries) as executor:
        results = list(executor.map(deliver, range(args.deliveries)))

    statuses = [status for status, _ in results]
    if any(status != 200 for status in statuses):
        raise RuntimeError(f"Concurrent deliveries failed: {statuses}")
    mission_ids = {body["mission"]["id"] for _, body in results}
    if len(mission_ids) != 1:
        raise RuntimeError(f"Duplicate event produced multiple missions: {mission_ids}")

    mission_id = mission_ids.pop()
    with httpx.Client(timeout=30) as client:
        health_response = client.get(
            f"{args.controller_url.rstrip('/')}/health",
            headers={"authorization": f"Bearer {token}"},
        )
        snapshot_response = client.get(
            f"{args.controller_url.rstrip('/')}/v1/missions/{mission_id}",
            headers={"authorization": f"Bearer {token}"},
        )
    health_response.raise_for_status()
    snapshot_response.raise_for_status()
    health = health_response.json()
    snapshot = snapshot_response.json()
    declared_events = [
        event for event in snapshot["events"] if event["event_type"] == "MISSION_DECLARED"
    ]
    if len(declared_events) != 1 or len(snapshot["runs"]) != 1:
        raise RuntimeError(
            "Duplicate delivery was not idempotent: "
            f"declared_events={len(declared_events)}, runs={len(snapshot['runs'])}"
        )

    print(
        json.dumps(
            {
                "database": health["database"],
                "deliveries": args.deliveries,
                "event_id": args.event_id,
                "mission_declared_events": len(declared_events),
                "mission_id": mission_id,
                "release_state": snapshot["mission"]["release_state"],
                "runs": len(snapshot["runs"]),
                "statuses": statuses,
                "truth_mode": snapshot["mission"]["truth_mode"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
