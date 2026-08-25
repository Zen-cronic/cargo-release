from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from typing import Any

import httpx

GEMMA_KIND = "GEMMA_RELEASE_CRITIC"
EMBEDDING_KIND = "GEMINI_EMBEDDING_RETRIEVAL"
VEO_KIND = "VEO_POST_RELEASE_REPLAY"


def identity_token() -> str:
    result = subprocess.run(
        ["gcloud", "auth", "print-identity-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty identity token")
    return token


def model_receipt(snapshot: dict[str, Any], kind: str) -> dict[str, Any]:
    matches = [item for item in snapshot.get("model_receipts", []) if item.get("kind") == kind]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {kind} receipt, found {len(matches)}")
    return matches[0]


def model_trace(
    snapshot: dict[str, Any], operation: str, *, truth_mode: str = "NATIVE"
) -> dict[str, Any]:
    matches = [item for item in snapshot.get("traces", []) if item.get("operation") == operation]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {operation} trace, found {len(matches)}")
    trace = matches[0]
    if (
        trace.get("truth_mode") != truth_mode
        or trace.get("status") != "COMPLETED"
        or trace.get("detail", {}).get("release_authority") is not False
        or trace.get("detail", {}).get("release_affected") is not False
    ):
        raise RuntimeError(f"Managed model trace failed its authority boundary: {trace}")
    return trace


def require_common_model_boundary(
    receipt: dict[str, Any],
    *,
    model_id: str,
    location: str,
    truth_mode: str = "NATIVE",
) -> None:
    if (
        receipt.get("model_id") != model_id
        or receipt.get("location") != location
        or receipt.get("status") != "COMPLETED"
        or receipt.get("truth_mode") != truth_mode
        or receipt.get("release_authority") is not False
        or not receipt.get("request_ref")
        or len(str(receipt.get("input_digest", ""))) != 64
        or len(str(receipt.get("output_digest", ""))) != 64
    ):
        raise RuntimeError(f"Managed model receipt failed its common boundary: {receipt}")


def validate_human_gate(
    snapshot: dict[str, Any],
    *,
    truth_mode: str = "NATIVE",
    gemma_location: str = "global",
    embedding_location: str = "global",
    require_gemma_tool_marker: bool = True,
) -> None:
    if (
        snapshot["mission"]["release_state"] != "READY_FOR_SIGNATURE"
        or snapshot["mission"]["version"] != 1
        or snapshot["approvals"]
        or snapshot["receipts"]
    ):
        raise RuntimeError("Mission did not remain at the untouched human gate")

    gemma = model_receipt(snapshot, GEMMA_KIND)
    require_common_model_boundary(
        gemma,
        model_id="google/gemma-4-26b-a4b-it-maas",
        location=gemma_location,
        truth_mode=truth_mode,
    )
    if require_gemma_tool_marker and gemma["result"].get("tool_calls_exposed") is not False:
        raise RuntimeError("Gemma receipt did not prove its no-tools boundary")
    if (
        require_gemma_tool_marker
        and gemma["result"].get("prompt_version") != "cargo-release-critic-v1"
    ):
        raise RuntimeError("Gemma receipt did not retain the accepted prompt version")
    model_trace(
        snapshot,
        "review_release_packet_non_authoritative",
        truth_mode=truth_mode,
    )

    embedding = model_receipt(snapshot, EMBEDDING_KIND)
    require_common_model_boundary(
        embedding,
        model_id="gemini-embedding-2",
        location=embedding_location,
        truth_mode=truth_mode,
    )
    embedding_result = embedding["result"]
    if (
        embedding_result.get("release_authority") is not False
        or embedding_result.get("release_affected") is not False
        or embedding_result.get("confidence_percentages_exposed") is not False
        or embedding_result.get("corpus_version") != "cargo-reviewed-cases-v1"
        or embedding_result.get("dimensions") != 128
        or len(embedding_result.get("top_cases", [])) != 3
        or "score" in json.dumps(embedding_result).lower()
    ):
        raise RuntimeError("Embedding receipt violated the rank-only boundary")
    model_trace(
        snapshot,
        "rank_reviewed_synthetic_cases_non_authoritative",
        truth_mode=truth_mode,
    )


def validate_veo_replay(
    released: dict[str, Any],
    replayed: dict[str, Any],
    *,
    truth_mode: str = "NATIVE",
    location: str = "us-central1",
    asset_prefix: str = "gs://ata-2026-cargo-cargo-release-runtime/post-release-media/",
) -> dict[str, Any]:
    if (
        released["mission"]["release_state"] != "RELEASED"
        or replayed["mission"]["release_state"] != "RELEASED"
        or replayed["mission"]["version"] != released["mission"]["version"]
    ):
        raise RuntimeError("Veo replay changed or preceded deterministic release authority")

    veo = model_receipt(replayed, VEO_KIND)
    require_common_model_boundary(
        veo,
        model_id="veo-3.1-fast-generate-001",
        location=location,
        truth_mode=truth_mode,
    )
    result = veo["result"]
    if (
        result.get("generated_after_release") is not True
        or result.get("training_only") is not True
        or result.get("evidence") is not False
        or result.get("release_authority") is not False
        or result.get("fallback_used") is not False
        or result.get("safety_filtered_count") != 0
        or result.get("prompt_version") != "cargo-post-release-replay-v1"
        or len(str(result.get("asset_sha256", ""))) != 64
        or not str(result.get("asset_uri", "")).startswith(asset_prefix)
    ):
        raise RuntimeError("Veo receipt violated the post-release training-only boundary")
    model_trace(
        replayed,
        "generate_synthetic_training_replay_after_release",
        truth_mode=truth_mode,
    )
    return veo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove all three managed bonus models without granting release authority."
    )
    parser.add_argument(
        "--controller-url",
        default="https://cargo-release-controller-1015646664425.us-central1.run.app",
    )
    parser.add_argument("--event-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = identity_token()
    auth_headers = {"authorization": f"Bearer {token}"}
    casualty = {
        "source_ref": "SYNTHETIC/COMBINED-MODELS/MANAGED-PROOF",
        "vessel": "MV Northstar",
        "container_ref": "TCLU-482019-7",
    }
    envelope = {
        "message": {
            "data": base64.b64encode(json.dumps(casualty).encode()).decode(),
            "messageId": "synthetic-combined-model-proof",
            "attributes": {"schema": "casualty-declared-v1", "synthetic": "true"},
        },
        "subscription": "synthetic://combined-models/managed-proof",
    }
    event_headers = {
        **auth_headers,
        "content-type": "application/json",
        "ce-id": args.event_id,
        "ce-source": "//cargo-release.local/combined-model-proof",
        "ce-type": "com.cargorelease.synthetic.combined-model-proof.v1",
        "x-cloud-trace-context": "2123456789abcdef0123456789abcdef/1;o=1",
    }
    timeout = httpx.Timeout(900, connect=30)

    with httpx.Client(base_url=args.controller_url.rstrip("/"), timeout=timeout) as client:
        health_response = client.get("/health", headers=auth_headers)
        health_response.raise_for_status()
        health = health_response.json()
        if health.get("database") != "postgresql":
            raise RuntimeError("Managed controller is not using PostgreSQL authority")

        held_response = client.post("/v1/events/casualty", headers=event_headers, json=envelope)
        held_response.raise_for_status()
        held: dict[str, Any] = held_response.json()
        mission_id = held["mission"]["id"]
        expected_id = f"mission-{hashlib.sha256(args.event_id.encode()).hexdigest()[:12]}"
        if mission_id != expected_id:
            raise RuntimeError("Managed event did not produce its deterministic mission ID")
        validate_human_gate(held)

        release_response = client.post(
            f"/v1/missions/{mission_id}/approvals/owner-bond:approve-and-resume",
            headers={**auth_headers, "content-type": "application/json"},
            json={
                "expected_version": held["mission"]["version"],
                "actor": "cargo-owner.combined-model-proof",
            },
        )
        release_response.raise_for_status()
        released: dict[str, Any] = release_response.json()
        if released.get("notifications"):
            raise RuntimeError("Delivery-disabled deployment unexpectedly sent a notification")

        replay_response = client.post(
            f"/v1/missions/{mission_id}/models/veo-replay:generate",
            headers={**auth_headers, "content-type": "application/json"},
            json={
                "confirm_training_only": True,
                "actor": "operator.combined-model-proof",
            },
        )
        replay_response.raise_for_status()
        replayed: dict[str, Any] = replay_response.json()
        veo = validate_veo_replay(released, replayed)
        if {item["kind"] for item in replayed["model_receipts"]} != {
            GEMMA_KIND,
            EMBEDDING_KIND,
            VEO_KIND,
        }:
            raise RuntimeError("Combined proof did not retain exactly the three model products")

        media_response = client.get(
            f"/v1/missions/{mission_id}/models/veo-replay/media",
            headers=auth_headers,
        )
        media_response.raise_for_status()
        media_digest = hashlib.sha256(media_response.content).hexdigest()
        if (
            media_response.headers.get("content-type") != "video/mp4"
            or media_digest != veo["result"].get("asset_sha256")
        ):
            raise RuntimeError("Private replay relay did not match the retained media digest")

        retry_response = client.post(
            f"/v1/missions/{mission_id}/models/veo-replay:generate",
            headers={**auth_headers, "content-type": "application/json"},
            json={
                "confirm_training_only": True,
                "actor": "operator.combined-model-idempotency-proof",
            },
        )
        retry_response.raise_for_status()
        retry: dict[str, Any] = retry_response.json()
        model_receipt(retry, VEO_KIND)

    print(
        json.dumps(
            {
                "database": health["database"],
                "embedding_request_ref": model_receipt(held, EMBEDDING_KIND)["request_ref"],
                "event_id": args.event_id,
                "gemma_request_ref": model_receipt(held, GEMMA_KIND)["request_ref"],
                "media_sha256": media_digest,
                "mission_id": mission_id,
                "model_receipts": len(replayed["model_receipts"]),
                "notification_count": len(replayed.get("notifications", [])),
                "release_state": replayed["mission"]["release_state"],
                "release_version": replayed["mission"]["version"],
                "veo_operation": veo["request_ref"],
                "veo_retry_receipts": len(
                    [item for item in retry["model_receipts"] if item["kind"] == VEO_KIND]
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
