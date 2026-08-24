from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from cargo_release.api import create_app


def test_demo_route_walk_releases_cargo_but_not_adjustment(tmp_path: Path) -> None:
    client = TestClient(create_app(str(tmp_path / "api.db")))
    response = client.post("/v1/missions/demo")
    assert response.status_code == 200
    snapshot = response.json()
    mission_id = snapshot["mission"]["id"]

    def post(path: str, body: dict[str, object] | None = None) -> dict[str, Any]:
        result = client.post(path, json=body)
        assert result.status_code == 200, result.text
        return cast(dict[str, Any], result.json())

    snapshot = post(
        f"/v1/missions/{mission_id}:analyze",
        {"expected_version": snapshot["mission"]["version"], "actor": "operator.demo"},
    )
    snapshot = post(
        f"/v1/missions/{mission_id}/approvals/owner-bond",
        {"expected_version": snapshot["mission"]["version"], "actor": "cargo-owner.demo"},
    )
    snapshot = post(f"/v1/missions/{mission_id}/demo/insurer")
    snapshot = post(
        f"/v1/missions/{mission_id}:submit-security",
        {"expected_version": snapshot["mission"]["version"], "actor": "operator.demo"},
    )
    snapshot = post(f"/v1/missions/{mission_id}/demo/adjuster")
    assert snapshot["mission"]["release_state"] == "SECURITY_SUBMITTED"
    snapshot = post(
        f"/v1/missions/{mission_id}:correct-security",
        {"expected_version": snapshot["mission"]["version"], "actor": "operator.demo"},
    )
    snapshot = post(f"/v1/missions/{mission_id}/demo/adjuster")
    snapshot = post(f"/v1/missions/{mission_id}/demo/carrier-release")
    assert snapshot["mission"]["release_state"] == "SECURITY_ACCEPTED"
    snapshot = post(f"/v1/missions/{mission_id}/demo/carrier-readback")

    assert snapshot["mission"]["release_state"] == "RELEASED"
    assert snapshot["mission"]["adjustment_state"] == "OPEN"
    assert len(snapshot["receipts"]) == 5


def test_api_requires_current_version(tmp_path: Path) -> None:
    client = TestClient(create_app(str(tmp_path / "conflict.db")))
    snapshot = client.post("/v1/missions/demo").json()
    mission_id = snapshot["mission"]["id"]
    response = client.post(
        f"/v1/missions/{mission_id}:analyze",
        json={"expected_version": 42, "actor": "stale"},
    )
    assert response.status_code == 409
