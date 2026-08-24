from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cargo_release import memory
from cargo_release.engine import CargoReleaseEngine
from cargo_release.memory import AgentPlatformMemoryBank
from cargo_release.models import VersionedAction
from cargo_release.runtime import MissionOrchestrator
from cargo_release.store import SQLiteMissionStore


def test_managed_memory_submission_does_not_require_operation_polling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteMissionStore(str(tmp_path / "memory.db"))
    engine = CargoReleaseEngine(store)
    runtime = MissionOrchestrator(engine)
    snapshot = runtime.run(engine.create_demo_mission().mission.id)
    snapshot = engine.approve_owner_bond(
        snapshot.mission.id,
        VersionedAction(
            expected_version=snapshot.mission.version,
            actor="cargo-owner.demo",
        ),
    )
    snapshot = runtime.run(snapshot.mission.id)
    captured: dict[str, object] = {}

    class FakeMemories:
        def generate(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                name="projects/demo/locations/us-central1/reasoningEngines/1/operations/2"
            )

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            self.agent_engines = SimpleNamespace(memories=FakeMemories())

    monkeypatch.setattr(memory.vertexai, "Client", FakeClient)
    managed = AgentPlatformMemoryBank(
        store,
        "demo",
        "us-central1",
        "projects/demo/locations/us-central1/reasoningEngines/1",
    )

    result = managed.remember_release_context(snapshot)

    assert result.endswith("/operations/2")
    assert captured["config"] == {"wait_for_completion": False}
    assert captured["scope"] == {"mission_id": snapshot.mission.id}
    assert store.reviewed_memory(snapshot.mission.id, "verified-release-context-v1")
