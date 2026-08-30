from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Callable
from typing import Any, Protocol, cast

import google.auth
import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from pydantic import BaseModel, Field

from cargo_release.models import TruthMode

MULTIMODAL_EXTRACTION_KIND = "GEMINI_ADJUSTER_REJECTION_EXTRACTION"
EXTRACTION_SCHEMA_VERSION = "adjuster-rejection-v1"
DEFAULT_MULTIMODAL_MODEL = "gemini-3.5-flash"
MIN_EXTRACTION_CONFIDENCE = 0.85


class MultimodalExtractionError(RuntimeError):
    def __init__(self, message: str, *, code: str = "MULTIMODAL_EXTRACTION_ERROR") -> None:
        super().__init__(message)
        self.code = code


class AdjusterRejectionExtraction(BaseModel):
    document_type: str
    decision: str
    case_reference: str
    container_ref: str
    pack_revision: int
    checked_defect: str
    missing_field: str
    correction_instruction: str
    confidence: float = Field(ge=0, le=1)


class MultimodalInvocation(BaseModel):
    request_ref: str
    input_digest: str
    output_digest: str
    extraction: AdjusterRejectionExtraction


class MultimodalExtractionPort(Protocol):
    model_id: str
    location: str
    truth_mode: TruthMode

    def extract(self, media: bytes, source_digest: str) -> MultimodalInvocation: ...


class FixtureMultimodalExtractor:
    model_id = DEFAULT_MULTIMODAL_MODEL
    location = "fixture"
    truth_mode = TruthMode.FIXTURE

    def extract(self, media: bytes, source_digest: str) -> MultimodalInvocation:
        if hashlib.sha256(media).hexdigest() != source_digest:
            raise MultimodalExtractionError("Prepared scan digest does not match mission intake")
        extraction = AdjusterRejectionExtraction(
            document_type="ADJUSTER_SECURITY_PACK_REJECTION",
            decision="REJECTED",
            case_reference="GA/NST/0819",
            container_ref="TCLU-482019-7",
            pack_revision=1,
            checked_defect="DECLARATION_REFERENCE_MISSING",
            missing_field="declaration_reference",
            correction_instruction=(
                "Add the declaration reference from the casualty notice and resubmit revision 2."
            ),
            confidence=0.99,
        )
        normalized = json.dumps(
            extraction.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return MultimodalInvocation(
            request_ref=f"fixture-multimodal-{source_digest[:16]}",
            input_digest=source_digest,
            output_digest=hashlib.sha256(normalized.encode()).hexdigest(),
            extraction=extraction,
        )


def _access_token() -> str:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(GoogleAuthRequest())  # type: ignore[no-untyped-call]
    token = credentials.token
    if not isinstance(token, str) or not token:
        raise MultimodalExtractionError("Google credentials returned no access token")
    return token


def _json_object(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        raise MultimodalExtractionError(
            "Gemini extraction returned no JSON object",
            code="NO_JSON_OBJECT",
        )
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError as error:
        raise MultimodalExtractionError(
            "Gemini extraction returned invalid JSON",
            code="INVALID_JSON_OBJECT",
        ) from error
    if not isinstance(parsed, dict):
        raise MultimodalExtractionError(
            "Gemini extraction result must be a JSON object",
            code="NON_OBJECT_RESULT",
        )
    return cast(dict[str, Any], parsed)


def _structured_json_part(parts: list[object]) -> dict[str, Any]:
    """Select the final non-thought JSON part without retaining reasoning text."""

    saw_non_thought_text = False
    for part in reversed(parts):
        if not isinstance(part, dict) or part.get("thought") is True:
            continue
        text = part.get("text")
        if not isinstance(text, str):
            continue
        saw_non_thought_text = True
        try:
            return _json_object(text)
        except MultimodalExtractionError as error:
            if error.code != "NO_JSON_OBJECT":
                raise
    raise MultimodalExtractionError(
        "Gemini extraction returned no structured non-thought result",
        code="NO_JSON_OBJECT" if saw_non_thought_text else "NO_NON_THOUGHT_TEXT_RESULT",
    )


class VertexMultimodalExtractor:
    truth_mode = TruthMode.NATIVE

    def __init__(
        self,
        project: str,
        *,
        location: str = "global",
        model_id: str = DEFAULT_MULTIMODAL_MODEL,
        client: httpx.Client | None = None,
        token_provider: Callable[[], str] = _access_token,
    ) -> None:
        if not project:
            raise MultimodalExtractionError("CARGO_RELEASE_MODEL_PROJECT is required")
        self.project = project
        self.location = location
        self.model_id = model_id
        self.client = client
        self.token_provider = token_provider

    def _request(self, body: dict[str, Any]) -> httpx.Response:
        endpoint = (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{self.project}/locations/{self.location}/publishers/google/models/"
            f"{self.model_id}:generateContent"
        )
        headers = {"authorization": f"Bearer {self.token_provider()}"}
        if self.client is not None:
            return self.client.post(endpoint, headers=headers, json=body)
        with httpx.Client(timeout=60) as client:
            return client.post(endpoint, headers=headers, json=body)

    def extract(self, media: bytes, source_digest: str) -> MultimodalInvocation:
        if hashlib.sha256(media).hexdigest() != source_digest:
            raise MultimodalExtractionError("Prepared scan digest does not match mission intake")
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Extract only visibly supported fields from this fictional "
                                "adjuster "
                                "security-pack rejection. Return JSON matching this exact shape: "
                                "{document_type, decision, case_reference, container_ref, "
                                "pack_revision, checked_defect, missing_field, "
                                "correction_instruction, confidence}. Do not infer authority, "
                                "legal "
                                "sufficiency, or release status. confidence must be 0..1."
                            )
                        },
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(media).decode(),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 500,
                "responseMimeType": "application/json",
            },
        }
        response = self._request(body)
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            prompt_feedback = payload.get("promptFeedback")
            block_reason = (
                prompt_feedback.get("blockReason")
                if isinstance(prompt_feedback, dict)
                else None
            )
            suffix = str(block_reason or "UNKNOWN").upper().replace("-", "_")
            raise MultimodalExtractionError(
                "Gemini extraction returned no candidate",
                code=f"NO_CANDIDATE_{suffix}",
            )
        content = candidates[0].get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list) or not parts:
            finish_reason = candidates[0].get("finishReason", "UNKNOWN")
            suffix = str(finish_reason).upper().replace("-", "_")
            raise MultimodalExtractionError(
                "Gemini extraction returned no text result",
                code=f"NO_TEXT_RESULT_{suffix}",
            )
        extraction = AdjusterRejectionExtraction.model_validate(
            _structured_json_part(cast(list[object], parts))
        )
        normalized = json.dumps(
            extraction.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        request_ref = response.headers.get("x-request-id") or payload.get("responseId")
        if not isinstance(request_ref, str) or not request_ref:
            request_ref = f"vertex-multimodal-{source_digest[:16]}"
        return MultimodalInvocation(
            request_ref=request_ref,
            input_digest=source_digest,
            output_digest=hashlib.sha256(normalized.encode()).hexdigest(),
            extraction=extraction,
        )


def validate_extraction(
    extraction: AdjusterRejectionExtraction,
    *,
    expected_case_reference: str,
    expected_container_ref: str,
) -> tuple[bool, str]:
    checks = {
        "LOW_CONFIDENCE": extraction.confidence >= MIN_EXTRACTION_CONFIDENCE,
        "UNSUPPORTED_DOCUMENT_TYPE": (
            extraction.document_type == "ADJUSTER_SECURITY_PACK_REJECTION"
        ),
        "UNSUPPORTED_DECISION": extraction.decision == "REJECTED",
        "CASE_REFERENCE_MISMATCH": extraction.case_reference == expected_case_reference,
        "CONTAINER_REFERENCE_MISMATCH": extraction.container_ref == expected_container_ref,
        "PACK_REVISION_MISMATCH": extraction.pack_revision == 1,
        "UNSUPPORTED_DEFECT": (
            extraction.checked_defect == "DECLARATION_REFERENCE_MISSING"
        ),
        "UNSUPPORTED_CORRECTION_FIELD": extraction.missing_field == "declaration_reference",
    }
    failed = [code for code, passed in checks.items() if not passed]
    return (not failed, "ACCEPTED" if not failed else failed[0])


def build_multimodal_extractor() -> MultimodalExtractionPort:
    mode = os.getenv("CARGO_RELEASE_MULTIMODAL_MODE", "FIXTURE").upper()
    if mode == "FIXTURE":
        return FixtureMultimodalExtractor()
    if mode != "VERTEX":
        raise MultimodalExtractionError(
            "CARGO_RELEASE_MULTIMODAL_MODE must be FIXTURE or VERTEX"
        )
    project = os.getenv("CARGO_RELEASE_MODEL_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or ""
    return VertexMultimodalExtractor(
        project,
        location=os.getenv("CARGO_RELEASE_MULTIMODAL_LOCATION", "global"),
        model_id=os.getenv("CARGO_RELEASE_MULTIMODAL_MODEL", DEFAULT_MULTIMODAL_MODEL),
    )
