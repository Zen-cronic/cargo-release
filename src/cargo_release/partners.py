from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from cargo_release.models import PartnerReceipt, ReceiptKind, utc_now
from cargo_release.security import sign_receipt

PARTNER_SECRETS = {
    "insurer": os.getenv("CARGO_RELEASE_INSURER_SECRET", "demo-insurer-secret"),
    "adjuster": os.getenv("CARGO_RELEASE_ADJUSTER_SECRET", "demo-adjuster-secret"),
    "carrier": os.getenv("CARGO_RELEASE_CARRIER_SECRET", "demo-carrier-secret"),
}


def _issue(
    issuer: str,
    mission_id: str,
    kind: ReceiptKind,
    subject_ref: str,
    status: str,
    payload: dict[str, Any],
) -> PartnerReceipt:
    receipt = PartnerReceipt(
        mission_id=mission_id,
        kind=kind,
        issuer=issuer,
        external_id=f"{issuer[:3].upper()}-{uuid4().hex[:10].upper()}",
        subject_ref=subject_ref,
        status=status,
        issued_at=utc_now(),
        payload=payload,
    )
    return sign_receipt(receipt, PARTNER_SECRETS[issuer])


def issue_insurer_guarantee(mission_id: str, case_ref: str) -> PartnerReceipt:
    return _issue(
        "insurer",
        mission_id,
        ReceiptKind.INSURER_GUARANTEE,
        case_ref,
        "ISSUED",
        {"guarantee_ref": f"GUAR-{case_ref}", "coverage_decision": "NOT_MADE"},
    )


def issue_adjuster_review(
    mission_id: str, case_ref: str, *, declaration_reference_present: bool
) -> PartnerReceipt:
    if declaration_reference_present:
        return _issue(
            "adjuster",
            mission_id,
            ReceiptKind.ADJUSTER_ACCEPTANCE,
            case_ref,
            "FULL_SECURITY_ACCEPTED",
            {"security_scope": "owner bond + insurer guarantee", "legal_opinion": "NOT_MADE"},
        )
    return _issue(
        "adjuster",
        mission_id,
        ReceiptKind.ADJUSTER_REJECTION,
        case_ref,
        "CORRECTION_REQUIRED",
        {"missing": ["declaration reference on owner bond"]},
    )


def issue_carrier_release(mission_id: str, container_ref: str) -> PartnerReceipt:
    return _issue(
        "carrier",
        mission_id,
        ReceiptKind.CARRIER_RELEASE_ORDER,
        container_ref,
        "RELEASE_ORDERED",
        {"container_ref": container_ref, "terminal": "North Harbor T4"},
    )


def issue_carrier_readback(
    mission_id: str, container_ref: str, release_external_id: str
) -> PartnerReceipt:
    return _issue(
        "carrier",
        mission_id,
        ReceiptKind.CARRIER_RELEASE_READBACK,
        container_ref,
        "RELEASE_VISIBLE",
        {"container_ref": container_ref, "release_order_ref": release_external_id},
    )


class GuaranteeRequest(BaseModel):
    mission_id: str
    case_ref: str
    owner_bond_approved: bool


class ReviewRequest(BaseModel):
    mission_id: str
    case_ref: str
    owner_bond_signed: bool
    insurer_guarantee_present: bool
    declaration_reference_present: bool


class ReleaseRequest(BaseModel):
    mission_id: str
    container_ref: str
    adjuster_acceptance_ref: str


class ReadbackRequest(BaseModel):
    mission_id: str
    container_ref: str
    release_external_id: str


def create_insurer_app() -> FastAPI:
    app = FastAPI(title="Cargo Release — Insurer Sandbox")

    @app.post("/v1/guarantees:issue", response_model=PartnerReceipt)
    def guarantee(request: GuaranteeRequest) -> PartnerReceipt:
        if not request.owner_bond_approved:
            raise HTTPException(409, "Owner bond approval is required")
        return issue_insurer_guarantee(request.mission_id, request.case_ref)

    return app


def create_adjuster_app() -> FastAPI:
    app = FastAPI(title="Cargo Release — Adjuster Sandbox")

    @app.post("/v1/security:review", response_model=PartnerReceipt)
    def review(request: ReviewRequest) -> PartnerReceipt:
        if not request.owner_bond_signed or not request.insurer_guarantee_present:
            raise HTTPException(409, "Full security pack has not been submitted")
        return issue_adjuster_review(
            request.mission_id,
            request.case_ref,
            declaration_reference_present=request.declaration_reference_present,
        )

    return app


def create_carrier_app() -> FastAPI:
    app = FastAPI(title="Cargo Release — Carrier Sandbox")

    @app.post("/v1/releases:issue", response_model=PartnerReceipt)
    def release(request: ReleaseRequest) -> PartnerReceipt:
        if not request.adjuster_acceptance_ref:
            raise HTTPException(409, "Adjuster acceptance receipt is required")
        return issue_carrier_release(request.mission_id, request.container_ref)

    @app.post("/v1/releases:readback", response_model=PartnerReceipt)
    def readback(request: ReadbackRequest) -> PartnerReceipt:
        return issue_carrier_readback(
            request.mission_id, request.container_ref, request.release_external_id
        )

    return app


insurer_app = create_insurer_app()
adjuster_app = create_adjuster_app()
carrier_app = create_carrier_app()
