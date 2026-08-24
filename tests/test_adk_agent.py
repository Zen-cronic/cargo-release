from __future__ import annotations

import pytest

from cargo_release import adk_agent


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
