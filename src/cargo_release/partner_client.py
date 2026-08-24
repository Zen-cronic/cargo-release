from __future__ import annotations

import os
from typing import Protocol

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from cargo_release.models import MissionSnapshot, PartnerReceipt, ReceiptKind, TruthMode
from cargo_release.partners import (
    issue_adjuster_review,
    issue_carrier_readback,
    issue_carrier_release,
    issue_insurer_guarantee,
)


class PartnerPort(Protocol):
    truth_mode: TruthMode

    def insurer_guarantee(self, snapshot: MissionSnapshot) -> PartnerReceipt: ...
    def adjuster_review(self, snapshot: MissionSnapshot, *, corrected: bool) -> PartnerReceipt: ...
    def carrier_release(self, snapshot: MissionSnapshot) -> PartnerReceipt: ...
    def carrier_readback(
        self, snapshot: MissionSnapshot, release_external_id: str
    ) -> PartnerReceipt: ...


class LocalPartnerFixtures:
    truth_mode = TruthMode.FIXTURE

    def insurer_guarantee(self, snapshot: MissionSnapshot) -> PartnerReceipt:
        return issue_insurer_guarantee(snapshot.mission.id, snapshot.mission.case_ref)

    def adjuster_review(self, snapshot: MissionSnapshot, *, corrected: bool) -> PartnerReceipt:
        return issue_adjuster_review(
            snapshot.mission.id,
            snapshot.mission.case_ref,
            declaration_reference_present=corrected,
        )

    def carrier_release(self, snapshot: MissionSnapshot) -> PartnerReceipt:
        return issue_carrier_release(snapshot.mission.id, snapshot.mission.container_ref)

    def carrier_readback(
        self, snapshot: MissionSnapshot, release_external_id: str
    ) -> PartnerReceipt:
        return issue_carrier_readback(
            snapshot.mission.id,
            snapshot.mission.container_ref,
            release_external_id,
        )


class CloudRunPartnerServices:
    truth_mode = TruthMode.NATIVE

    def __init__(self, insurer_url: str, adjuster_url: str, carrier_url: str) -> None:
        self.insurer_url = insurer_url.rstrip("/")
        self.adjuster_url = adjuster_url.rstrip("/")
        self.carrier_url = carrier_url.rstrip("/")

    @staticmethod
    def _post(base_url: str, path: str, payload: dict[str, object]) -> PartnerReceipt:
        token: str = id_token.fetch_id_token(  # type: ignore[no-untyped-call]
            Request(), base_url
        )
        with httpx.Client(base_url=base_url, timeout=30) as client:
            response = client.post(
                path,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return PartnerReceipt.model_validate(response.json())

    def insurer_guarantee(self, snapshot: MissionSnapshot) -> PartnerReceipt:
        return self._post(
            self.insurer_url,
            "/v1/guarantees:issue",
            {
                "mission_id": snapshot.mission.id,
                "case_ref": snapshot.mission.case_ref,
                "owner_bond_approved": bool(snapshot.approvals),
            },
        )

    def adjuster_review(self, snapshot: MissionSnapshot, *, corrected: bool) -> PartnerReceipt:
        return self._post(
            self.adjuster_url,
            "/v1/security:review",
            {
                "mission_id": snapshot.mission.id,
                "case_ref": snapshot.mission.case_ref,
                "owner_bond_signed": bool(snapshot.approvals),
                "insurer_guarantee_present": bool(snapshot.receipts),
                "declaration_reference_present": corrected,
            },
        )

    def carrier_release(self, snapshot: MissionSnapshot) -> PartnerReceipt:
        acceptance = next(
            item for item in snapshot.receipts if item.kind is ReceiptKind.ADJUSTER_ACCEPTANCE
        )
        return self._post(
            self.carrier_url,
            "/v1/releases:issue",
            {
                "mission_id": snapshot.mission.id,
                "container_ref": snapshot.mission.container_ref,
                "adjuster_acceptance_ref": acceptance.external_id,
            },
        )

    def carrier_readback(
        self, snapshot: MissionSnapshot, release_external_id: str
    ) -> PartnerReceipt:
        return self._post(
            self.carrier_url,
            "/v1/releases:readback",
            {
                "mission_id": snapshot.mission.id,
                "container_ref": snapshot.mission.container_ref,
                "release_external_id": release_external_id,
            },
        )


def build_partner_port() -> PartnerPort:
    urls = (
        os.getenv("CARGO_RELEASE_INSURER_URL"),
        os.getenv("CARGO_RELEASE_ADJUSTER_URL"),
        os.getenv("CARGO_RELEASE_CARRIER_URL"),
    )
    on_cloud_run = bool(os.getenv("K_SERVICE") and os.getenv("GOOGLE_CLOUD_PROJECT"))
    if on_cloud_run and all(urls):
        insurer, adjuster, carrier = urls
        assert insurer is not None and adjuster is not None and carrier is not None
        return CloudRunPartnerServices(insurer, adjuster, carrier)
    return LocalPartnerFixtures()
