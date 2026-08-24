from __future__ import annotations

from fastapi.testclient import TestClient

from cargo_release.models import PartnerReceipt, ReceiptKind
from cargo_release.partners import (
    PARTNER_SECRETS,
    create_adjuster_app,
    create_carrier_app,
    create_insurer_app,
)
from cargo_release.security import verify_receipt


def test_insurer_sandbox_enforces_owner_approval_and_signs_receipt() -> None:
    client = TestClient(create_insurer_app())
    body = {"mission_id": "mission-demo", "case_ref": "GA-DEMO", "owner_bond_approved": False}
    assert client.post("/v1/guarantees:issue", json=body).status_code == 409
    body["owner_bond_approved"] = True
    response = client.post("/v1/guarantees:issue", json=body)
    assert response.status_code == 200
    receipt = PartnerReceipt.model_validate(response.json())
    assert receipt.kind is ReceiptKind.INSURER_GUARANTEE
    assert verify_receipt(receipt, PARTNER_SECRETS["insurer"])


def test_adjuster_sandbox_issues_rejection_then_acceptance() -> None:
    client = TestClient(create_adjuster_app())
    body = {
        "mission_id": "mission-demo",
        "case_ref": "GA-DEMO",
        "owner_bond_signed": True,
        "insurer_guarantee_present": True,
        "declaration_reference_present": False,
    }
    rejected = PartnerReceipt.model_validate(
        client.post("/v1/security:review", json=body).json()
    )
    assert rejected.kind is ReceiptKind.ADJUSTER_REJECTION
    body["declaration_reference_present"] = True
    accepted = PartnerReceipt.model_validate(
        client.post("/v1/security:review", json=body).json()
    )
    assert accepted.kind is ReceiptKind.ADJUSTER_ACCEPTANCE


def test_carrier_sandbox_separates_order_from_readback() -> None:
    client = TestClient(create_carrier_app())
    order_response = client.post(
        "/v1/releases:issue",
        json={
            "mission_id": "mission-demo",
            "container_ref": "TCLU-482019-7",
            "adjuster_acceptance_ref": "ADJ-ACCEPTED",
        },
    )
    order = PartnerReceipt.model_validate(order_response.json())
    assert order.kind is ReceiptKind.CARRIER_RELEASE_ORDER
    readback = PartnerReceipt.model_validate(
        client.post(
            "/v1/releases:readback",
            json={
                "mission_id": "mission-demo",
                "container_ref": "TCLU-482019-7",
                "release_external_id": order.external_id,
            },
        ).json()
    )
    assert readback.kind is ReceiptKind.CARRIER_RELEASE_READBACK
    assert readback.payload["release_order_ref"] == order.external_id
