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

Create a demo mission with `POST /v1/missions/demo`, then use the bounded demo endpoints exposed in `/docs`. Every partner receipt is HMAC-signed by a distinct synthetic identity. `RELEASED` requires adjuster acceptance, carrier release order, and carrier read-back; the separate adjustment lifecycle remains `OPEN`.

## Truth labels

- `FIXTURE`: deterministic local evidence or partner sandbox.
- `ADAPTER`: a production-shaped port is present but not connected to a managed service.
- `NATIVE`: the request traversed a configured Google-managed surface and retained its receipt/trace identifier.

No production deployment, customer outreach, credential use, or external action is authorized by this repository.
