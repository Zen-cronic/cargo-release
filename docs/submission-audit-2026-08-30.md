# Cargo Release submission audit — updated 2026-08-31

Audit basis: local `main`, anonymous GitHub access, logged-out production, the synchronized
submission media package, and the verified Alex v7 Console-proof master. Deadline: 2026-08-31
20:00 EDT. This is not a final all-pass audit because the public social and Devpost URLs remain
operator-owned gates.

| Risk order | Gate | Status | Evidence | Fix by |
|---:|---|---|---|---|
| 1 | Exact judge-visible repository | **PASS** | `https://github.com/Zen-cronic/cargo-release` is public. Anonymous requests return `200` for the repository, raw README, MIT license, and architecture PNG. Current and historical commits contain no token-shaped secret or tracked private-key file. | — |
| 2 | Exact final light/multimodal video | **PARTIAL** | Alex v7 passes locally at 1920×1080, 208.80 seconds, -2 dB peak, and no detected black frames. Its 196.84-second live application source remains continuous; a disclosed 12-second mission-matched Console insert proves Cloud Run before architecture. `https://youtu.be/mBSkNDSCHJY` returns `200`, but the operator's logged-out 1080p playback check remains. | Before submission |
| 3 | Live Vertex visual extraction claim | **BLOCKED** | Zero-traffic Gemini 3.5 candidates produced `NATIVE`, zero-authority degraded receipts and left missions at version 0, but the valid prepared scan returned non-JSON text and never reached deterministic acceptance. Production remains the disclosed fixture path. | 2026-08-31 12:00 EDT decision |
| 4 | Logged-out hosted app | **PASS** | Public `.run.app` health is `200`, PostgreSQL-backed, light by default, and horizontally stable. | — |
| 5 | Architecture image | **PASS** | Submission PNG is a 3600×2400 render of the current tracked SVG, including exact service names and the corrected verified-receipt edge. | — |
| 6 | Thumbnail and gallery media | **PASS** | The project-thumbnail upload packet now includes an inspected 1800×1200 JPG (277,473 bytes) plus PNG fallback, both exact 3:2 and under 5 MB; the original 16:9 asset is preserved. Two versioned 3:2 gallery PNGs preserve the complete light-theme evidence and quarantine views. | — |
| 7 | Required Gemini/ADK/GCP stack | **PASS** | Retained managed proof covers Gemini 3.5 Flash, root plus four scoped ADK workers, Cloud Run, Cloud SQL, Pub/Sub/Eventarc, and zero model authority. | — |
| 8 | Reproducible testing and license | **PASS** | README contains local, browser, PostgreSQL, and managed-probe instructions; GitHub detects the MIT license. Current rerun: Ruff clean, strict mypy clean across 18 source files, backend 64 passed / 5 skipped, frontend metric and relay tests passed, and TypeScript check passed. | — |
| 9 | New-project disclosure | **PASS** | The Devpost draft states the August 3–31 build window, standard tooling, and no incorporated pre-existing project code. | — |
| 10 | Rollback and judging-window health | **PASS** | Serving pair `00023-hay` / `00018-jam`; immediate pair `00021-tac` / `00016-nol` is Ready on immutable images. | Monitor through judging |
| 11 | Submission documentation consistency | **PASS** | README, checkpoint, Devpost draft, v7 runbook, architecture, bonus-model status, and media filenames share the same v7 and fixture-truth boundary. | — |
| 12 | Public blog bonus | **PARTIAL** | `https://dev.to/zin_kg/i-built-an-ai-cargo-fleet-that-never-holds-the-key-474k` returns `200`; purpose language, final links, cover, and four images pass. Dev.to rendered 84 hard `<br>` tags across 44 prose paragraphs from source wrapping. The synchronized local source is mechanically unwrapped and ready to repaste. | Before submission |
| 13 | Public social bonus | **BLOCKED** | The X copy and media are ready, but no public post URL has been supplied or verified. | Before submission |
| 14 | Public Devpost project URL | **PARTIAL** | `https://devpost.com/software/cargo-release` is recorded, but a logged-out request currently resolves to Devpost's login page. Confirm **My Projects** shows the green **Submitted** state; final public visibility may still depend on organizer moderation/gallery publication. | Before deadline |

## Submission truth boundary

- Do not describe the public visual-extraction path as live Vertex Gemini unless a later guarded
  candidate accepts the prepared scan and the persisted receipt is `NATIVE`, `COMPLETED`,
  `ACCEPTED`, digest-bound, and `release_authority=false`.
- It is accurate to say the public app demonstrates the deterministic multimodal workflow with a
  disclosed fixture and that a managed Gemini failure was proven to fail closed without mutation.
- The retained ADK Gemini 3.5 managed proof remains valid and is separate from the blocked visual
  extraction packet.

## Final judge-view audit gate

Rerun after the social URL has replaced its placeholder and Devpost shows the green **Submitted**
state.
Verify every artifact logged out, play `https://youtu.be/mBSkNDSCHJY` at 1080p, compare every claim
with the deployed app, and freeze the repository, video, and linked artifacts after the deadline.
