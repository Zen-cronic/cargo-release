from __future__ import annotations

import os

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cargo_release.engine import CargoReleaseEngine, DomainError, IdentityError
from cargo_release.models import MissionSnapshot, ReceiptEnvelope, ReceiptKind, VersionedAction
from cargo_release.partners import (
    issue_adjuster_review,
    issue_carrier_readback,
    issue_carrier_release,
    issue_insurer_guarantee,
)
from cargo_release.runtime import MissionOrchestrator
from cargo_release.security import ReceiptSecurityError
from cargo_release.store import MissionNotFound, SQLiteMissionStore, StoreError


def create_app(database_path: str | None = None) -> FastAPI:
    path: str = (
        database_path
        if database_path is not None
        else os.environ.get("CARGO_RELEASE_DB", "var/cargo-release.db")
    )
    store = SQLiteMissionStore(path)
    engine = CargoReleaseEngine(store)
    runtime = MissionOrchestrator(engine)
    app = FastAPI(
        title="Cargo Release Mission API",
        version="0.1.0",
        description="Synthetic General Average security-to-release workflow.",
    )
    app.state.engine = engine
    app.state.runtime = runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3024", "http://localhost:3024"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(StoreError)
    async def handle_store_error(_request: Request, error: StoreError) -> JSONResponse:
        status = 404 if isinstance(error, MissionNotFound) else 409
        return JSONResponse(status_code=status, content={"detail": str(error)})

    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, error: DomainError) -> JSONResponse:
        status = 403 if isinstance(error, IdentityError) else 409
        return JSONResponse(status_code=status, content={"detail": str(error)})

    @app.exception_handler(ReceiptSecurityError)
    async def handle_security_error(_request: Request, error: ReceiptSecurityError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(error)})

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "FIXTURE"}

    @app.post("/v1/missions/demo", response_model=MissionSnapshot)
    def create_demo() -> MissionSnapshot:
        return engine.create_demo_mission()

    @app.get("/v1/missions/{mission_id}", response_model=MissionSnapshot)
    def get_mission(mission_id: str) -> MissionSnapshot:
        return store.snapshot(mission_id)

    @app.post("/v1/missions/{mission_id}:analyze", response_model=MissionSnapshot)
    def analyze(mission_id: str, action: VersionedAction) -> MissionSnapshot:
        return engine.analyze_evidence(mission_id, action)

    @app.post("/v1/missions/{mission_id}:run", response_model=MissionSnapshot)
    def run_mission(mission_id: str) -> MissionSnapshot:
        return runtime.run(mission_id)

    @app.post("/v1/missions/{mission_id}/approvals/owner-bond", response_model=MissionSnapshot)
    def approve(mission_id: str, action: VersionedAction) -> MissionSnapshot:
        return engine.approve_owner_bond(mission_id, action)

    @app.post(
        "/v1/missions/{mission_id}/approvals/owner-bond:approve-and-resume",
        response_model=MissionSnapshot,
    )
    def approve_and_resume(mission_id: str, action: VersionedAction) -> MissionSnapshot:
        engine.approve_owner_bond(mission_id, action)
        return runtime.run(mission_id)

    @app.post("/v1/missions/{mission_id}:submit-security", response_model=MissionSnapshot)
    def submit(mission_id: str, action: VersionedAction) -> MissionSnapshot:
        return engine.submit_security(mission_id, action)

    @app.post("/v1/missions/{mission_id}:correct-security", response_model=MissionSnapshot)
    def correct(mission_id: str, action: VersionedAction) -> MissionSnapshot:
        return engine.correct_security(mission_id, action)

    @app.post("/v1/partner-receipts")
    def accept_receipt(
        envelope: ReceiptEnvelope, x_partner_identity: str = Header(...)
    ) -> dict[str, object]:
        snapshot, created = engine.apply_partner_receipt(envelope.receipt, x_partner_identity)
        return {"created": created, "snapshot": snapshot.model_dump(mode="json")}

    @app.post("/v1/missions/{mission_id}/demo/insurer", response_model=MissionSnapshot)
    def demo_insurer(mission_id: str) -> MissionSnapshot:
        snapshot = store.snapshot(mission_id)
        if not any(item.kind == "OWNER_BOND" for item in snapshot.approvals):
            raise DomainError("Owner bond approval is required before guarantee issuance")
        receipt = issue_insurer_guarantee(mission_id, snapshot.mission.case_ref)
        return engine.apply_partner_receipt(receipt, "partner:insurer")[0]

    @app.post("/v1/missions/{mission_id}/demo/adjuster", response_model=MissionSnapshot)
    def demo_adjuster(mission_id: str) -> MissionSnapshot:
        snapshot = store.snapshot(mission_id)
        corrected = any(event.event_type == "SECURITY_PACK_CORRECTED" for event in snapshot.events)
        receipt = issue_adjuster_review(
            mission_id,
            snapshot.mission.case_ref,
            declaration_reference_present=corrected,
        )
        return engine.apply_partner_receipt(receipt, "partner:adjuster")[0]

    @app.post("/v1/missions/{mission_id}/demo/carrier-release", response_model=MissionSnapshot)
    def demo_carrier_release(mission_id: str) -> MissionSnapshot:
        snapshot = store.snapshot(mission_id)
        receipt = issue_carrier_release(mission_id, snapshot.mission.container_ref)
        return engine.apply_partner_receipt(receipt, "partner:carrier")[0]

    @app.post("/v1/missions/{mission_id}/demo/carrier-readback", response_model=MissionSnapshot)
    def demo_carrier_readback(mission_id: str) -> MissionSnapshot:
        snapshot = store.snapshot(mission_id)
        release = next(
            (item for item in snapshot.receipts if item.kind is ReceiptKind.CARRIER_RELEASE_ORDER),
            None,
        )
        if release is None:
            raise DomainError("Carrier release order is required before read-back")
        receipt = issue_carrier_readback(
            mission_id, snapshot.mission.container_ref, release.external_id
        )
        return engine.apply_partner_receipt(receipt, "partner:carrier")[0]

    return app


app = create_app()
