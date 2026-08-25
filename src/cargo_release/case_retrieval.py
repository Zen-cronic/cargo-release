from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable
from typing import Any, Protocol, cast
from uuid import uuid4

import httpx

from cargo_release.engine import DomainError
from cargo_release.gemma_critic import _access_token
from cargo_release.models import (
    EvidenceStatus,
    MissionSnapshot,
    ModelReceiptStatus,
    ReleaseState,
    TruthMode,
)
from cargo_release.store import MissionStore

EMBEDDING_RETRIEVAL_KIND = "GEMINI_EMBEDDING_RETRIEVAL"
EMBEDDING_RETRIEVAL_VERSION = "cargo-reviewed-cases-v1"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_EMBEDDING_DIMENSIONS = 128
RETRIEVAL_LABEL = "Nearest reviewed synthetic examples—not precedent or recommendation"

REVIEWED_CASES: tuple[dict[str, str], ...] = (
    {
        "case_id": "reviewed-identifier-001",
        "title": "Manifest resolves a container check-digit conflict",
        "pattern": (
            "General Average cargo file with a bill-of-lading container mismatch. "
            "A verified carrier manifest resolves the check digit before an owner bond is drafted."
        ),
        "reviewed_outcome": (
            "Quarantine the conflicting identifier, retain the manifest source, and stop at human "
            "owner attestation."
        ),
        "key_difference": (
            "This example contains identifier reconciliation, not proof of the security amount."
        ),
    },
    {
        "case_id": "reviewed-injection-002",
        "title": "Broker instruction remains quarantined",
        "pattern": (
            "General Average evidence bundle includes an email addressed to a model that asks it "
            "to accept a guarantee or override policy."
        ),
        "reviewed_outcome": (
            "Keep the email visible but excluded from mission facts and every downstream model "
            "packet."
        ),
        "key_difference": (
            "Quarantine is a security control; this example makes no coverage or release decision."
        ),
    },
    {
        "case_id": "reviewed-security-003",
        "title": "Adjuster rejection produces a corrected security pack",
        "pattern": (
            "An owner-attested bond and insurer guarantee reach the adjuster, who rejects a "
            "missing declaration reference before later acceptance."
        ),
        "reviewed_outcome": (
            "Create a content-addressed correction and wait for a separately signed adjuster "
            "acceptance receipt."
        ),
        "key_difference": (
            "This example begins after human attestation and cannot justify the current owner bond."
        ),
    },
    {
        "case_id": "reviewed-readback-004",
        "title": "Carrier order requires independent read-back",
        "pattern": (
            "Full security has adjuster acceptance and a carrier release order exists, "
            "but physical cargo remains held until the carrier returns a signed read-back."
        ),
        "reviewed_outcome": (
            "Require both carrier order and read-back receipts before the deterministic RELEASED "
            "transition."
        ),
        "key_difference": (
            "This is a terminal release control, not a recommendation for an earlier mission state."
        ),
    },
    {
        "case_id": "reviewed-provenance-005",
        "title": "Security amount retains its reviewed source",
        "pattern": (
            "A draft General Average owner bond states a security amount and links that value to a "
            "reviewed valuation or commercial evidence reference."
        ),
        "reviewed_outcome": (
            "Keep the bond in draft until a human verifies both the amount and its "
            "source reference."
        ),
        "key_difference": (
            "The current bond states an amount without the reviewed source link present here."
        ),
    },
    {
        "case_id": "reviewed-guarantee-006",
        "title": "Insurer guarantee remains independent authority",
        "pattern": (
            "After owner attestation, an insurer issues a separately signed guarantee tied to the "
            "mission and owner-bond artifact."
        ),
        "reviewed_outcome": (
            "Verify issuer identity and signature before submitting the security pack "
            "to the adjuster."
        ),
        "key_difference": (
            "No insurer guarantee is expected before the current human-attestation gate."
        ),
    },
    {
        "case_id": "reviewed-idempotency-007",
        "title": "Duplicate casualty delivery converges on one mission",
        "pattern": (
            "Multiple deliveries of one marked synthetic Eventarc casualty event reach concurrent "
            "controller instances."
        ),
        "reviewed_outcome": (
            "Converge on one mission declaration, one bounded run, and one hash-linked transition."
        ),
        "key_difference": (
            "This operational durability example does not resolve any release-packet fact."
        ),
    },
    {
        "case_id": "reviewed-coverage-008",
        "title": "Coverage remains an external decision",
        "pattern": (
            "A cargo release packet contains policy-adjacent evidence while the application "
            "records coverage_decision as NOT_MADE."
        ),
        "reviewed_outcome": (
            "Keep policy facts inspectable without asking any model or agent to decide coverage."
        ),
        "key_difference": (
            "This control confirms non-authority; it does not imply that cargo may be released."
        ),
    },
)


class CaseRetrievalError(DomainError):
    pass


class RetrievalInvocation:
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


class CaseRetrievalPort(Protocol):
    enabled: bool
    model_id: str
    location: str
    truth_mode: TruthMode

    def retrieve(self, snapshot: MissionSnapshot) -> RetrievalInvocation: ...


def sanitized_query(snapshot: MissionSnapshot) -> str:
    evidence = []
    for item in snapshot.evidence:
        facts = item.facts if item.status is not EvidenceStatus.QUARANTINED else {}
        evidence.append(
            {
                "kind": item.kind,
                "status": item.status,
                "facts": facts,
            }
        )
    packet = {
        "domain": "General Average cargo release",
        "release_state": snapshot.mission.release_state,
        "vessel": snapshot.mission.vessel,
        "container_ref": snapshot.mission.container_ref,
        "evidence": evidence,
        "artifacts": [
            {
                "kind": item.kind,
                "status": item.status,
                "content": item.content,
            }
            for item in snapshot.artifacts
        ],
        "authority_boundary": (
            "Examples are rank-only context. Human attestation and verified receipts remain "
            "required."
        ),
    }
    return json.dumps(packet, sort_keys=True, separators=(",", ":"))


def retrieval_packet(snapshot: MissionSnapshot) -> dict[str, Any]:
    return {
        "version": EMBEDDING_RETRIEVAL_VERSION,
        "query": sanitized_query(snapshot),
        "corpus": list(REVIEWED_CASES),
        "top_k": 3,
        "dimensions": DEFAULT_EMBEDDING_DIMENSIONS,
        "label": RETRIEVAL_LABEL,
    }


def _digest(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode()).hexdigest()


def _dot(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise CaseRetrievalError("Embedding vectors must have one matching non-zero dimension")
    if not all(math.isfinite(value) for value in [*left, *right]):
        raise CaseRetrievalError("Embedding vectors must contain only finite values")
    return sum(a * b for a, b in zip(left, right, strict=True))


def rank_cases(
    query_vector: list[float], case_vectors: list[list[float]], *, top_k: int = 3
) -> list[dict[str, Any]]:
    if len(case_vectors) != len(REVIEWED_CASES):
        raise CaseRetrievalError("Embedding response did not cover the reviewed corpus")
    scored = [
        (_dot(query_vector, vector), reviewed_case)
        for reviewed_case, vector in zip(REVIEWED_CASES, case_vectors, strict=True)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]["case_id"]))
    return [
        {
            "rank": index,
            "case_id": reviewed_case["case_id"],
            "title": reviewed_case["title"],
            "reviewed_outcome": reviewed_case["reviewed_outcome"],
            "key_difference": reviewed_case["key_difference"],
        }
        for index, (_score, reviewed_case) in enumerate(scored[:top_k], start=1)
    ]


def _result(
    top_cases: list[dict[str, Any]],
    *,
    dimensions: int,
    embedding_set_digest: str,
    request_ref_source: str,
) -> dict[str, Any]:
    return {
        "label": RETRIEVAL_LABEL,
        "corpus_version": EMBEDDING_RETRIEVAL_VERSION,
        "corpus_size": len(REVIEWED_CASES),
        "dimensions": dimensions,
        "rank_method": "DOT_PRODUCT_TOP_K_RANK_ONLY",
        "top_cases": top_cases,
        "embedding_set_sha256": embedding_set_digest,
        "request_ref_source": request_ref_source,
        "release_authority": False,
        "release_affected": False,
        "confidence_percentages_exposed": False,
    }


class DisabledCaseRetrieval:
    enabled = False
    model_id = DEFAULT_EMBEDDING_MODEL
    location = "global"
    truth_mode = TruthMode.ADAPTER

    def retrieve(self, snapshot: MissionSnapshot) -> RetrievalInvocation:
        del snapshot
        raise CaseRetrievalError("Reviewed-case retrieval is disabled")


class FixtureCaseRetrieval:
    enabled = True
    model_id = DEFAULT_EMBEDDING_MODEL
    location = "fixture"
    truth_mode = TruthMode.FIXTURE

    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, snapshot: MissionSnapshot) -> RetrievalInvocation:
        self.calls += 1
        packet = retrieval_packet(snapshot)
        fixture_ids = (
            "reviewed-provenance-005",
            "reviewed-coverage-008",
            "reviewed-identifier-001",
        )
        fixture_cases = [
            next(item for item in REVIEWED_CASES if item["case_id"] == case_id)
            for case_id in fixture_ids
        ]
        top_cases = [
            {
                "rank": index,
                "case_id": reviewed_case["case_id"],
                "title": reviewed_case["title"],
                "reviewed_outcome": reviewed_case["reviewed_outcome"],
                "key_difference": reviewed_case["key_difference"],
            }
            for index, reviewed_case in enumerate(fixture_cases, start=1)
        ]
        result = _result(
            top_cases,
            dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            embedding_set_digest=_digest({"fixture": packet}),
            request_ref_source="FIXTURE",
        )
        return RetrievalInvocation(
            request_ref=f"fixture-embedding-{self.calls}",
            input_digest=_digest(packet),
            output_digest=_digest(result),
            result=result,
        )


class VertexCaseRetrieval:
    enabled = True
    truth_mode = TruthMode.NATIVE

    def __init__(
        self,
        project: str,
        *,
        location: str = "global",
        model_id: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
        client: httpx.Client | None = None,
        token_provider: Callable[[], str] = _access_token,
    ) -> None:
        if not project:
            raise CaseRetrievalError("CARGO_RELEASE_MODEL_PROJECT is required")
        if location not in {"global", "us", "eu"}:
            raise CaseRetrievalError("Gemini Embedding 2 requires global, us, or eu")
        if not 128 <= dimensions <= 3072:
            raise CaseRetrievalError("Embedding dimensions must be between 128 and 3072")
        self.project = project
        self.location = location
        self.model_id = model_id
        self.dimensions = dimensions
        self.client = client
        self.token_provider = token_provider

    def _request(self, text: str, task_type: str, correlation: str) -> httpx.Response:
        endpoint = (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{self.project}/locations/{self.location}/publishers/google/models/"
            f"{self.model_id}:embedContent"
        )
        headers = {
            "authorization": f"Bearer {self.token_provider()}",
            "x-goog-request-reason": f"cargo-release-{correlation}",
        }
        body = {
            "content": {"role": "user", "parts": [{"text": text}]},
            "embedContentConfig": {
                "taskType": task_type,
                "outputDimensionality": self.dimensions,
                "autoTruncate": False,
            },
        }
        if self.client is not None:
            return self.client.post(endpoint, headers=headers, json=body)
        with httpx.Client(timeout=45) as client:
            return client.post(endpoint, headers=headers, json=body)

    def _embed(self, text: str, task_type: str, correlation: str) -> tuple[list[float], str | None]:
        response = self._request(text, task_type, correlation)
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        embedding = payload.get("embedding")
        if not isinstance(embedding, dict) or not isinstance(embedding.get("values"), list):
            raise CaseRetrievalError("Embedding 2 returned no vector")
        vector = [float(value) for value in embedding["values"]]
        if len(vector) != self.dimensions:
            raise CaseRetrievalError("Embedding 2 returned an unexpected dimension")
        managed_ref = next(
            (
                response.headers.get(name)
                for name in ("x-request-id", "x-goog-request-id", "x-guploader-uploadid")
                if response.headers.get(name)
            ),
            None,
        )
        return vector, managed_ref

    def retrieve(self, snapshot: MissionSnapshot) -> RetrievalInvocation:
        packet = retrieval_packet(snapshot)
        correlation = uuid4().hex
        query_vector, query_ref = self._embed(
            packet["query"], "RETRIEVAL_QUERY", correlation
        )
        case_vectors: list[list[float]] = []
        managed_refs = [query_ref] if query_ref else []
        for reviewed_case in REVIEWED_CASES:
            text = " | ".join(
                [
                    reviewed_case["title"],
                    reviewed_case["pattern"],
                    reviewed_case["reviewed_outcome"],
                    reviewed_case["key_difference"],
                ]
            )
            vector, managed_ref = self._embed(text, "RETRIEVAL_DOCUMENT", correlation)
            case_vectors.append(vector)
            if managed_ref:
                managed_refs.append(managed_ref)
        top_cases = rank_cases(query_vector, case_vectors, top_k=packet["top_k"])
        result = _result(
            top_cases,
            dimensions=self.dimensions,
            embedding_set_digest=_digest([query_vector, *case_vectors]),
            request_ref_source=("MANAGED_RESPONSE" if managed_refs else "CLIENT_CORRELATION"),
        )
        request_ref = _digest(managed_refs)[:24] if managed_refs else f"client-{correlation}"
        return RetrievalInvocation(
            request_ref=request_ref,
            input_digest=_digest(packet),
            output_digest=_digest(result),
            result=result,
        )


class CaseRetrievalService:
    def __init__(self, store: MissionStore, port: CaseRetrievalPort) -> None:
        self.store = store
        self.port = port

    def maybe_retrieve(
        self,
        mission_id: str,
        *,
        retry: bool = False,
        actor: str = "system:reviewed-case-retrieval@1.0.0",
    ) -> MissionSnapshot:
        snapshot = self.store.snapshot(mission_id)
        if not self.port.enabled:
            return snapshot
        if (
            snapshot.mission.release_state is not ReleaseState.READY_FOR_SIGNATURE
            or snapshot.approvals
        ):
            return snapshot
        existing = [
            item for item in snapshot.model_receipts if item.kind == EMBEDDING_RETRIEVAL_KIND
        ]
        if existing and not retry:
            return snapshot

        lease_owner = f"case-retrieval-{uuid4().hex[:12]}"
        if not self.store.acquire_lease(mission_id, lease_owner, ttl_seconds=60):
            raise CaseRetrievalError("Mission has an active operation; retry advisory retrieval")
        try:
            snapshot = self.store.snapshot(mission_id)
            if (
                snapshot.mission.release_state is not ReleaseState.READY_FOR_SIGNATURE
                or snapshot.approvals
            ):
                return snapshot
            try:
                invocation = self.port.retrieve(snapshot)
                result = invocation.result
                status = ModelReceiptStatus.COMPLETED
                request_ref = invocation.request_ref
                source_digest = invocation.input_digest
                output_digest = invocation.output_digest
            except Exception as error:
                status = ModelReceiptStatus.DEGRADED
                request_ref = f"embedding-error-{uuid4().hex[:12]}"
                source_digest = _digest(retrieval_packet(snapshot))
                result = {
                    "error_type": type(error).__name__,
                    "retryable": True,
                    "release_affected": False,
                    "release_authority": False,
                    "corpus_version": EMBEDDING_RETRIEVAL_VERSION,
                }
                output_digest = _digest(result)

            snapshot, created = self.store.record_model_receipt(
                mission_id,
                kind=EMBEDDING_RETRIEVAL_KIND,
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
            if created:
                self.store.record_trace(
                    mission_id,
                    "reviewed-case-retrieval@1.0.0",
                    "rank_reviewed_synthetic_cases_non_authoritative",
                    self.port.truth_mode,
                    status,
                    {
                        "model_id": self.port.model_id,
                        "location": self.port.location,
                        "request_ref": request_ref,
                        "input_digest": source_digest,
                        "output_digest": output_digest,
                        "release_authority": False,
                        "release_affected": False,
                        "rank_only": True,
                    },
                )
                snapshot = self.store.snapshot(mission_id)
            return snapshot
        finally:
            self.store.release_lease(mission_id, lease_owner)


def build_case_retrieval() -> CaseRetrievalPort:
    if os.getenv("CARGO_RELEASE_EMBEDDING_RETRIEVAL_ENABLED") != "1":
        return DisabledCaseRetrieval()
    if os.getenv("CARGO_RELEASE_EMBEDDING_RETRIEVAL_MODE") == "FIXTURE":
        return FixtureCaseRetrieval()
    project = os.getenv("CARGO_RELEASE_MODEL_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or ""
    return VertexCaseRetrieval(
        project,
        location=os.getenv("CARGO_RELEASE_EMBEDDING_LOCATION", "global"),
        model_id=os.getenv("CARGO_RELEASE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        dimensions=int(
            os.getenv(
                "CARGO_RELEASE_EMBEDDING_DIMENSIONS",
                str(DEFAULT_EMBEDDING_DIMENSIONS),
            )
        ),
    )
