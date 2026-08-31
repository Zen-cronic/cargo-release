# Cargo Release submission audit — updated 2026-08-31

Audit basis: local `main`, logged-out production, the synchronized submission media package, and
the verified Alex v7 Console-proof master. Deadline: 2026-08-31 20:00 EDT. This is not a final all-pass
audit because repository access and the public video URL remain operator-owned gates.

| Risk order | Gate | Status | Evidence | Fix by |
|---:|---|---|---|---|
| 1 | Exact judge-visible repository | **BLOCKED** | Logged-out GitHub returns `404`; local `main` is ahead of `origin/main`. Push the final documentation commits, then make the repository public or verify both named judge accounts have access. | 2026-08-31 14:00 EDT |
| 2 | Exact final light/multimodal video | **BLOCKED** | Alex v7 passes locally at 1920×1080, 208.80 seconds, -2 dB peak, and no detected black frames. Its 196.84-second live application source remains continuous; a disclosed 12-second mission-matched Console insert proves Cloud Run before architecture. Public YouTube/Vimeo and logged-out 1080p verification are still missing. | 2026-08-31 14:00 EDT |
| 3 | Live Vertex visual extraction claim | **BLOCKED** | Zero-traffic Gemini 3.5 candidates produced `NATIVE`, zero-authority degraded receipts and left missions at version 0, but the valid prepared scan returned non-JSON text and never reached deterministic acceptance. Production remains the disclosed fixture path. | 2026-08-31 12:00 EDT decision |
| 4 | Logged-out hosted app | **PASS** | Public `.run.app` health is `200`, PostgreSQL-backed, light by default, and horizontally stable. | — |
| 5 | Architecture image | **PASS** | Submission PNG is a 3600×2400 render of the current tracked SVG, including exact service names and the corrected verified-receipt edge. | — |
| 6 | Gallery media | **PASS** | Two versioned 3:2 PNG derivatives preserve the complete light-theme evidence and quarantine views; originals remain available. | — |
| 7 | Required Gemini/ADK/GCP stack | **PASS** | Retained managed proof covers Gemini 3.5 Flash, root plus four scoped ADK workers, Cloud Run, Cloud SQL, Pub/Sub/Eventarc, and zero model authority. | — |
| 8 | Reproducible testing and license | **PASS** | README contains local, browser, PostgreSQL, and managed-probe instructions; GitHub detects the MIT license. | — |
| 9 | New-project disclosure | **PASS** | The Devpost draft states the August 3–31 build window, standard tooling, and no incorporated pre-existing project code. | — |
| 10 | Rollback and judging-window health | **PASS** | Serving pair `00023-hay` / `00018-jam`; immediate pair `00021-tac` / `00016-nol` is Ready on immutable images. | Monitor through judging |
| 11 | Submission documentation consistency | **PASS** | README, checkpoint, Devpost draft, v7 runbook, architecture, bonus-model status, and media filenames share the same v7 and fixture-truth boundary. | — |
| 12 | Public blog and social bonus | **BLOCKED** | Final local drafts and media exist, but dev.to image/video URLs and public blog/X URLs remain pending. | 2026-08-31 16:00 EDT |

## Submission truth boundary

- Do not describe the public visual-extraction path as live Vertex Gemini unless a later guarded
  candidate accepts the prepared scan and the persisted receipt is `NATIVE`, `COMPLETED`,
  `ACCEPTED`, digest-bound, and `release_authority=false`.
- It is accurate to say the public app demonstrates the deterministic multimodal workflow with a
  disclosed fixture and that a managed Gemini failure was proven to fail closed without mutation.
- The retained ADK Gemini 3.5 managed proof remains valid and is separate from the blocked visual
  extraction packet.

## Final judge-view audit gate

Rerun only after the exact `main` commit is judge-accessible, Alex v7 has a public YouTube/Vimeo
URL, and the blog/social URLs have replaced their placeholders. Verify every artifact logged out,
play the video at 1080p, compare every claim with the deployed app, and freeze the repository,
video, and linked artifacts after the deadline.
