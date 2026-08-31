# Cargo Release

**A receipt-gated agent fleet for one of shipping’s strangest handoffs: getting fictional cargo
released after a General Average casualty without letting an AI become the insurer, adjuster, or
carrier.**

[Open the live Google Cloud deployment](https://cargo-release-web-1015646664425.us-central1.run.app)
· [Inspect the Alex v7 proof mission](https://cargo-release-web-1015646664425.us-central1.run.app/?mission=mission-13820650dbee)

| Submission artifact | Link |
|---|---|
| Demo video | `PENDING — replace with the public Alex v7 YouTube or Vimeo URL` |
| Hackathon blog post | `PENDING — replace with the public post URL` |
| Social post | `PENDING — replace with the public #AllThingsAgentic post URL` |
| Upstream OSS contribution | `PENDING — replace only after the ADK documentation PR is filed and verified` |

> **The twist:** agents do the work; receipts—not agents—hold the keys. One owner attestation can
> drive the security submission, rejection, correction, acceptance, carrier order, carrier
> read-back, and a marked operator notification, but physical release is a deterministic state
> transition gated by independently signed receipts.

Cargo Release targets **The Fortified Enterprise Fleet**. Its unlikely hero is the cargo-interest
operator caught between a casualty notice and three independent institutions. The demo is entirely
fictional and synthetic: it never decides coverage, liability, contribution, legal sufficiency, or
real cargo release.

## What the live mission does

1. Pub/Sub and Eventarc deliver an authenticated casualty CloudEvent. Duplicate delivery converges
   on one Cloud SQL mission.
2. The bounded controller reconciles five evidence sources. The public deployment uses a disclosed
   deterministic extraction fixture for the digest-bound synthetic adjuster scan while the Vertex
   Gemini adapter remains staged. The same deterministic policy validates its case, container,
   revision, checkbox, confidence, and correction field. Model-addressed email is quarantined.
3. The workflow stops at its only human gate. The operator attests the synthetic owner bond.
4. The controller autonomously obtains an insurer guarantee, submits security pack v1, preserves
   an adjuster rejection, and uses the validated scan's `missing_field` and source reference to
   produce v2. The model never decides whether that extraction is trusted.
5. The carrier independently issues a release order and confirms the read-back. Only then does
   physical cargo become `RELEASED`; the General Average adjustment remains `OPEN`.
6. A marked, idempotent Slack notice is delivered to the operator-owned endpoint after release. It
   explicitly says that no real cargo action occurred.

The managed workflow is deliberately dual-path: Eventarc and the authenticated web relay both call
the deterministic controller directly. Agent Runtime is a governed operator/delegation plane with
read-only inspection workers and one lease-protected resume tool; it is not falsely drawn as the
main Eventarc hop.

## Measured friction removed

The submission uses a falsifiable capability count, not an invented time-savings benchmark:

```text
1 human attestation
  → 5 unique signed partner receipts
  + 1 security submission
  + 1 automatic correction
  + 1 marked post-release notification
  = 8 autonomous downstream actions
```

The metric deduplicates receipt kinds, event types, and delivered notifications, so redelivery
cannot inflate it. Reproduce the invariant with:

```bash
cd web
npm ci
npm run test:metrics
```

The managed durability proof also sent the same casualty event six times concurrently across three
Cloud Run instances. All six requests returned successfully and converged on one declaration, one
run, and one human gate.

## Architecture

![Cargo Release Google Cloud authority architecture](docs/architecture.svg)

The diagram is intentionally an authority map, not a logo inventory:

- **Authenticated intake:** Pub/Sub → Eventarc and the public Next.js Cloud Run service’s
  fail-closed relay. The only media input is the prepared synthetic scan bound to the mission
  digest; there is no public upload surface.
- **ADK coordination plane:** one Gemini 3.5+ coordinator and four separately scoped sub-agents.
- **Deterministic authority:** a private Cloud Run controller is the sole writer to Cloud SQL for
  PostgreSQL. In Cloud Run, the default store selector refuses to initialize unless PostgreSQL is
  configured, so the automatic SQLite fallback is restricted to non-managed local execution.
- **Independent keys:** human owner attestation plus HMAC-signed insurer, adjuster, and carrier
  receipts from identity-isolated private Cloud Run fixtures.
- **Governance:** Agent Identity, Agent Gateway, Registry, Model Armor, Cloud Trace, structured
  spans, and reviewed Memory Bank facts.
- **Observable consequence:** receipt-gated physical release followed by exactly one marked
  synthetic Slack delivery.

### Hero technology

| Hero technology | Load-bearing role | Managed proof | Authority boundary |
|---|---|---|---|
| Vertex AI Agent Runtime + Gemini 3.5 Flash + Google ADK | One coordinator delegates to four separately scoped inspection workers | Managed invocation `e-3277014e-be11-4945-acc9-658e1c0bbbb6` | Workers are read-only and always return `release_authority=false` |
| Pub/Sub + Eventarc | Authenticated casualty ingress with native event and trace identifiers; duplicate delivery converges on one mission | Alex v6 message `21614781193876288` and mission `mission-13820650dbee` | Opening a mission cannot attest or release cargo |
| Private Cloud Run controller + Cloud SQL PostgreSQL 16 | The sole deterministic state writer evaluates versions, leases, validated evidence, human attestation, and signed receipts | Production health reports PostgreSQL; replay and concurrency acceptance tests pass | No model, browser, memory entry, or notification can write release state |
| Three identity-isolated Cloud Run partner services | Insurer, adjuster, and carrier independently issue issuer-bound, replay-safe receipts | Five verified receipts plus carrier read-back are retained in the v6 mission | A receipt advances only from an allowed prior state with a valid signature |
| Agent Identity, Agent Gateway, Registry, Model Armor, Memory Bank, Logging, and Trace | Govern egress, sanitize untrusted input, retain reviewed facts, and expose provenance | Truth-labelled managed resources and hash-linked mission activity | Cross-cutting controls observe or constrain the workflow; none authorize release |
| Secret Manager + marked Slack delivery | Protect the operator webhook and prove the post-read-back consequence | The v6 take shows the mission-matched message in the authenticated channel | Notification occurs after release and has `release_authority=false` |

### ADK agent roster

The managed agent tree is explicit and tool-scoped:

| ADK agent | Tool authority | Output boundary |
|---|---|---|
| `cargo_release_coordinator` | One `start_bounded_mission` tool | Performs one fail-closed preflight and at most one controller lease probe |
| `manifest_evidence_worker` | `inspect_evidence_scope` only | Statuses, fact keys, and digests; never raw evidence text |
| `security_pack_worker` | `inspect_security_scope` only | Human, insurer, adjuster, and artifact references; never receipt payloads |
| `carrier_authority_worker` | `inspect_authority_scope` only | Acceptance, order, and read-back references; never signatures |
| `runtime_recovery_worker` | `assess_runtime_recovery` only | Classifies durable state; cannot acquire a lease or advance |

Each worker uses structured output, cannot transfer to peers, inherits the eligible Gemini model,
and returns `release_authority=false`. Tool errors become a degraded report with
`retry_in_this_turn=false`. The controller’s atomic lease—not the model—decides whether a recorded
`RUNNING` operation is active or stale.

The receipt saga, notification service, model adapters, and adjustment monitor are deterministic
capability actors. They are shown separately and are not padded into the ADK agent count.

### Google AI models

The required coordinator uses `gemini-3.5-flash` through Vertex AI’s `global` endpoint while the
governed Agent Runtime remains in `us-central1`. The source fails closed if configured below Gemini
3.5.

The same Gemini family has a staged visual-intake adapter that extracts a typed
`adjuster-rejection-v1` record from the prepared PNG. The public deployment and Alex v6 demo use
the explicitly labelled deterministic extraction fixture because the managed adapter's valid-scan
attempt returned malformed structured output and correctly failed closed. In either mode,
deterministic validation—not model prose—must accept every expected field and confidence ≥ 0.85
before the evidence becomes trusted. A durable zero-authority receipt records the source artifact,
schema, validation outcome, digests, and request reference. Corrupt, ambiguous, or low-confidence
output leaves cargo `EVIDENCE_BLOCKED`.

Three additional Google models are integrated for the event’s optional model bonus:

| Bonus model | Product use | Managed proof | Authority boundary |
|---|---|---|---|
| Gemma 4 (`google/gemma-4-26b-a4b-it-maas`) | Reviews a sanitized owner-bond packet for a constrained checklist finding | Request `b2f4b88b-1a24-4ccb-9045-8f84fd57b3a8` persisted matching input/output digests | No tools; advisory receipt only; `release_authority=false` |
| Gemini Embedding 2 (`gemini-embedding-2`) | Ranks eight reviewed synthetic cases after deterministic filtering | Correlation `client-98a6bfd2408049f6a42e0e2812756438` returned the three labelled patterns at `recall@3=3/3` | Rank-only context; no scores, precedent claim, threshold, or release branch |
| Veo 3.1 Fast (`veo-3.1-fast-generate-001`) | Generates a four-second post-release synthetic training replay into private Cloud Storage | Operation `a79a8f4b-9403-4815-828f-ed755e41dd4f` produced the digest-verified product asset | Training-only, never evidence, not attached to the authoritative Slack notice, and `release_authority=false` |

Managed model failure remains visible and never blocks, approves, or advances cargo.

## Safety and authorization boundaries

- The browser can reach only an exact method/path allowlist in the server relay. Query forwarding,
  raw partner receipts, notifications, internal retries, and arbitrary controller mutations fail
  closed.
- The owner actor is injected by the authenticated web service; a browser-supplied actor is
  rejected.
- Agent Gateway is bound to the Agent Runtime identity with a fail-closed IAP authorization policy
  and an exact Registry endpoint allowlist.
- Prompt-injection-shaped evidence remains visible and quarantined. Scoped ADK workers never
  receive its raw text.
- Valid visual evidence and hostile text take separate paths: the scan survives only after typed
  extraction plus deterministic validation; the email produces an explicit quarantine event and
  no fact, memory entry, or state transition.
- Managed state requires Cloud SQL. SQLite is allowed only as an explicitly labeled local fixture.
- Every partner receipt is issuer-bound, signed, digest-addressed, idempotent, and valid only from
  an allowed prior state.
- Slack delivery is post-read-back, marked synthetic, allowlisted to Slack webhook hosts, and
  idempotent. The webhook URL lives only in Secret Manager and is never persisted or printed.
- Memory Bank stores reviewed post-release facts only. Model and memory output cannot write mission
  state.

## Run locally

Requirements: Python 3.12, Poetry, Node.js 24+, and npm.

Terminal 1 — deterministic fixture controller:

```bash
poetry install
poetry run uvicorn cargo_release.api:app --host 127.0.0.1 --port 8095
```

Terminal 2 — Next.js mission room:

```bash
cd web
npm ci
npm run dev
```

Open <http://127.0.0.1:3024>. The local path uses synthetic evidence, local partner fixtures, and
SQLite; it sends no Slack message and makes no real-party call.

Optional deterministic model fixtures:

```bash
export CARGO_RELEASE_GEMMA_CRITIC_ENABLED=1
export CARGO_RELEASE_GEMMA_CRITIC_MODE=FIXTURE
export CARGO_RELEASE_EMBEDDING_RETRIEVAL_ENABLED=1
export CARGO_RELEASE_EMBEDDING_RETRIEVAL_MODE=FIXTURE
export CARGO_RELEASE_VEO_REPLAY_ENABLED=1
export CARGO_RELEASE_VEO_REPLAY_MODE=FIXTURE
export CARGO_RELEASE_MULTIMODAL_MODE=FIXTURE
```

For the managed visual extractor, set `CARGO_RELEASE_MULTIMODAL_MODE=VERTEX` plus the existing
model project/location configuration. The light multimodal build is live at the public URL above.
Its extraction path remains in deterministic `FIXTURE` mode until a separately staged Vertex
configuration passes managed proof and promotion.

## Reproducible verification

Default local contract:

```bash
poetry run ruff check src tests
poetry run mypy src
poetry run pytest

cd web
npm run test:relay
npm run test:metrics
npm run check
npm run build
npm run test:e2e
```

The five PostgreSQL acceptance tests are intentionally skipped unless
`CARGO_RELEASE_TEST_DATABASE_URL` points to a disposable PostgreSQL database. They prove restart
persistence, duplicate-event convergence, lease exclusion, duplicate-receipt safety, and model
receipt persistence:

```bash
export CARGO_RELEASE_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:5432/cargo_release_test'
poetry run pytest tests/test_postgres_store.py
```

Managed probes are explicit and state-changing; run them only against an operator-approved test
project:

- `scripts/probe_managed_cloudsql.py`
- `scripts/probe_managed_bonus_models.py`
- `scripts/probe_managed_notification.py`
- `web/scripts/rehearse-production.mjs` (read-only retained-mission rehearsal)

## Managed deployment inventory

Project: `ata-2026-cargo` · primary region: `us-central1` · model inference: `global`

| Surface | Managed proof |
|---|---|
| Public product | `cargo-release-web` on Cloud Run |
| Deterministic controller | Private `cargo-release-controller` on Cloud Run |
| Durable authority | Cloud SQL PostgreSQL 16 instance `cargo-release-postgres` |
| Agent runtime | Vertex AI Agent Runtime + Agent Identity + automatic Registry entry |
| Event intake | Pub/Sub + Eventarc with retained CloudEvent and trace identifiers |
| Multimodal intake | Prepared PNG → deterministic fixture extraction → policy validation is live; the Vertex adapter is implemented but pending managed activation proof |
| Partner boundary | Three private Cloud Run services with separate service accounts |
| Governance | Agent Gateway, IAP request authorization, Registry, Model Armor |
| Advisory models | Vertex AI Gemma 4, Gemini Embedding 2, and Veo 3.1 Fast |
| Reviewed memory | Vertex AI Memory Bank, post-release facts only |
| Operator consequence | Secret Manager-backed Slack incoming webhook |
| Observability | Cloud Logging, Cloud Trace, structured mission spans and hash-linked events |

Current light multimodal build, promoted 2026-08-30 after a zero-traffic stage and smoke test:

- controller `cargo-release-controller-00023-hay` at 100%, with `00021-tac` retained Ready for
  rollback;
- web `cargo-release-web-00018-jam` at 100%, with `00016-nol` retained Ready for rollback;
- public light-theme smoke: health `200`, forbidden relay `404`, query forwarding `400`, PostgreSQL
  authority, held state, and five prepared evidence sources;
- managed four-worker invocation `e-3277014e-be11-4945-acc9-658e1c0bbbb6` on Gemini 3.5 Flash;
- canonical post-promotion rehearsal: 11 assertions and 5 captures passed, including Eventarc
  provenance, the Authority Map, Slack proof, all three bonus-model receipts, and the deterministic
  transition boundary.

The first continuous take exposed a provider-valid Eventarc trace without the optional sampling
suffix. Commit `59b2aed` repairs only that trace grammar. The operator approved the exact repaired
pair and rollback pair; `deploy/promote_recording_candidate.sh` promoted controller first, verified
PostgreSQL health, promoted web, and passed canonical relay results `200/404/400`. Independent
traffic/image audit confirmed both serving revisions and both rollback revisions Ready on immutable
digests.

The Alex v7 candidate preserves the complete Alex v6 continuous Proof-of-Action run, which
published Pub/Sub message `21614781193876288` and recorded mission `mission-13820650dbee` from
native Eventarc intake through one owner attestation, the retained adjuster rejection and
correction, five verified receipts, carrier read-back, and a marked Slack delivery. Final state is
physical cargo `RELEASED`, General Average adjustment `OPEN`, and run `COMPLETED`; visual extraction
is truth-labelled `FIXTURE` / `ACCEPTED`.

The 1920×1080 H.264/AAC v7 master is 208.80 seconds and peaks at -2 dB with no detected black
frames. The live application segment remains the exact 196.84-second continuous v6 source with zero
cuts or splices. Two disclosed master edits insert a 12-second Google Cloud Console proof beat after
the completed product flow and before the architecture walkthrough. At 0:08, the public `.run.app`
URL appears beside the native Eventarc mission and Pub/Sub message ID. At 2:06, Cloud Run shows
project `ata-2026-cargo`, controller `cargo-release-controller`, region `us-central1`, and logs
filtered to the same mission returning `200 OK`. The architecture scene then names the exact Google
Cloud service at each step. The v7 SHA-256 is
`7be77bcf201c6a9bac27f682e50437441fb004998bfa9d1d364e859a106ede7d`. Older v2–v6 candidates
remain preserved; publication and logged-out 1080p verification remain operator-owned external
actions.

Deployment helpers are under `deploy/`. They default to zero-traffic or fail-closed staging where
supported and retain rollback revisions. Do not run the Slack configurator in a transcript: it uses
a hidden prompt specifically to keep the bearer webhook out of shell history and chat.

## Truth labels

- `NATIVE`: the request retained a Google-managed resource, event, operation, or trace identifier.
- `ADAPTER`: production-shaped code or configuration exists but this mission has no managed
  receipt for that surface.
- `FIXTURE`: declared synthetic evidence, partner data, or local behavior.

The live interface applies these labels per mission. It never upgrades a local fixture merely
because a Google Cloud service exists elsewhere in the project.

## Demo safety statement

Cargo Release demonstrates architecture and workflow control with fictional data. “Released” means
the synthetic mission reached its deterministic terminal state after verified fixture receipts. It
does not release real cargo, communicate a legal conclusion, settle General Average contribution,
or instruct a real insurer, adjuster, carrier, terminal, or cargo owner.
