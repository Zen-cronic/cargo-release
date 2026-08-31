# Cargo Release — Devpost submission form

Concise paste-ready draft. Replace fields marked `PENDING` only after the linked artifact is public
and verified. The light multimodal build is deployed; its public extraction path remains in
deterministic `FIXTURE` mode until the separately staged Vertex configuration passes managed proof.

## Project Story — About the project

### Inspiration

After a General Average casualty, undamaged cargo can remain held while an owner, insurer,
adjuster, and carrier exchange evidence and authority. We wanted agents to remove that coordination
burden without quietly becoming the decision-maker.

### What it does

Cargo Release turns one synthetic casualty event into a receipt-gated release mission. A prepared
scan follows a typed extraction-and-validation contract while a hostile email is quarantined. One
human attests the owner bond; the fleet then submits security, preserves the v1 rejection, produces
v2, and collects signed insurer, adjuster, and carrier receipts. Cargo opens only after adjuster
acceptance and an independent carrier read-back. The adjustment remains open. The public demo
truthfully labels its extraction fixture; its managed Gemini adapter is staged and fails closed.

### How we built it

Gemini 3.5 Flash and ADK coordinate four tool-scoped workers. Pub/Sub and Eventarc open an
idempotent mission on Cloud Run. A private FastAPI controller is the sole Cloud SQL writer. The
visual adapter and disclosed production fixture share one typed, zero-authority receipt contract;
deterministic policy validates its digest, schema, case, container, revision, checkbox, and
confidence. Identity-bound partner services issue signed receipts. Next.js renders the
held/released bay, evidence, revisions, receipts, traces, and live Authority Map.

### Challenges we ran into

The hard part was separating useful model output from authority. We also had to make duplicate
events, concurrent resumes, stale versions, bad signatures, low-confidence scans, and prompt
injection fail closed without making the demo unreadable.

### Accomplishments that we're proud of

- One attestation produces eight duplicate-safe downstream actions.
- A valid image changes v2; hostile text changes nothing.
- Five issuer-bound receipts and a two-key rule—not model prose—open the container.
- Every transition remains reconstructable from Cloud SQL state, hashes, identities, and traces.

### What we learned

Agent autonomy is more credible when its limits are visible. Structured model receipts,
deterministic validation, durable rejection reasons, and independent authority make a failure path
more persuasive than a perfect happy path.

### What's next for Cargo Release

Activate and prove the managed Gemini visual extractor, add more partner adapters behind the same
receipt contract, and extend the open adjustment monitor without expanding model authority.

## Built with

Gemini 3.5 Flash, Google ADK, Vertex AI Agent Runtime, Cloud Run, Cloud SQL, Pub/Sub, Eventarc,
Agent Gateway, Agent Identity, Agent Registry, Model Armor, Cloud Trace, Cloud Logging, Memory Bank,
Gemma 4, Gemini Embedding 2, Veo 3.1 Fast, Next.js, FastAPI, PostgreSQL, Python, TypeScript

22 tags; Devpost allows 25.

## Try it out links

- Live app: https://cargo-release-web-1015646664425.us-central1.run.app
- Code: https://github.com/Zen-cronic/cargo-release
- Alex v7 proof mission: https://cargo-release-web-1015646664425.us-central1.run.app/?mission=mission-13820650dbee

## Public artifact links

| Artifact | Exact URL | Status |
|---|---|---|
| Hosted app | https://cargo-release-web-1015646664425.us-central1.run.app | Public |
| Proof mission | https://cargo-release-web-1015646664425.us-central1.run.app/?mission=mission-13820650dbee | Public |
| Source repository | https://github.com/Zen-cronic/cargo-release | Public |
| Demo video | https://youtu.be/mBSkNDSCHJY | Public URL supplied by operator |
| Upstream OSS PR | https://github.com/google/adk-docs/pull/2187 | Open; checks passing |
| Devpost project page | `PENDING — add after submission is saved/published` | Operator gate |
| Hackathon blog post | `PENDING — add after publishing and logged-out verification` | Operator gate |
| Social post | `PENDING — add after publishing and logged-out verification` | Operator gate |

## Project Media — Image gallery

Upload in this order; every image is PNG and under 5 MB. Caption counts use Unicode code points and
are all below the 140-character limit.

1. `/home/zin-kg/code/hackathons/allthingsagentic-2026/submission/cargo-release/architecture.png`

   Caption (127 characters): Authority map: authenticated intake, four scoped ADK workers, one Cloud SQL writer, independent receipts, and physical release.
2. `/home/zin-kg/code/hackathons/allthingsagentic-2026/submission/cargo-release/gallery/multimodal-correction-3x2.png`

   Caption (123 characters): A validated rejection scan causes security-pack v2 while hostile email text is quarantined and cannot change trusted state.
3. `/home/zin-kg/code/hackathons/allthingsagentic-2026/submission/cargo-release/gallery/quarantined-email-3x2.png`

   Caption (114 characters): Prompt-injection email quarantined with zero facts, memory, or transitions while the synthetic cargo remains HELD.

## Video demo link

https://youtu.be/mBSkNDSCHJY

The verified Alex v7 master is 208.80 seconds at 1920×1080. Its full live application execution
remains continuous and unedited; a disclosed 12-second, mission-matched Cloud Run Console proof
follows the product flow before the architecture walkthrough.

## Category

**Fortified Enterprise Fleet**

## What date did you start this project?

`08-23-26`

First commit: `ed20fef`, created during the submission period.

## New-project and pre-existing-work disclosure

Cargo Release was built during the August 3–31, 2026 submission period using standard frameworks,
open-source libraries, and AI coding assistants. No pre-existing project code was incorporated.

## URL to your public or private code repo

https://github.com/Zen-cronic/cargo-release

## Did you add Reproducible Testing instructions to your README?

**Yes.** The README includes local, browser, PostgreSQL acceptance, and managed-probe instructions.

## Hosted project URL

https://cargo-release-web-1015646664425.us-central1.run.app

## Testing instructions (judge-only)

No login. Start autonomous mission; compare the validated scan with the quarantined email; approve
the bond once; verify RELEASED while adjustment stays OPEN; inspect receipts and the Authority Map.
All data is synthetic; extraction is FIXTURE.

Mechanical Unicode count: **244 characters** (255-character field limit).

## Which Google SDK did you use?

| Form option | Select? | Evidence boundary |
|---|---:|---|
| ADK | **Yes** | Coordinator and four scoped workers import and use Google ADK. |
| Google GenAI SDK | **No** | No direct production-runtime use; the staged visual adapter calls Vertex AI REST. |
| Antigravity SDK | **No** | Not used. |
| Genkit | **No** | Not used. |
| Other | **No** | Vertex REST is transport, not another agent SDK. |

## Which Google Cloud Service(s) did you use?

| Form option | Select? |
|---|---:|
| Cloud Run | **Yes** |
| Cloud SQL | **Yes** |
| Pub/Sub | **Yes** |
| Firestore | **No** |
| Google Kubernetes Engine | **No** |

If free text is available, also name Eventarc, Vertex AI Agent Runtime, Cloud Trace, Cloud Logging,
Secret Manager, Agent Gateway, Agent Identity, Agent Registry, Model Armor, and Memory Bank.

## Architecture diagram

Upload `/home/zin-kg/code/hackathons/allthingsagentic-2026/submission/cargo-release/architecture.png`
(PNG, 3600×2400, under 5 MB). Editable source: `docs/architecture.svg`.

## Which Google AI Models did you use?

- **Select Gemini 3.5 Flash:** required managed ADK coordinator. A separate visual adapter is staged; the
  public demo uses the disclosed deterministic extraction fixture after managed malformed output
  correctly failed closed.
- **Select Gemma 4:** sanitized proposal critic, no tools or authority.
- **Select Gemini Embedding 2:** rank-only retrieval over reviewed synthetic cases.
- **Select Veo 3.1 Fast:** post-release synthetic training replay, never evidence.
- **Do not select Lyria:** not used.

## Optional bonus — public content

`PENDING — public URL.` Publish-ready local draft: `blog.md`. It states that the article was created
for the purposes of entering the All Things Agentic Hackathon. Replace this field only after the
article is public and verified logged out.

## Optional bonus — social post

`PENDING — public X URL.` Character-budgeted local draft: `social.md`; it contains
`#AllThingsAgentic Hackathon`. Replace this field only after the post and attached media are public.

## Upstream OSS contribution

[google/adk-docs#2187](https://github.com/google/adk-docs/pull/2187) — open documentation PR,
verified publicly on 2026-08-31 with its Google CLA, header, and change checks passing. Do not
describe it as accepted or merged unless GitHub shows that state.
