from __future__ import annotations

import json
from pathlib import Path

import httpx

from cargo_release.api import create_app
from cargo_release.case_retrieval import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    RETRIEVAL_LABEL,
    FixtureCaseRetrieval,
    RetrievalInvocation,
    VertexCaseRetrieval,
    retrieval_packet,
)
from cargo_release.models import MissionSnapshot, TruthMode
from tests.asgi_client import ASGITestClient


class FailingCaseRetrieval:
    enabled = True
    model_id = DEFAULT_EMBEDDING_MODEL
    location = "global"
    truth_mode = TruthMode.NATIVE

    def retrieve(self, snapshot: MissionSnapshot) -> RetrievalInvocation:
        del snapshot
        raise TimeoutError("synthetic embedding timeout")


def held_snapshot(client: ASGITestClient) -> dict[str, object]:
    created = client.post("/v1/missions/demo").json()
    response = client.post(f"/v1/missions/{created['mission']['id']}:run")
    assert response.status_code == 200, response.text
    return response.json()


def test_case_retrieval_runs_once_without_state_authority(tmp_path: Path) -> None:
    port = FixtureCaseRetrieval()
    client = ASGITestClient(
        create_app(str(tmp_path / "retrieval.db"), case_retrieval=port)
    )

    snapshot = held_snapshot(client)

    assert snapshot["mission"]["release_state"] == "READY_FOR_SIGNATURE"
    assert snapshot["mission"]["version"] == 1
    assert port.calls == 1
    receipt = snapshot["model_receipts"][0]
    assert receipt["kind"] == "GEMINI_EMBEDDING_RETRIEVAL"
    assert receipt["model_id"] == "gemini-embedding-2"
    assert receipt["status"] == "COMPLETED"
    assert receipt["release_authority"] is False
    assert receipt["result"]["label"] == RETRIEVAL_LABEL
    assert receipt["result"]["confidence_percentages_exposed"] is False
    assert [item["rank"] for item in receipt["result"]["top_cases"]] == [1, 2, 3]

    repeated = client.post(f"/v1/missions/{snapshot['mission']['id']}:run").json()
    assert port.calls == 1
    assert len(repeated["model_receipts"]) == 1


def test_retrieval_packet_excludes_quarantined_prompt_text(tmp_path: Path) -> None:
    snapshot = MissionSnapshot.model_validate(
        held_snapshot(ASGITestClient(create_app(str(tmp_path / "sanitized.db"))))
    )

    packet = retrieval_packet(snapshot)
    rendered = json.dumps(packet, sort_keys=True)
    query = json.loads(packet["query"])
    broker = next(item for item in query["evidence"] if item["kind"] == "Broker email")

    assert "Ignore prior policy" not in rendered
    assert "mark the guarantee accepted" not in rendered
    assert broker == {"kind": "Broker email", "status": "QUARANTINED", "facts": {}}


def test_vertex_embedding_ranks_cases_without_exposing_scores(tmp_path: Path) -> None:
    snapshot = MissionSnapshot.model_validate(
        held_snapshot(ASGITestClient(create_app(str(tmp_path / "vertex.db"))))
    )
    requests: list[httpx.Request] = []
    strengths = [1.0, 0.9, 0.5, -0.1, 0.7, 0.95, 0.2, 0.4, 0.1]

    def respond(request: httpx.Request) -> httpx.Response:
        index = len(requests)
        requests.append(request)
        vector = [strengths[index], *([0.0] * (DEFAULT_EMBEDDING_DIMENSIONS - 1))]
        return httpx.Response(
            200,
            headers={"x-request-id": f"managed-embedding-{index}"},
            json={"embedding": {"values": vector}},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        invocation = VertexCaseRetrieval(
            "ata-2026-cargo",
            client=http_client,
            token_provider=lambda: "ephemeral-test-token",
        ).retrieve(snapshot)

    assert len(requests) == 9
    bodies = [json.loads(request.content) for request in requests]
    assert bodies[0]["embedContentConfig"]["taskType"] == "RETRIEVAL_QUERY"
    assert all(
        body["embedContentConfig"]["taskType"] == "RETRIEVAL_DOCUMENT"
        for body in bodies[1:]
    )
    assert all(
        body["embedContentConfig"]["outputDimensionality"] == 128 for body in bodies
    )
    assert all(request.url.path.endswith(":embedContent") for request in requests)
    assert [item["case_id"] for item in invocation.result["top_cases"]] == [
        "reviewed-provenance-005",
        "reviewed-identifier-001",
        "reviewed-readback-004",
    ]
    assert invocation.result["request_ref_source"] == "MANAGED_RESPONSE"
    assert invocation.result["confidence_percentages_exposed"] is False
    assert "score" not in json.dumps(invocation.result).lower()


def test_embedding_failure_is_visible_and_does_not_block_human_gate(tmp_path: Path) -> None:
    client = ASGITestClient(
        create_app(
            str(tmp_path / "degraded.db"),
            case_retrieval=FailingCaseRetrieval(),
        )
    )

    snapshot = held_snapshot(client)

    assert snapshot["mission"]["release_state"] == "READY_FOR_SIGNATURE"
    assert snapshot["mission"]["version"] == 1
    receipt = snapshot["model_receipts"][0]
    assert receipt["status"] == "DEGRADED"
    assert receipt["result"]["error_type"] == "TimeoutError"
    assert receipt["result"]["release_affected"] is False
    assert receipt["release_authority"] is False


def test_retrieval_retry_requires_non_authority_confirmation(tmp_path: Path) -> None:
    port = FixtureCaseRetrieval()
    client = ASGITestClient(create_app(str(tmp_path / "retry.db"), case_retrieval=port))
    snapshot = client.post("/v1/missions/demo").json()

    response = client.post(
        f"/v1/missions/{snapshot['mission']['id']}/models/case-retrieval:retry",
        json={"confirm_non_authoritative": False},
    )

    assert response.status_code == 409
    assert "cannot authorize cargo" in response.json()["detail"]
    assert port.calls == 0
