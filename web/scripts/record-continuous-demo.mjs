import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { chromium } from "@playwright/test";

const execFileAsync = promisify(execFile);
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const requiredApproval = "I_APPROVE_ONE_CONTINUOUS_SYNTHETIC_RECORDING";
if (process.env.CARGO_RELEASE_CONTINUOUS_RECORDING_APPROVED !== requiredApproval) {
  console.error("Continuous recording not started.");
  console.error("This take publishes one marked synthetic Eventarc mission, records one scripted operator attestation, and sends at most one marked Slack notice.");
  console.error(`Set CARGO_RELEASE_CONTINUOUS_RECORDING_APPROVED=${requiredApproval} to authorize it.`);
  process.exit(3);
}

const appUrl = (process.env.APP_URL ??
  "https://cargo-release-web-1015646664425.us-central1.run.app").replace(/\/$/, "");
const modelMissionId = process.env.MODEL_MISSION_ID ?? "mission-f92f38ea26c6";
const outputDirectory = path.resolve(
  process.env.RECORDING_OUTPUT ?? "../.playwright-mcp/continuous-demo",
);
const recordingStem = process.env.RECORDING_STEM ?? "cargo-release-continuous-proof";
const repositoryRoot = path.resolve("..");
const eventTrigger = path.join(repositoryRoot, "scripts", "publish_recording_event.sh");
const rawVideoPath = path.join(outputDirectory, `${recordingStem}.webm`);
const finalVideoPath = path.join(outputDirectory, `${recordingStem}.mp4`);
const reportPath = path.join(outputDirectory, `${recordingStem}.json`);
const viewport = { width: 1920, height: 1080 };

await mkdir(outputDirectory, { recursive: true });

const startedAt = Date.now();
const beats = [];
const browserErrors = [];
let missionId = null;
let messageId = null;
let finalSnapshot = null;

function mark(name, detail = undefined) {
  const at = Number(((Date.now() - startedAt) / 1000).toFixed(2));
  beats.push({ name, at, ...(detail ? { detail } : {}) });
  console.log(`[${at.toFixed(1).padStart(6)}s] ${name}`);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchMission(candidateMissionId, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let lastStatus = 0;
  while (Date.now() < deadline) {
    const response = await fetch(
      `${appUrl}/api/cargo/v1/missions/${encodeURIComponent(candidateMissionId)}`,
    );
    lastStatus = response.status;
    if (response.ok) return response.json();
    if (response.status !== 404) {
      throw new Error(`Mission relay returned ${response.status}: ${await response.text()}`);
    }
    await sleep(1_000);
  }
  throw new Error(`Eventarc mission did not appear within ${timeoutMs}ms; last status ${lastStatus}`);
}

async function showCaption(page, text, position = "bottom") {
  await page.evaluate(({ caption, placement }) => {
    document.querySelector("#cargo-proof-caption")?.remove();
    const element = document.createElement("div");
    element.id = "cargo-proof-caption";
    element.textContent = caption;
    element.style.cssText = [
      "position:fixed",
      placement === "top" ? "top:168px" : "bottom:34px",
      "left:50%",
      "transform:translateX(-50%)",
      "z-index:2147483647",
      "max-width:1180px",
      "padding:14px 22px",
      "border:1px solid rgba(25,100,220,.42)",
      "border-radius:10px",
      "background:rgba(255,255,255,.96)",
      "box-shadow:0 14px 38px rgba(38,74,112,.18)",
      "color:#071d36",
      "font:600 23px/1.35 Arial,sans-serif",
      "letter-spacing:.01em",
      "text-align:center",
      "pointer-events:none",
    ].join(";");
    document.body.append(element);
  }, { caption: text, placement: position });
}

async function hideCaption(page) {
  await page.evaluate(() => document.querySelector("#cargo-proof-caption")?.remove());
}

async function holdBeat(page, name, caption, milliseconds, position = "bottom") {
  await showCaption(page, caption, position);
  mark(name);
  await sleep(milliseconds);
  await hideCaption(page);
  await sleep(900);
}

async function durationSeconds(filePath) {
  const { stdout } = await execFileAsync("ffprobe", [
    "-v", "error",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1",
    filePath,
  ]);
  return Number(stdout.trim());
}

const health = await fetch(`${appUrl}/api/cargo/health`);
assert.equal(health.status, 200, "Canonical relay health must pass before recording");
const healthPayload = await health.json();
assert.equal(healthPayload.database, "postgresql", "Managed recording must use PostgreSQL");

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport,
  deviceScaleFactor: 1,
  colorScheme: "light",
  recordVideo: { dir: outputDirectory, size: viewport },
});
const page = await context.newPage();
const video = page.video();
page.on("pageerror", (error) => browserErrors.push(error.message));

let recordingError = null;
try {
  await page.setContent(`<!doctype html>
    <html><head><meta charset="utf-8"><style>
      *{box-sizing:border-box} body{margin:0;background:#edf6ff;color:#071d36;font-family:Arial,sans-serif}
      main{height:1080px;display:grid;place-items:center;padding:100px;background:
        radial-gradient(circle at 20% 20%,rgba(30,103,235,.15),transparent 34%),linear-gradient(135deg,#f8fbff,#eaf4ff)}
      section{width:1340px;border:1px solid #9bbfe9;border-radius:24px;background:rgba(255,255,255,.94);box-shadow:0 30px 80px rgba(33,79,125,.16);padding:66px}
      small{color:#0c61d8;font:700 18px monospace;letter-spacing:.16em} h1{font-size:76px;line-height:1.02;margin:18px 0 24px}
      p{font-size:27px;line-height:1.5;color:#4b647e;max-width:1150px}.url{color:#087b62;font:22px monospace}
      pre{margin:30px 0 0;padding:24px;border-radius:12px;background:#f2f7fd;border:1px solid #bdd2e9;color:#12314f;font:21px/1.6 monospace;white-space:pre-wrap}
      .live{display:inline-flex;gap:10px;align-items:center;color:#b86200;font:700 18px monospace}.dot{width:11px;height:11px;border-radius:50%;background:#f37a00}
    </style></head><body><main><section>
      <div class="live"><span class="dot"></span>LIVE CONTINUOUS PLAYWRIGHT CAPTURE · NO CUTS OR SPLICES</div>
      <h1>One casualty event.<br>One human attestation.</h1>
      <p>Google Cloud Pub/Sub → Eventarc → Cloud Run → Cloud SQL. The model coordinates; humans and independently verified receipts retain release authority.</p>
      <div class="url">${escapeHtml(appUrl)}</div>
      <pre id="trigger-output">Preparing one marked synthetic event…</pre>
    </section></main></body></html>`);
  mark("B0 continuous proof card", { app_url: appUrl });
  await sleep(5_000);

  const { stdout: triggerOutput } = await execFileAsync(eventTrigger, [], {
    cwd: repositoryRoot,
    env: {
      ...process.env,
      CARGO_RELEASE_RECORDING_EVENT_APPROVED: "I_APPROVE_ONE_MARKED_SYNTHETIC_RECORDING_EVENT",
    },
    timeout: 60_000,
  });
  messageId = triggerOutput.match(/Message ID: ([0-9]+)/)?.[1] ?? null;
  missionId = triggerOutput.match(/Mission ID: (mission-[a-f0-9]+)/)?.[1] ?? null;
  assert.ok(messageId, "Recording trigger returned no Pub/Sub message ID");
  assert.ok(missionId, "Recording trigger returned no deterministic mission ID");
  await page.evaluate((output) => {
    const node = document.querySelector("#trigger-output");
    if (node) node.textContent = output;
  }, triggerOutput.trim());
  mark("B1 Pub/Sub event published", { message_id: messageId, mission_id: missionId });
  await sleep(7_000);

  const heldSnapshot = await fetchMission(missionId);
  assert.equal(heldSnapshot.mission.truth_mode, "NATIVE");
  assert.equal(heldSnapshot.mission.release_state, "READY_FOR_SIGNATURE");
  assert.equal(heldSnapshot.approvals.length, 0);
  assert.equal(heldSnapshot.notifications.length, 0);

  const missionUrl = `${appUrl}/?mission=${encodeURIComponent(missionId)}`;
  await page.goto(missionUrl, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.getByRole("heading", { name: "Cargo held at North Harbor" }).waitFor({ timeout: 45_000 });
  await page.getByText("Native Eventarc mission", { exact: true }).waitFor();
  await page.getByText("NATIVE", { exact: true }).first().waitFor();
  await page.getByTestId("primary-action").getByText("Approve bond & resume", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B2 native Eventarc mission at human gate",
    "NATIVE Eventarc mission. The deterministic controller reconciled evidence, then stopped at the only human gate.",
    7_000,
  );

  await page.getByRole("button", { name: /^Evidence \d+$/ }).click();
  await page.getByRole("button", { name: /Broker email/ }).click();
  await page.getByText("QUARANTINED", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B3 quarantined model-addressed evidence",
    "This source tells the model to accept a guarantee. It stays inspectable, but contributes no mission fact and cannot mutate release state.",
    8_000,
    "top",
  );

  const visualEvidence = page.locator(".evidence-index button").filter({ hasText: "IMAGE" });
  assert.equal(await visualEvidence.count(), 1, "Expected exactly one prepared image evidence source");
  await visualEvidence.click();
  await page.getByText("Prepared synthetic scan · authenticated mission intake only", { exact: true }).waitFor();
  await page.getByText("Deterministic validation", { exact: true }).waitFor();
  await page.getByText("ACCEPTED", { exact: true }).waitFor();
  await page.getByText("Exact workflow consequence", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B4 prepared scan validated and correction selected",
    "The prepared scan survives. Its extracted missing field is digest-bound and deterministically validated; this public path truth-labels extraction as FIXTURE.",
    10_000,
    "top",
  );

  await page.getByRole("button", { name: /^Documents \d+$/ }).click();
  await page.getByRole("heading", { name: "Cargo owner General Average bond" }).waitFor();
  await holdBeat(
    page,
    "B5 content-addressed owner bond",
    "The system drafted a versioned owner bond from reviewed facts. Artifact creation is not authority.",
    6_500,
    "top",
  );

  await page.getByRole("button", { name: "Mission", exact: true }).click();
  const primaryAction = page.getByTestId("primary-action");
  await primaryAction.getByText("Approve bond & resume", { exact: true }).waitFor();
  await showCaption(
    page,
    "ONE SCRIPTED OPERATOR ATTESTATION — the only browser transition. Independent services must still issue every release key.",
  );
  mark("B6 one operator attestation requested");
  await sleep(4_000);
  await primaryAction.click();
  await showCaption(
    page,
    "LIVE RECEIPT SAGA — Cloud SQL lease, insurer guarantee, adjuster rejection, bounded correction, acceptance, carrier order, read-back.",
  );
  await page.getByRole("heading", { name: "Cargo released" }).waitFor({ timeout: 120_000 });
  await page.getByText("Carrier read-back verified").waitFor();
  await page.getByText("Marked synthetic notice delivered", { exact: false }).waitFor({ timeout: 45_000 });
  mark("B7 live saga completed and Slack delivery returned");
  await sleep(5_000);
  await hideCaption(page);
  await sleep(900);

  await page.getByRole("button", { name: /^Documents \d+$/ }).click();
  await page.getByRole("button", { name: /SECURITY PACK · V2/ }).click();
  await page.getByRole("heading", { name: "Full security submission pack" }).waitFor();
  await holdBeat(
    page,
    "B8 rejected pack corrected as revision two",
    "The adjuster rejected revision one. The failure was recorded; revision two corrected the missing declaration reference and was resubmitted.",
    8_000,
    "top",
  );

  await page.getByRole("button", { name: /^Receipts \d+$/ }).click();
  await page.getByRole("heading", { name: "Receipts unlock cargo" }).waitFor();
  await holdBeat(
    page,
    "B9 five issuer-bound receipts",
    "Five verified, issuer-bound receipts hold the keys: insurer, adjuster rejection and acceptance, carrier order, and independent read-back.",
    8_000,
    "top",
  );
  await page.getByRole("button", { name: /Carrier read-back/ }).click();
  await page.getByRole("dialog", { name: "Carrier read-back" }).waitFor();
  await holdBeat(
    page,
    "B10 inspected carrier read-back receipt",
    "The terminal state depends on this verified carrier read-back—not on model prose.",
    5_500,
    "top",
  );
  await page.getByRole("button", { name: "Close receipt" }).click();

  await page.getByRole("button", { name: "Mission", exact: true }).click();
  await page.getByRole("heading", { name: "Cargo released" }).waitFor();
  await page.getByTestId("adjustment-state").getByText("OPEN", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B11 physical release and open adjustment",
    "Physical cargo is RELEASED. The General Average adjustment deliberately remains OPEN because those are different lifecycles.",
    7_000,
  );

  await page.getByRole("button", { name: /^Activity \d+$/ }).click();
  await page.getByText("Synthetic outbound proof · non-authoritative", { exact: true }).waitFor();
  await page.getByText("operator-owned Slack #general", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B12 marked independently observable consequence",
    "Only after carrier read-back, one marked synthetic Slack notice is delivered. It cannot release real cargo and duplicate delivery cannot create another.",
    8_000,
    "top",
  );

  await page.goto(`${appUrl}/?mission=${encodeURIComponent(modelMissionId)}`, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  await page.getByRole("heading", { name: "Cargo released" }).waitFor({ timeout: 45_000 });
  await page.getByRole("button", { name: /^AI checks \d+$/ }).click();
  for (const model of [
    "google/gemma-4-26b-a4b-it-maas",
    "gemini-embedding-2",
    "veo-3.1-fast-generate-001",
  ]) {
    await page.getByText(model, { exact: true }).waitFor();
  }
  await page.getByText("veo-3.1-fast-generate-001", { exact: true }).scrollIntoViewIfNeeded();
  await holdBeat(
    page,
    "B13 three pre-validated zero-authority Google models",
    "Pre-validated managed receipts: Gemma critiques, Embedding 2 ranks reviewed cases, and Veo creates post-release training media. All three declare release_authority=false.",
    10_000,
    "top",
  );

  await page.goto(`${appUrl}/?mission=${encodeURIComponent(missionId)}`, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  await page.getByRole("heading", { name: "Cargo released" }).waitFor({ timeout: 45_000 });
  await page.getByRole("button", { name: "Authority map", exact: true }).click();
  await page.getByRole("heading", { name: "Authority moves. Agents do not own it." }).waitFor();
  for (const worker of ["Evidence worker", "Security worker", "Authority worker", "Recovery worker"]) {
    await page.getByText(worker, { exact: true }).waitFor();
  }
  await page.getByText("release_authority=false for every model and worker", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B14 root plus four scoped ADK workers",
    "Gemini 3.5 delegates through ADK to four read-only workers. The live Eventarc path and governed operator plane stay truthfully separate; every worker returns release_authority=false.",
    10_000,
    "top",
  );
  await page.getByTestId("friction-metric").scrollIntoViewIfNeeded();
  await page.getByTestId("human-attestations").getByText("1", { exact: true }).waitFor();
  await page.getByTestId("friction-metric").getByText("8 / 8", { exact: false }).waitFor();
  await holdBeat(
    page,
    "B15 duplicate-safe friction metric",
    "Measured capability count: one human attestation produced eight unique downstream actions. Duplicate receipts, events, and notices cannot inflate it.",
    8_000,
    "top",
  );

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.getByRole("button", { name: "Architecture", exact: true }).click();
  const architecture = page.getByRole("dialog", { name: "Architecture" });
  await architecture.getByRole("heading", { name: "Transition ownership" }).waitFor();
  await architecture.getByText("Fail-closed IAP authorization", { exact: false }).waitFor();
  await holdBeat(
    page,
    "B16 managed architecture boundary",
    "Agent Gateway constrains the managed route. Cloud SQL is the sole state writer. Model output and managed memory never write release state.",
    8_000,
    "top",
  );
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: "Mission", exact: true }).click();
  await holdBeat(
    page,
    "B17 closing proof",
    "Cargo Release: agents do the coordination; humans and independently verified receipts retain authority.",
    7_000,
  );

  finalSnapshot = await fetchMission(missionId);
  assert.equal(finalSnapshot.mission.truth_mode, "NATIVE");
  assert.equal(finalSnapshot.mission.release_state, "RELEASED");
  assert.equal(finalSnapshot.mission.adjustment_state, "OPEN");
  assert.equal(finalSnapshot.approvals.length, 1);
  assert.equal(finalSnapshot.receipts.length, 5);
  assert.equal(finalSnapshot.notifications.length, 1);
  assert.equal(finalSnapshot.runs.at(-1)?.status, "COMPLETED");
  const multimodalReceipt = finalSnapshot.model_receipts?.find(
    (item) => item.kind === "GEMINI_ADJUSTER_REJECTION_EXTRACTION",
  );
  assert.ok(multimodalReceipt, "Prepared scan must produce a multimodal extraction receipt");
  assert.equal(multimodalReceipt.validation_outcome, "ACCEPTED");
  mark("END — final state assertions passed");
} catch (error) {
  recordingError = error;
  mark("FAILED", { error: error instanceof Error ? error.message : String(error) });
} finally {
  await page.close();
  await context.close();
  await browser.close();
}

if (!video) throw new Error("Playwright did not create a video artifact");
await rename(await video.path(), rawVideoPath);

await execFileAsync("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-i", rawVideoPath,
  "-map", "0:v:0", "-an",
  "-c:v", "libx264", "-preset", "medium", "-crf", "18",
  "-pix_fmt", "yuv420p", "-color_range", "tv",
  "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
  "-movflags", "+faststart",
  finalVideoPath,
]);

const rawDuration = await durationSeconds(rawVideoPath);
const finalDuration = await durationSeconds(finalVideoPath);
const durationDelta = Math.abs(rawDuration - finalDuration);
const sha256 = createHash("sha256").update(await readFile(finalVideoPath)).digest("hex");
const verificationErrors = [];
if (recordingError) {
  verificationErrors.push(recordingError instanceof Error
    ? recordingError.stack ?? recordingError.message
    : String(recordingError));
}
if (!Number.isFinite(finalDuration)) verificationErrors.push("Final duration is not finite");
if (finalDuration >= 240) verificationErrors.push(`Take is ${finalDuration}s; cap is under 240s`);
if (durationDelta > 0.25) verificationErrors.push(`Transcode duration delta is ${durationDelta}s`);
if (browserErrors.length) verificationErrors.push(`Browser errors: ${browserErrors.join(" | ")}`);
const report = {
  status: verificationErrors.length ? "FAILED" : "PASSED",
  app_url: appUrl,
  started_at: new Date(startedAt).toISOString(),
  finished_at: new Date().toISOString(),
  viewport,
  continuous: true,
  cuts_or_splices: 0,
  event: { message_id: messageId, mission_id: missionId },
  final_state: finalSnapshot ? {
    truth_mode: finalSnapshot.mission.truth_mode,
    release_state: finalSnapshot.mission.release_state,
    adjustment_state: finalSnapshot.mission.adjustment_state,
    approvals: finalSnapshot.approvals.length,
    receipts: finalSnapshot.receipts.length,
    notifications: finalSnapshot.notifications.length,
    latest_run: finalSnapshot.runs.at(-1)?.status,
    multimodal_extraction: finalSnapshot.model_receipts?.find(
      (item) => item.kind === "GEMINI_ADJUSTER_REJECTION_EXTRACTION",
    ) ? {
      truth_mode: finalSnapshot.model_receipts.find(
        (item) => item.kind === "GEMINI_ADJUSTER_REJECTION_EXTRACTION",
      ).truth_mode,
      validation_outcome: finalSnapshot.model_receipts.find(
        (item) => item.kind === "GEMINI_ADJUSTER_REJECTION_EXTRACTION",
      ).validation_outcome,
    } : null,
  } : null,
  beats,
  browser_errors: browserErrors,
  artifacts: {
    raw_video: rawVideoPath,
    final_video: finalVideoPath,
    raw_duration_seconds: rawDuration,
    final_duration_seconds: finalDuration,
    duration_delta_seconds: durationDelta,
    sha256,
  },
  verification_errors: verificationErrors,
};
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

if (verificationErrors.length) {
  throw new Error(`Continuous proof failed verification: ${verificationErrors.join(" | ")}`);
}

console.log(`continuous proof passed: ${finalDuration.toFixed(2)}s, sha256:${sha256}`);
console.log(finalVideoPath);
