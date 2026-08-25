from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import _transformers
from pydantic import ValidationError

from cargo_release import adk_agent


def mission_snapshot(
    release_state: str,
    *,
    approvals: list[dict[str, Any]] | None = None,
    runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "mission": {
            "id": "mission-abe2d197faad",
            "case_ref": "GA-2026-TEST",
            "container_ref": "TCLU-482019-7",
            "release_state": release_state,
            "adjustment_state": "OPEN",
            "version": 7,
            "truth_mode": "NATIVE",
        },
        "evidence": [],
        "approvals": approvals or [],
        "receipts": [],
        "artifacts": [],
        "runs": runs or [],
    }


def test_coordinator_requires_gemini_3_5_or_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARGO_RELEASE_MODEL", "gemini-2.5-flash")
    with pytest.raises(RuntimeError, match=r"requires Gemini 3\.5\+"):
        adk_agent._coordinator_model()


def test_coordinator_routes_compliant_vertex_model_to_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARGO_RELEASE_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("CARGO_RELEASE_MODEL_LOCATION", "global")
    monkeypatch.setenv("CARGO_RELEASE_MODEL_PROJECT", "ata-2026-cargo")

    model = adk_agent._coordinator_model()

    assert isinstance(model, Gemini)
    assert model.model == "gemini-3.5-flash"
    assert model.client_kwargs == {
        "vertexai": True,
        "location": "global",
        "project": "ata-2026-cargo",
    }


def test_local_controller_needs_no_cloud_identity() -> None:
    assert adk_agent._controller_headers("http://127.0.0.1:8095") == {}


def test_cloud_controller_uses_configured_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeImpersonatedCredentials:
        def __init__(self, **kwargs: object) -> None:
            captured["impersonation"] = kwargs
            captured["target_credentials"] = self

    class FakeIDTokenCredentials:
        token = "signed-id-token"

        def __init__(self, **kwargs: object) -> None:
            captured["identity_token"] = kwargs

        def refresh(self, request: object) -> None:
            captured["refresh_request"] = request

    monkeypatch.setenv(
        "CARGO_RELEASE_CONTROLLER_AUDIENCE",
        "https://controller-audience.example/",
    )
    monkeypatch.setenv(
        "CARGO_RELEASE_CALLER_SERVICE_ACCOUNT",
        "cargo-coordinator@example.iam.gserviceaccount.com",
    )
    source_credentials = object()
    monkeypatch.setattr(
        adk_agent.google.auth,
        "default",
        lambda **_kwargs: (source_credentials, "test-project"),
    )
    monkeypatch.setattr(
        adk_agent.impersonated_credentials,
        "Credentials",
        FakeImpersonatedCredentials,
    )
    monkeypatch.setattr(
        adk_agent.impersonated_credentials,
        "IDTokenCredentials",
        FakeIDTokenCredentials,
    )

    assert adk_agent._controller_headers("https://controller-endpoint.example") == {
        "X-Serverless-Authorization": "Bearer signed-id-token"
    }
    assert captured["impersonation"] == {
        "source_credentials": source_credentials,
        "target_principal": "cargo-coordinator@example.iam.gserviceaccount.com",
        "target_scopes": [adk_agent.GOOGLE_CLOUD_PLATFORM_SCOPE],
        "lifetime": 300,
    }
    assert captured["identity_token"] == {
        "target_credentials": captured["target_credentials"],
        "target_audience": "https://controller-audience.example/",
        "include_email": True,
    }


def test_cloud_controller_requires_dedicated_caller_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CARGO_RELEASE_CALLER_SERVICE_ACCOUNT", raising=False)

    with pytest.raises(RuntimeError, match="CARGO_RELEASE_CALLER_SERVICE_ACCOUNT"):
        adk_agent._controller_headers("https://controller-endpoint.example")


def test_coordinator_delegates_to_four_separately_scoped_workers() -> None:
    workers = {worker.name: worker for worker in adk_agent.root_agent.sub_agents}

    assert set(workers) == {
        "manifest_evidence_worker",
        "security_pack_worker",
        "carrier_authority_worker",
        "runtime_recovery_worker",
    }
    expected_tools = {
        "manifest_evidence_worker": "inspect_evidence_scope",
        "security_pack_worker": "inspect_security_scope",
        "carrier_authority_worker": "inspect_authority_scope",
        "runtime_recovery_worker": "assess_runtime_recovery",
    }
    for name, worker in workers.items():
        assert isinstance(worker, Agent)
        assert worker.parent_agent is adk_agent.root_agent
        assert worker.model == ""
        assert worker.mode == "single_turn"
        assert worker.include_contents == "none"
        assert worker.disallow_transfer_to_peers is True
        assert worker.output_schema is adk_agent.ScopedWorkerReport
        assert [tool.__name__ for tool in worker.tools] == [expected_tools[name]]
        assert adk_agent.start_bounded_mission not in worker.tools

    coordinator_callables = [
        tool for tool in adk_agent.root_agent.tools if callable(tool)
    ]
    assert coordinator_callables == [adk_agent.start_bounded_mission]


def test_scoped_worker_schema_is_managed_genai_compatible_and_fail_closed() -> None:
    schema = adk_agent.ScopedWorkerReport.model_json_schema()

    _transformers.process_schema(schema, client=None)

    release_authority = schema["properties"]["release_authority"]
    assert release_authority["type"] == "boolean"
    assert "const" not in release_authority
    with pytest.raises(
        ValidationError,
        match="scoped workers cannot hold release authority",
    ):
        adk_agent.ScopedWorkerReport(
            worker="manifest_evidence_worker",
            mission_id="mission-abe2d197faad",
            status="VERIFIED",
            summary="Managed schema compatibility probe",
            next_action="RETURN_TO_COORDINATOR",
            release_authority=True,
        )


def test_scoped_workers_never_expose_untrusted_text_payloads_or_signatures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = mission_snapshot("RELEASED")
    snapshot.update(
        {
            "evidence": [
                {
                    "id": "evidence-1",
                    "kind": "Broker email",
                    "filename": "broker.eml",
                    "sha256": "abc123",
                    "status": "QUARANTINED",
                    "summary": "MALICIOUS_PROMPT_TEXT",
                    "facts": {"accepted_as_fact": False},
                }
            ],
            "approvals": [
                {
                    "id": "approval-1",
                    "kind": "OWNER_BOND",
                    "actor": "operator@example.test",
                    "artifact_ref": "artifact://bond@abc123",
                    "approved_at": "2026-08-25T00:00:00Z",
                }
            ],
            "artifacts": [
                {
                    "id": "artifact-1",
                    "kind": "OWNER_BOND",
                    "revision": 1,
                    "status": "APPROVED",
                    "digest": "bond-digest",
                    "content": {"secret": "RAW_ARTIFACT_CONTENT"},
                }
            ],
            "receipts": [
                {
                    "id": "receipt-1",
                    "kind": "ADJUSTER_ACCEPTANCE",
                    "issuer": "adjuster",
                    "external_id": "ADJ-1",
                    "subject_ref": "GA-2026-TEST",
                    "status": "ACCEPTED",
                    "verified": True,
                    "digest": "adjuster-digest",
                    "payload": {"secret": "RAW_RECEIPT_PAYLOAD"},
                    "signature": "RAW_RECEIPT_SIGNATURE",
                },
                {
                    "id": "receipt-2",
                    "kind": "CARRIER_RELEASE_ORDER",
                    "issuer": "carrier",
                    "external_id": "CAR-1",
                    "subject_ref": "TCLU-482019-7",
                    "status": "RELEASED",
                    "verified": True,
                    "digest": "order-digest",
                },
                {
                    "id": "receipt-3",
                    "kind": "CARRIER_RELEASE_READBACK",
                    "issuer": "carrier",
                    "external_id": "READBACK-1",
                    "subject_ref": "TCLU-482019-7",
                    "status": "CONFIRMED",
                    "verified": True,
                    "digest": "readback-digest",
                },
            ],
        }
    )
    monkeypatch.setattr(adk_agent, "inspect_mission", lambda _mission_id: snapshot)

    reports = [
        adk_agent.inspect_evidence_scope("mission-abe2d197faad"),
        adk_agent.inspect_security_scope("mission-abe2d197faad"),
        adk_agent.inspect_authority_scope("mission-abe2d197faad"),
    ]
    rendered = json.dumps(reports)

    assert "MALICIOUS_PROMPT_TEXT" not in rendered
    assert "RAW_ARTIFACT_CONTENT" not in rendered
    assert "RAW_RECEIPT_PAYLOAD" not in rendered
    assert "RAW_RECEIPT_SIGNATURE" not in rendered
    assert reports[0]["untrusted_evidence_text_exposed"] is False
    assert reports[1]["receipt_payloads_exposed"] is False
    assert reports[2]["receipt_signatures_exposed"] is False
    assert reports[2]["chain_complete"] is True
    assert all(report["release_authority"] is False for report in reports)


def test_bounded_recovery_stops_at_human_gate_without_posting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adk_agent,
        "inspect_mission",
        lambda _mission_id: mission_snapshot("READY_FOR_SIGNATURE"),
    )
    monkeypatch.setattr(
        adk_agent,
        "_controller_request",
        lambda *_args, **_kwargs: pytest.fail("human gate must not be advanced"),
    )

    result = adk_agent.start_bounded_mission("mission-abe2d197faad")

    assert result["advanced"] is False
    assert result["recovery"]["status"] == "WAITING_HUMAN"
    assert result["recovery"]["next_action"] == "WAIT_FOR_OWNER_BOND"


@pytest.mark.parametrize("last_status", ["FAILED", "RUNNING"])
def test_bounded_recovery_performs_one_controller_lease_probe(
    monkeypatch: pytest.MonkeyPatch,
    last_status: str,
) -> None:
    before = mission_snapshot(
        "SECURITY_SUBMITTED",
        approvals=[{"kind": "OWNER_BOND"}],
        runs=[
            {
                "id": "run-old",
                "status": last_status,
                "reason": "RUNTIME_ERROR",
                "steps": 4,
            }
        ],
    )
    after = mission_snapshot(
        "RELEASED",
        approvals=[{"kind": "OWNER_BOND"}],
        runs=[
            {
                "id": "run-new",
                "status": "COMPLETED",
                "reason": "CARRIER_READBACK_VERIFIED",
                "steps": 3,
            }
        ],
    )
    calls: list[str] = []
    monkeypatch.setattr(adk_agent, "inspect_mission", lambda _mission_id: before)

    def post(path: str, _payload: object = None) -> dict[str, Any]:
        calls.append(path)
        return after

    monkeypatch.setattr(adk_agent, "_controller_request", post)

    result = adk_agent.start_bounded_mission("mission-abe2d197faad")

    assert calls == ["/v1/missions/mission-abe2d197faad:run"]
    assert result["advanced"] is True
    assert result["attempts"] == 1
    assert result["state"]["mission"]["release_state"] == "RELEASED"
    assert result["recovery"]["retry_in_this_turn"] is False


def test_tool_error_recovery_is_bounded_and_non_authoritative() -> None:
    report = adk_agent._recover_tool_error(
        tool=SimpleNamespace(name="start_bounded_mission"),  # type: ignore[arg-type]
        args={"mission_id": "mission-abe2d197faad"},
        tool_context=SimpleNamespace(),  # type: ignore[arg-type]
        error=TimeoutError("upstream timeout with private detail"),
    )

    assert report == {
        "status": "DEGRADED",
        "tool": "start_bounded_mission",
        "mission_id": "mission-abe2d197faad",
        "error_class": "TimeoutError",
        "retry_in_this_turn": False,
        "next_action": "RETURN_TO_COORDINATOR",
        "release_authority": False,
    }
