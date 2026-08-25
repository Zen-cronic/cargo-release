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
    captured: dict[str, str] = {}

    def fake_fetch_id_token(_request: object, audience: str) -> str:
        captured["audience"] = audience
        return "signed-id-token"

    monkeypatch.setenv(
        "CARGO_RELEASE_CONTROLLER_AUDIENCE",
        "https://controller-audience.example/",
    )
    monkeypatch.setattr(adk_agent.id_token, "fetch_id_token", fake_fetch_id_token)

    assert adk_agent._controller_headers("https://controller-endpoint.example") == {
        "X-Serverless-Authorization": "Bearer signed-id-token"
    }
    assert captured["audience"] == "https://controller-audience.example/"
