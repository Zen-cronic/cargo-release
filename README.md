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

Current local checkpoint: 15 backend/API/partner tests and two Playwright journeys pass. The browser suite proves the one-start/one-approval release, generated security-pack inspection, prompt-injection quarantine, and architecture truth labels.

## Truth labels

- `FIXTURE`: deterministic local evidence or partner sandbox.
- `ADAPTER`: a production-shaped port is present but not connected to a managed service.
- `NATIVE`: the request traversed a configured Google-managed surface and retained its receipt/trace identifier.

No production deployment, customer outreach, credential use, or external action is authorized by this repository.
