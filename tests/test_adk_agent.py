from __future__ import annotations

import pytest
from google.adk.models import Gemini

from cargo_release import adk_agent


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
