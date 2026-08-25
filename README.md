# Cargo Release

Working name for a Fortified Enterprise Fleet hackathon candidate. Cargo Release coordinates a fictional General Average security mission from casualty notice to independently verified cargo release.

The deterministic controller—not an LLM—owns mission state. Agents may reconcile evidence and draft artifacts, while human approval and signed insurer, adjuster, and carrier receipts gate consequential transitions. The demo never contacts a real party and never decides coverage, liability, contribution, or legal sufficiency.

## Local backend

This repository follows the workspace Python contract:

```bash
export VIRTUAL_ENV="$HOME/.pyenv/versions/.cargo-release"
export PATH="$VIRTUAL_ENV/bin:$PATH"
poetry install
poetry run uvicorn cargo_release.api:app --reload --port 8095
```

Create a demo mission with `POST /v1/missions/demo`, then call `POST /v1/missions/{id}:run`. The bounded runtime reconciles evidence, generates the owner-bond artifact, and yields at the human approval gate. `POST /v1/missions/{id}/approvals/owner-bond:approve-and-resume` records that attestation and autonomously completes insurer issuance, adjuster rejection and correction, acceptance, carrier release order, and carrier read-back.

Every partner receipt is HMAC-signed by a distinct synthetic identity. `RELEASED` requires adjuster acceptance, carrier release order, and carrier read-back; the separate adjustment lifecycle remains `OPEN`. Runtime leases prevent concurrent execution, the 12-step cap stops loops, completed transitions are resumable, and artifacts retain immutable content digests and revisions.

## Google-managed execution path

The deployable vertical slice keeps the same deterministic controller while adding managed
execution evidence:

- Pub/Sub and Eventarc deliver a real CloudEvent envelope to an idempotent casualty endpoint.
- an ADK coordinator deploys to Agent Runtime with Agent Identity, bounded inspect/advance tools,
  and a fail-closed Gemini 3.5+ eligibility guard; its model inference uses Vertex AI's `global`
  endpoint while the governed runtime remains in `us-central1`;
- private insurer, adjuster, and carrier Cloud Run services are invoked with Google-signed ID
  tokens and return separately signed receipts;
- the public Next.js shell relays same-origin requests through its server runtime, which uses the
  web service identity to invoke the private controller with a Google-signed ID token;
- Memory Bank receives reviewed post-release facts only; it cannot mutate mission state; and
- Agent Registry, Agent Gateway, Model Armor, and Agent Observability provide discovery,
  policy-enforced routing, inline screening, and end-to-end telemetry.

Local execution remains deterministic and labels all unconnected surfaces honestly. See the
[per-project Google Cloud setup checklist](../submission/cargo-release/google-cloud-setup-checklist.md)
and [`deploy/service-inventory.yaml`](deploy/service-inventory.yaml) for the exact service boundary.
The current SQLite controller is an explicit single-instance judging proof, not a
production-durability claim.

## Local frontend

```bash
cd web
npm install
npm run dev
```

Open `http://127.0.0.1:3024`. The default Mission view keeps the business consequence and the only open decision in frame; Evidence, generated Documents, partner Receipts, and hash-linked Activity are progressively disclosed in separate workspaces.

## Verification

```bash
export VIRTUAL_ENV="$HOME/.pyenv/versions/.cargo-release"
export PATH="$VIRTUAL_ENV/bin:$PATH"
poetry run pytest
poetry run ruff check src tests
poetry run mypy src
cd web
npm run check
npm run build
npm run test:e2e
```

Current local checkpoint: 21 backend/API/partner tests and two Playwright journeys pass. The browser suite proves the one-start/one-approval release, generated security-pack inspection, prompt-injection quarantine, and architecture truth labels. The backend suite also covers the real Pub/Sub envelope, Eventarc idempotency, managed-label fail-closed gates, reviewed memory, private-partner selection, and native provenance propagation.

## Truth labels

- `FIXTURE`: deterministic local evidence or partner sandbox.
- `ADAPTER`: a production-shaped port is present but not connected to a managed service.
- `NATIVE`: the request traversed a configured Google-managed surface and retained its receipt/trace identifier.

No production deployment, customer outreach, credential use, or external action is authorized by this repository.
