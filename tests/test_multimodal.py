from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest

from cargo_release.multimodal import (
    AdjusterRejectionExtraction,
    FixtureMultimodalExtractor,
    MultimodalExtractionError,
    VertexMultimodalExtractor,
    validate_extraction,
)


def valid_extraction(**updates: object) -> AdjusterRejectionExtraction:
    extraction = AdjusterRejectionExtraction(
        document_type="ADJUSTER_SECURITY_PACK_REJECTION",
        decision="REJECTED",
        case_reference="GA/NST/0819",
        container_ref="TCLU-482019-7",
        pack_revision=1,
        checked_defect="DECLARATION_REFERENCE_MISSING",
        missing_field="declaration_reference",
        correction_instruction="Add the declaration reference and resubmit revision 2.",
        confidence=0.97,
    )
    return extraction.model_copy(update=updates)


def test_vertex_multimodal_sends_digest_bound_png_and_parses_schema() -> None:
    media = b"synthetic-png-bytes"
    digest = hashlib.sha256(media).hexdigest()
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"x-request-id": "managed-visual-1"},
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps(valid_extraction().model_dump(mode="json"))}
                            ]
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        invocation = VertexMultimodalExtractor(
            "ata-2026-cargo",
            client=client,
            token_provider=lambda: "ephemeral-test-token",
        ).extract(media, digest)

    assert invocation.request_ref == "managed-visual-1"
    assert invocation.input_digest == digest
    assert invocation.extraction.missing_field == "declaration_reference"
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert requests[0].url.path.endswith("gemini-3.5-flash:generateContent")
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    image = body["contents"][0]["parts"][1]["inlineData"]
    assert image["mimeType"] == "image/png"
    assert base64.b64decode(image["data"]) == media


def test_visual_digest_and_deterministic_schema_fail_closed() -> None:
    with pytest.raises(MultimodalExtractionError, match="digest"):
        FixtureMultimodalExtractor().extract(b"altered", "0" * 64)

    accepted, outcome = validate_extraction(
        valid_extraction(missing_field="release_state"),
        expected_case_reference="GA/NST/0819",
        expected_container_ref="TCLU-482019-7",
    )
    assert not accepted
    assert outcome == "UNSUPPORTED_CORRECTION_FIELD"


def test_vertex_failure_codes_expose_no_raw_model_content() -> None:
    media = b"synthetic-png-bytes"
    digest = hashlib.sha256(media).hexdigest()

    def no_candidate(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"promptFeedback": {"blockReason": "IMAGE_SAFETY"}},
        )

    with httpx.Client(transport=httpx.MockTransport(no_candidate)) as client:
        extractor = VertexMultimodalExtractor(
            "ata-2026-cargo",
            client=client,
            token_provider=lambda: "ephemeral-test-token",
        )
        with pytest.raises(MultimodalExtractionError) as captured:
            extractor.extract(media, digest)

    assert captured.value.code == "NO_CANDIDATE_IMAGE_SAFETY"
    assert "synthetic-png-bytes" not in str(captured.value)
