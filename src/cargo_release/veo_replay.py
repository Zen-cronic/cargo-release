from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from typing import Any, Protocol, cast
from urllib.parse import quote
from uuid import uuid4

import httpx

from cargo_release.engine import DomainError
from cargo_release.gemma_critic import _access_token
from cargo_release.models import (
    MissionSnapshot,
    ModelReceipt,
    ModelReceiptStatus,
    ReceiptKind,
    ReleaseState,
    TruthMode,
)
from cargo_release.store import MissionStore

VEO_REPLAY_KIND = "VEO_POST_RELEASE_REPLAY"
VEO_REPLAY_PROMPT_VERSION = "cargo-post-release-replay-v1"
DEFAULT_VEO_MODEL = "veo-3.1-fast-generate-001"
DEFAULT_VEO_LOCATION = "us-central1"
VEO_REPLAY_LABEL = "SYNTHETIC REPLAY — NOT EVIDENCE — GENERATED AFTER RELEASE"


class VeoReplayError(DomainError):
    pass


class VeoInvocation:
    def __init__(
        self,
        *,
        request_ref: str,
        input_digest: str,
        output_digest: str,
        result: dict[str, Any],
    ) -> None:
        self.request_ref = request_ref
        self.input_digest = input_digest
        self.output_digest = output_digest
        self.result = result


class VeoReplayPort(Protocol):
    enabled: bool
    model_id: str
    location: str
    truth_mode: TruthMode

    def generate(self, snapshot: MissionSnapshot) -> VeoInvocation: ...


def _digest(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode()).hexdigest()


def replay_prompt(snapshot: MissionSnapshot) -> str:
    return (
        "Create an abstract synthetic training visualization of a teal intermodal cargo container "
        "at a fictional port checkpoint after a completed General Average release workflow. "
        "Show three clean geometric verification pulses followed by the container doors opening "
        "slightly under calm blue-green light. No people, logos, brands, documents, signatures, "
        "maps, readable identifiers, readable text, alarms, damage, emergency action, or "
        f"real-world instructions. Fictional vessel category: cargo ship. Terminal state: "
        f"{snapshot.mission.release_state}."
    )


def replay_packet(snapshot: MissionSnapshot, output_uri: str) -> dict[str, Any]:
    return {
        "prompt_version": VEO_REPLAY_PROMPT_VERSION,
        "prompt": replay_prompt(snapshot),
        "mission": {
            "id": snapshot.mission.id,
            "release_state": snapshot.mission.release_state,
            "version": snapshot.mission.version,
            "verified_readback": any(
                item.kind is ReceiptKind.CARRIER_RELEASE_READBACK and item.verified
                for item in snapshot.receipts
            ),
        },
        "parameters": {
            "duration_seconds": 4,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "sample_count": 1,
            "generate_audio": False,
            "person_generation": "dont_allow",
            "seed": 20260825,
            "storage_uri": output_uri,
        },
        "authority_boundary": {
            "generated_after_release": True,
            "training_only": True,
            "evidence": False,
            "release_authority": False,
        },
    }


def _asset_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_gcs_uri(uri: str, expected_prefix: str) -> tuple[str, str]:
    if not uri.startswith("gs://") or not expected_prefix.startswith("gs://"):
        raise VeoReplayError("Replay media must use a configured gs:// prefix")
    normalized_prefix = expected_prefix.rstrip("/") + "/"
    if not uri.startswith(normalized_prefix):
        raise VeoReplayError("Replay media URI is outside the configured output prefix")
    bucket_and_object = uri[5:].split("/", 1)
    if len(bucket_and_object) != 2 or not all(bucket_and_object):
        raise VeoReplayError("Replay media URI must include bucket and object")
    return bucket_and_object[0], bucket_and_object[1]


def fetch_gcs_media(
    uri: str,
    expected_prefix: str,
    *,
    client: httpx.Client | None = None,
    token_provider: Callable[[], str] = _access_token,
) -> bytes:
    bucket, object_name = parse_gcs_uri(uri, expected_prefix)
    endpoint = (
        "https://storage.googleapis.com/storage/v1/b/"
        f"{quote(bucket, safe='')}/o/{quote(object_name, safe='')}?alt=media"
    )
    headers = {"authorization": f"Bearer {token_provider()}"}
    if client is not None:
        response = client.get(endpoint, headers=headers)
    else:
        with httpx.Client(timeout=60) as http_client:
            response = http_client.get(endpoint, headers=headers)
    response.raise_for_status()
    return response.content


class DisabledVeoReplay:
    enabled = False
    model_id = DEFAULT_VEO_MODEL
    location = DEFAULT_VEO_LOCATION
    truth_mode = TruthMode.ADAPTER

    def generate(self, snapshot: MissionSnapshot) -> VeoInvocation:
        del snapshot
        raise VeoReplayError("Post-release replay is disabled")


class FixtureVeoReplay:
    enabled = True
    model_id = DEFAULT_VEO_MODEL
    location = "fixture"
    truth_mode = TruthMode.FIXTURE

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, snapshot: MissionSnapshot) -> VeoInvocation:
        self.calls += 1
        output_uri = f"fixture://veo-replay/{snapshot.mission.id}/sample_0.mp4"
        packet = replay_packet(snapshot, output_uri)
        asset_digest = _digest({"fixture": packet, "frames": 96})
        result = {
            "label": VEO_REPLAY_LABEL,
            "prompt_version": VEO_REPLAY_PROMPT_VERSION,
            "asset_uri": output_uri,
            "asset_sha256": asset_digest,
            "mime_type": "video/mp4",
            "duration_seconds": 4,
            "resolution": "1280x720",
            "fps": 24,
            "safety_filtered_count": 0,
            "generated_after_release": True,
            "training_only": True,
            "evidence": False,
            "release_authority": False,
            "fallback_used": False,
        }
        return VeoInvocation(
            request_ref=f"fixture-veo-{self.calls}",
            input_digest=_digest(packet),
            output_digest=_digest(result),
            result=result,
        )


class VertexVeoReplay:
    enabled = True
    truth_mode = TruthMode.NATIVE

    def __init__(
        self,
        project: str,
        output_uri: str,
        *,
        location: str = DEFAULT_VEO_LOCATION,
        model_id: str = DEFAULT_VEO_MODEL,
        client: httpx.Client | None = None,
        token_provider: Callable[[], str] = _access_token,
        poll_interval_seconds: float = 10,
        max_polls: int = 60,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not project:
            raise VeoReplayError("CARGO_RELEASE_MODEL_PROJECT is required")
        if location != DEFAULT_VEO_LOCATION:
            raise VeoReplayError("Veo 3.1 Fast replay is pinned to us-central1")
        if not output_uri.startswith("gs://"):
            raise VeoReplayError("CARGO_RELEASE_VEO_OUTPUT_URI must use gs://")
        if max_polls < 1 or poll_interval_seconds < 0:
            raise VeoReplayError("Veo polling configuration is invalid")
        self.project = project
        self.output_uri = output_uri.rstrip("/") + "/"
        self.location = location
        self.model_id = model_id
        self.client = client
        self.token_provider = token_provider
        self.poll_interval_seconds = poll_interval_seconds
        self.max_polls = max_polls
        self.sleeper = sleeper

    @property
    def model_endpoint(self) -> str:
        return (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{self.project}/locations/{self.location}/publishers/google/models/{self.model_id}"
        )

    def _post(self, endpoint: str, body: dict[str, Any]) -> httpx.Response:
        headers = {"authorization": f"Bearer {self.token_provider()}"}
        if self.client is not None:
            return self.client.post(endpoint, headers=headers, json=body)
        with httpx.Client(timeout=60) as client:
            return client.post(endpoint, headers=headers, json=body)

    def _launch(self, packet: dict[str, Any]) -> str:
        parameters = packet["parameters"]
        body = {
            "instances": [{"prompt": packet["prompt"]}],
            "parameters": {
                "storageUri": parameters["storage_uri"],
                "sampleCount": parameters["sample_count"],
                "durationSeconds": parameters["duration_seconds"],
                "aspectRatio": parameters["aspect_ratio"],
                "resolution": parameters["resolution"],
                "generateAudio": parameters["generate_audio"],
                "personGeneration": parameters["person_generation"],
                "seed": parameters["seed"],
            },
        }
        response = self._post(f"{self.model_endpoint}:predictLongRunning", body)
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        operation_name = payload.get("name")
        if not isinstance(operation_name, str) or not operation_name:
            raise VeoReplayError("Veo returned no operation name")
        return operation_name

    def _poll(self, operation_name: str) -> dict[str, Any]:
        for poll_index in range(self.max_polls):
            if poll_index:
                self.sleeper(self.poll_interval_seconds)
            response = self._post(
                f"{self.model_endpoint}:fetchPredictOperation",
                {"operationName": operation_name},
            )
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
            if payload.get("done") is True:
                if payload.get("error"):
                    raise VeoReplayError("Veo operation completed with an error")
                return payload
        raise VeoReplayError("Veo operation did not complete before the polling limit")

    def generate(self, snapshot: MissionSnapshot) -> VeoInvocation:
        generation_id = uuid4().hex[:12]
        output_uri = f"{self.output_uri}{snapshot.mission.id}/{generation_id}/"
        packet = replay_packet(snapshot, output_uri)
        operation_name = self._launch(packet)
        operation = self._poll(operation_name)
        response = operation.get("response")
        if not isinstance(response, dict):
            raise VeoReplayError("Veo operation returned no response")
        filtered_count = int(response.get("raiMediaFilteredCount", 0))
        videos = response.get("videos")
        if filtered_count != 0 or not isinstance(videos, list) or len(videos) != 1:
            raise VeoReplayError("Veo replay did not return exactly one safe video")
        video = videos[0]
        if not isinstance(video, dict) or not isinstance(video.get("gcsUri"), str):
            raise VeoReplayError("Veo response returned no GCS media URI")
        asset_uri = video["gcsUri"]
        media = fetch_gcs_media(
            asset_uri,
            self.output_uri,
            client=self.client,
            token_provider=self.token_provider,
        )
        result = {
            "label": VEO_REPLAY_LABEL,
            "prompt_version": VEO_REPLAY_PROMPT_VERSION,
            "asset_uri": asset_uri,
            "asset_sha256": _asset_sha256(media),
            "mime_type": str(video.get("mimeType", "video/mp4")),
            "duration_seconds": 4,
            "resolution": "1280x720",
            "fps": 24,
            "safety_filtered_count": filtered_count,
            "generated_after_release": True,
            "training_only": True,
            "evidence": False,
            "release_authority": False,
            "fallback_used": False,
        }
        return VeoInvocation(
            request_ref=operation_name,
            input_digest=_digest(packet),
            output_digest=_digest(result),
            result=result,
        )


class VeoReplayService:
    def __init__(self, store: MissionStore, port: VeoReplayPort) -> None:
        self.store = store
        self.port = port

    def generate(
        self,
        mission_id: str,
        *,
        actor: str = "operator.demo",
    ) -> MissionSnapshot:
        snapshot = self.store.snapshot(mission_id)
        if not self.port.enabled:
            raise VeoReplayError("Post-release replay is disabled")
        if snapshot.mission.release_state is not ReleaseState.RELEASED:
            raise VeoReplayError("Replay generation requires committed RELEASED state")
        if not any(
            item.kind is ReceiptKind.CARRIER_RELEASE_READBACK and item.verified
            for item in snapshot.receipts
        ):
            raise VeoReplayError("Replay generation requires verified carrier read-back")
        existing = [item for item in snapshot.model_receipts if item.kind == VEO_REPLAY_KIND]
        completed = [item for item in existing if item.status is ModelReceiptStatus.COMPLETED]
        if completed:
            return snapshot

        lease_owner = f"veo-replay-{uuid4().hex[:12]}"
        if not self.store.acquire_lease(mission_id, lease_owner, ttl_seconds=900):
            raise VeoReplayError("Mission has an active operation; retry replay generation")
        try:
            snapshot = self.store.snapshot(mission_id)
            authority_version = snapshot.mission.version
            try:
                invocation = self.port.generate(snapshot)
                result = invocation.result
                status = ModelReceiptStatus.COMPLETED
                request_ref = invocation.request_ref
                source_digest = invocation.input_digest
                output_digest = invocation.output_digest
            except Exception as error:
                status = ModelReceiptStatus.DEGRADED
                request_ref = f"veo-error-{uuid4().hex[:12]}"
                source_digest = _digest(replay_packet(snapshot, "gs://redacted/failure/"))
                result = {
                    "error_type": type(error).__name__,
                    "retryable": True,
                    "release_affected": False,
                    "release_authority": False,
                    "generated_after_release": True,
                    "training_only": True,
                    "prompt_version": VEO_REPLAY_PROMPT_VERSION,
                }
                output_digest = _digest(result)

            snapshot, created = self.store.record_model_receipt(
                mission_id,
                kind=VEO_REPLAY_KIND,
                model_id=self.port.model_id,
                location=self.port.location,
                request_ref=request_ref,
                input_digest=source_digest,
                output_digest=output_digest,
                status=status,
                truth_mode=self.port.truth_mode,
                result=result,
                actor=actor,
            )
            if snapshot.mission.version != authority_version:
                raise VeoReplayError(
                    "Replay receipt unexpectedly changed release authority version"
                )
            if created:
                self.store.record_trace(
                    mission_id,
                    "veo-post-release-replay@1.0.0",
                    "generate_synthetic_training_replay_after_release",
                    self.port.truth_mode,
                    status,
                    {
                        "model_id": self.port.model_id,
                        "location": self.port.location,
                        "request_ref": request_ref,
                        "input_digest": source_digest,
                        "output_digest": output_digest,
                        "generated_after_release": True,
                        "training_only": True,
                        "evidence": False,
                        "release_authority": False,
                        "release_affected": False,
                    },
                )
                snapshot = self.store.snapshot(mission_id)
            return snapshot
        finally:
            self.store.release_lease(mission_id, lease_owner)


def latest_veo_receipt(snapshot: MissionSnapshot) -> ModelReceipt | None:
    return next(
        (item for item in reversed(snapshot.model_receipts) if item.kind == VEO_REPLAY_KIND),
        None,
    )


def build_veo_replay() -> VeoReplayPort:
    if os.getenv("CARGO_RELEASE_VEO_REPLAY_ENABLED") != "1":
        return DisabledVeoReplay()
    if os.getenv("CARGO_RELEASE_VEO_REPLAY_MODE") == "FIXTURE":
        return FixtureVeoReplay()
    project = os.getenv("CARGO_RELEASE_MODEL_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or ""
    return VertexVeoReplay(
        project,
        os.getenv("CARGO_RELEASE_VEO_OUTPUT_URI", ""),
        location=os.getenv("CARGO_RELEASE_VEO_LOCATION", DEFAULT_VEO_LOCATION),
        model_id=os.getenv("CARGO_RELEASE_VEO_MODEL", DEFAULT_VEO_MODEL),
        poll_interval_seconds=float(os.getenv("CARGO_RELEASE_VEO_POLL_SECONDS", "10")),
        max_polls=int(os.getenv("CARGO_RELEASE_VEO_MAX_POLLS", "60")),
    )
