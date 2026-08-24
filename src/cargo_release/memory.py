from __future__ import annotations

import os
from typing import Protocol

import vertexai

from cargo_release.models import MissionSnapshot
from cargo_release.store import SQLiteMissionStore


class ReviewedMemoryPort(Protocol):
    def remember_release_context(self, snapshot: MissionSnapshot) -> str: ...


def _verified_release_fact(snapshot: MissionSnapshot) -> dict[str, object]:
    return {
        "case_ref": snapshot.mission.case_ref,
        "container_ref": snapshot.mission.container_ref,
        "release_state": snapshot.mission.release_state,
        "adjustment_state": snapshot.mission.adjustment_state,
        "verified_receipts": [
            {"kind": item.kind, "external_id": item.external_id, "digest": item.digest}
            for item in snapshot.receipts
            if item.verified
        ],
        "authority": "deterministic-controller",
    }


class LocalReviewedMemory:
    def __init__(self, store: SQLiteMissionStore) -> None:
        self.store = store

    def remember_release_context(self, snapshot: MissionSnapshot) -> str:
        key = "verified-release-context-v1"
        self.store.write_reviewed_memory(
            snapshot.mission.id,
            key,
            _verified_release_fact(snapshot),
            "policy:release-readback-v1",
        )
        return f"sqlite-memory://{snapshot.mission.id}/{key}"


class AgentPlatformMemoryBank(LocalReviewedMemory):
    def __init__(self, store: SQLiteMissionStore, project: str, location: str, name: str) -> None:
        super().__init__(store)
        self.client = vertexai.Client(project=project, location=location)
        self.name = name

    def remember_release_context(self, snapshot: MissionSnapshot) -> str:
        super().remember_release_context(snapshot)
        fact = _verified_release_fact(snapshot)
        operation = self.client.agent_engines.memories.generate(
            name=self.name,
            direct_memories_source={
                "direct_memories": [
                    {
                        "fact": (
                            f"Case {fact['case_ref']} released container "
                            f"{fact['container_ref']} after verified carrier read-back; "
                            f"General Average adjustment remains {fact['adjustment_state']}."
                        )
                    }
                ]
            },
            scope={"mission_id": snapshot.mission.id},
            config={"wait_for_completion": False},
        )
        return str(operation.name)


def build_memory_port(store: SQLiteMissionStore) -> ReviewedMemoryPort:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    name = os.getenv("CARGO_RELEASE_MEMORY_BANK")
    if project and name:
        return AgentPlatformMemoryBank(
            store,
            project,
            os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            name,
        )
    return LocalReviewedMemory(store)
