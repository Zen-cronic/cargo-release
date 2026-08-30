import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { access, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { chromium } from "@playwright/test";

const execFileAsync = promisify(execFile);
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const requiredApproval = "I_APPROVE_ONE_CONTINUOUS_SYNTHETIC_RECORDING";
if (process.env.CARGO_RELEASE_CONTINUOUS_RECORDING_APPROVED !== requiredApproval) {
  console.error("V3 recording not started.");
  console.error("This publishes one marked synthetic Eventarc mission, records one operator attestation, and sends at most one marked Slack notice.");
  console.error(`Set CARGO_RELEASE_CONTINUOUS_RECORDING_APPROVED=${requiredApproval} to authorize it.`);
  process.exit(3);
}

const appUrl = (process.env.APP_URL ??
  "https://cargo-release-web-1015646664425.us-central1.run.app").replace(/\/$/, "");
const modelMissionId = process.env.MODEL_MISSION_ID ?? "mission-f92f38ea26c6";
const slackChannelUrl = process.env.SLACK_CHANNEL_URL ??
  "https://app.slack.com/client/E0BSJNGCZHU/C0BSJNEE1HC";
const slackChannelId = new URL(slackChannelUrl).pathname.split("/").filter(Boolean).at(-1);
const chromeUserDataDir = process.env.SLACK_CHROME_USER_DATA_DIR;
const chromeProfile = process.env.SLACK_CHROME_PROFILE_DIRECTORY;
const chromeExecutable = process.env.SLACK_CHROME_EXECUTABLE ?? "/usr/bin/google-chrome";
const slackReadyPath = path.resolve(
  process.env.SLACK_RECORDING_READY ?? "../.playwright-mcp/slack-recording-profile-ready.json",
);
if (!chromeUserDataDir || !chromeProfile) {
  throw new Error("V3 requires SLACK_CHROME_USER_DATA_DIR and SLACK_CHROME_PROFILE_DIRECTORY so the real channel—not a reconstruction—is recorded");
}

const outputDirectory = path.resolve(
  process.env.RECORDING_OUTPUT ?? "../.playwright-mcp/continuous-demo-dan-v3",
);
const recordingStem = process.env.RECORDING_STEM ?? "cargo-release-light-dan-v3-source";
const repositoryRoot = path.resolve("..");
const eventTrigger = path.join(repositoryRoot, "scripts", "publish_recording_event.sh");
const rawVideoPath = path.join(outputDirectory, `${recordingStem}.webm`);
const finalVideoPath = path.join(outputDirectory, `${recordingStem}.mp4`);
const reportPath = path.join(outputDirectory, `${recordingStem}.json`);
const viewport = { width: 1920, height: 1080 };

await mkdir(outputDirectory, { recursive: true });

const slackReady = JSON.parse(await readFile(slackReadyPath, "utf8"));
assert.equal(slackReady.status, "READY", "Dedicated Slack recording profile is not ready");
assert.equal(slackReady.channelUrl, slackChannelUrl, "Slack readiness marker targets another channel");
try {
  await access(path.join(chromeUserDataDir, "SingletonLock"));
  throw new Error("Dedicated Slack recording profile is still open; close its Chrome window before recording");
} catch (error) {
  if (error instanceof Error && !error.message.includes("ENOENT")) throw error;
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

async function waitForHumanGate(candidateMissionId, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  let latest = null;
  while (Date.now() < deadline) {
    latest = await fetchMission(candidateMissionId);
    if (latest.mission.release_state === "READY_FOR_SIGNATURE") return latest;
    const run = latest.runs.at(-1);
    if (run?.status === "FAILED") {
      throw new Error(`Eventarc mission failed before the human gate: ${run.stop_reason}`);
    }
    await sleep(750);
  }
  throw new Error(
    `Eventarc mission did not reach READY_FOR_SIGNATURE within ${timeoutMs}ms; latest state ${latest?.mission.release_state ?? "UNKNOWN"}`,
  );
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
assert.equal((await health.json()).database, "postgresql", "Managed recording must use PostgreSQL");

// Publish before the red button so the very first frame can be the real product at its human gate.
// The report retains the native message ID; the recorded UI retains NATIVE Eventarc provenance.
const { stdout: triggerOutput } = await execFileAsync(eventTrigger, [], {
  cwd: repositoryRoot,
  env: {
    ...process.env,
    CARGO_RELEASE_RECORDING_EVENT_APPROVED: "I_APPROVE_ONE_MARKED_SYNTHETIC_RECORDING_EVENT",
  },
  timeout: 60_000,
});
const messageId = triggerOutput.match(/Message ID: ([0-9]+)/)?.[1] ?? null;
const missionId = triggerOutput.match(/Mission ID: (mission-[a-f0-9]+)/)?.[1] ?? null;
assert.ok(messageId, "Recording trigger returned no Pub/Sub message ID");
assert.ok(missionId, "Recording trigger returned no deterministic mission ID");
const heldSnapshot = await waitForHumanGate(missionId);
assert.equal(heldSnapshot.mission.truth_mode, "NATIVE");
assert.equal(heldSnapshot.mission.release_state, "READY_FOR_SIGNATURE");
assert.equal(heldSnapshot.approvals.length, 0);
assert.equal(heldSnapshot.notifications.length, 0);

const startedAt = Date.now();
const beats = [];
const browserErrors = [];
let finalSnapshot = null;
let recordingError = null;
let slackProofUrl = null;

function mark(name, detail = undefined) {
  const at = Number(((Date.now() - startedAt) / 1000).toFixed(2));
  beats.push({ name, at, ...(detail ? { detail } : {}) });
  console.log(`[${at.toFixed(1).padStart(6)}s] ${name}`);
}

async function showCaption(page, text, tone = "blue") {
  await page.evaluate(({ caption, captionTone }) => {
    document.querySelector("#cargo-proof-caption")?.remove();
    const palette = captionTone === "live"
      ? { border: "rgba(4,132,102,.5)", dot: "#078568", text: "#073d34" }
      : captionTone === "warning"
        ? { border: "rgba(221,126,0,.48)", dot: "#e77a00", text: "#4b2b00" }
        : { border: "rgba(25,100,220,.42)", dot: "#1264d7", text: "#071d36" };
    const element = document.createElement("div");
    element.id = "cargo-proof-caption";
    element.innerHTML = `<i></i><span></span>`;
    element.querySelector("span").textContent = caption;
    element.style.cssText = [
      "position:fixed", "bottom:42px", "left:50%", "transform:translateX(-50%)",
      "z-index:2147483647", "max-width:1240px", "display:flex", "align-items:center",
      "gap:14px", "padding:13px 20px", `border:1px solid ${palette.border}`,
      "border-radius:999px", "background:rgba(255,255,255,.97)",
      "box-shadow:0 14px 38px rgba(38,74,112,.18)", `color:${palette.text}`,
      "font:650 21px/1.3 Arial,sans-serif", "letter-spacing:.005em", "text-align:left",
      "pointer-events:none",
    ].join(";");
    const dot = element.querySelector("i");
    dot.style.cssText = [
      "width:11px", "height:11px", "flex:0 0 11px", "border-radius:50%",
      `background:${palette.dot}`,
      captionTone === "live" ? "animation:cargoPulse 1.1s ease-in-out infinite" : "",
    ].join(";");
    if (!document.querySelector("#cargo-proof-style")) {
      const style = document.createElement("style");
      style.id = "cargo-proof-style";
      style.textContent = "@keyframes cargoPulse{0%,100%{opacity:.35;scale:.72}50%{opacity:1;scale:1.25}}";
      document.head.append(style);
    }
    document.body.append(element);
  }, { caption: text, captionTone: tone });
}

async function hideCaption(page) {
  await page.evaluate(() => document.querySelector("#cargo-proof-caption")?.remove());
}

async function holdBeat(page, name, caption, milliseconds, tone = "blue") {
  await showCaption(page, caption, tone);
  mark(name);
  await sleep(milliseconds);
  await hideCaption(page);
  await sleep(650);
}

const context = await chromium.launchPersistentContext(chromeUserDataDir, {
  executablePath: chromeExecutable,
  headless: true,
  viewport,
  deviceScaleFactor: 1,
  colorScheme: "light",
  recordVideo: { dir: outputDirectory, size: viewport },
  args: [
    `--profile-directory=${chromeProfile}`,
    "--disable-session-crashed-bubble",
    "--disable-infobars",
  ],
});
const page = context.pages()[0] ?? await context.newPage();
for (const extra of context.pages().slice(1)) await extra.close();
const video = page.video();
page.on("pageerror", (error) => browserErrors.push(error.message));

try {
  const missionUrl = `${appUrl}/?mission=${encodeURIComponent(missionId)}`;
  await page.goto(missionUrl, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.getByRole("heading", { name: "Cargo held at North Harbor" }).waitFor({ timeout: 45_000 });
  await page.locator(".app-shell.theme-light").waitFor();
  await page.getByText("Native Eventarc mission", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B0 product kill shot — cargo held",
    "A hostile broker asks the AI to fake acceptance. The real product keeps the container HELD.",
    6_500,
    "warning",
  );
  await holdBeat(
    page,
    "B1 native Eventarc provenance",
    `LIVE CLOUD RUN · Native Eventarc mission ${missionId} · message ${messageId}`,
    4_500,
    "live",
  );

  await page.getByRole("button", { name: /^Evidence \d+$/ }).click();
  await page.getByRole("button", { name: /Broker email/ }).click();
  await page.getByText("QUARANTINED", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B2 hostile email quarantined",
    "Wrong path first: the email remains inspectable but contributes no fact, memory, or state transition.",
    6_500,
    "warning",
  );

  const visualEvidence = page.locator(".evidence-index button").filter({ hasText: "IMAGE" });
  assert.equal(await visualEvidence.count(), 1);
  await visualEvidence.click();
  await page.getByText("Prepared synthetic scan · authenticated mission intake only", { exact: true }).waitFor();
  await page.getByText("ACCEPTED", { exact: true }).waitFor();
  await page.getByText("Exact workflow consequence", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B3 valid scan selects correction",
    "Valid visual evidence survives: digest-bound fields pass deterministic validation and select declaration_reference for revision two.",
    8_500,
    "live",
  );

  await page.getByRole("button", { name: "Mission", exact: true }).click();
  const primaryAction = page.getByTestId("primary-action");
  await primaryAction.getByText("Approve bond & resume", { exact: true }).waitFor();
  await showCaption(page, "ONE HUMAN ATTESTATION → EIGHT BOUNDED DOWNSTREAM ACTIONS", "blue");
  mark("B4 one operator attestation requested");
  await sleep(4_000);
  await primaryAction.click();
  await page.getByRole("button", { name: "Authority map", exact: true }).click();
  await page.getByRole("heading", { name: "Authority moves. Agents do not own it." }).waitFor();
  await showCaption(page, "LIVE · UNCUT · Partner services are issuing independent signed receipts", "live");
  mark("B5 live partner wait begins");
  await sleep(7_000);
  await showCaption(page, "No loading edit: Cloud SQL holds the lease while insurer, adjuster, and carrier calls complete", "live");
  mark("B6 live partner wait continues");
  await page.getByText("Container released", { exact: true }).waitFor({ timeout: 120_000 });
  await page.getByTestId("friction-metric").getByText("8 / 8", { exact: false }).waitFor();
  mark("B7 authority map lights from released state");
  await sleep(4_500);
  await hideCaption(page);
  await sleep(650);

  await page.getByRole("button", { name: /^Documents \d+$/ }).click();
  await page.getByRole("button", { name: /SECURITY PACK · V2/ }).click();
  await page.getByRole("heading", { name: "Full security submission pack" }).waitFor();
  await holdBeat(
    page,
    "B8 durable rejection becomes revision two",
    "Revision one was rejected; the retained reason corrected exactly one field in revision two—without another human click.",
    7_000,
  );

  await page.getByRole("button", { name: /^Receipts \d+$/ }).click();
  await page.getByRole("heading", { name: "Receipts unlock cargo" }).waitFor();
  await holdBeat(
    page,
    "B9 five issuer-bound receipts",
    "Five verified issuer-bound receipts hold the keys. Model prose never does.",
    6_500,
    "live",
  );

  await page.getByRole("button", { name: "Mission", exact: true }).click();
  await page.getByRole("heading", { name: "Cargo released" }).waitFor();
  await page.getByTestId("adjustment-state").getByText("OPEN", { exact: true }).waitFor();
  await holdBeat(
    page,
    "B10 released cargo and open adjustment",
    "Physical cargo is RELEASED. The long-tail General Average adjustment correctly remains OPEN.",
    6_500,
    "live",
  );

  finalSnapshot = await fetchMission(missionId);
  assert.equal(finalSnapshot.notifications.length, 1);
  const providerRef = finalSnapshot.notifications[0].provider_ref;
  await page.goto(slackChannelUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
  const slackMissionText = page.getByText(missionId, { exact: false }).first();
  await slackMissionText.waitFor({ state: "attached", timeout: 60_000 });
  const slackMessageTextId = await slackMissionText.getAttribute("id");
  const slackMessageTimestamp = slackMessageTextId?.match(/-(\d+\.\d+)-message_text$/)?.[1];
  assert.ok(slackChannelId, "Slack channel URL contains no channel ID");
  assert.ok(slackMessageTimestamp, `Could not derive a Slack message timestamp for ${missionId}`);
  slackProofUrl = `${slackChannelUrl}/thread/${slackChannelId}-${slackMessageTimestamp}`;
  await page.goto(slackProofUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.getByText(missionId, { exact: false }).filter({ visible: true }).first().waitFor({
    timeout: 60_000,
  });
  await holdBeat(
    page,
    "B11 real Slack channel closes the loop",
    `REAL SLACK LOOP · ${missionId} · delivery ${providerRef} · synthetic demo, no real cargo action`,
    8_000,
    "live",
  );

  await page.goto(`${appUrl}/?mission=${encodeURIComponent(modelMissionId)}`, {
    waitUntil: "domcontentloaded", timeout: 45_000,
  });
  await page.getByRole("heading", { name: "Cargo released" }).waitFor({ timeout: 45_000 });
  await page.getByRole("button", { name: /^AI checks \d+$/ }).click();
  await page.getByText("veo-3.1-fast-generate-001", { exact: true }).scrollIntoViewIfNeeded();
  await holdBeat(
    page,
    "B12 bonus models remain non-authoritative",
    "Gemma reviews, Embedding Two retrieves, and Veo creates optional post-release training media. All declare release_authority=false.",
    8_000,
  );

  await page.goto(`${appUrl}/?mission=${encodeURIComponent(missionId)}`, {
    waitUntil: "domcontentloaded", timeout: 45_000,
  });
  await page.getByRole("heading", { name: "Cargo released" }).waitFor({ timeout: 45_000 });
  await page.getByRole("button", { name: "Authority map", exact: true }).click();
  await page.getByTestId("friction-metric").scrollIntoViewIfNeeded();
  await holdBeat(
    page,
    "B13 final authority map and metric",
    "One attestation produced eight unique actions. Gemini and four ADK specialists coordinated; Cloud SQL and verified receipts authorized.",
    9_000,
    "live",
  );

  await page.getByRole("button", { name: "Mission", exact: true }).click();
  await holdBeat(
    page,
    "B14 closing proof",
    "Cargo Release. Agents coordinate. Humans attest. Independent receipts hold the key.",
    6_000,
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
  assert.ok(multimodalReceipt);
  assert.equal(multimodalReceipt.validation_outcome, "ACCEPTED");
  mark("END — final state and Slack assertions passed");
} catch (error) {
  recordingError = error;
  mark("FAILED", { error: error instanceof Error ? error.message : String(error) });
} finally {
  await page.close();
  await context.close();
}

if (!video) throw new Error("Playwright did not create a video artifact");
await rename(await video.path(), rawVideoPath);
await execFileAsync("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y", "-i", rawVideoPath,
  "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
  "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709",
  "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart",
  finalVideoPath,
]);

const rawDuration = await durationSeconds(rawVideoPath);
const finalDuration = await durationSeconds(finalVideoPath);
const durationDelta = Math.abs(rawDuration - finalDuration);
const sha256 = createHash("sha256").update(await readFile(finalVideoPath)).digest("hex");
const verificationErrors = [];
if (recordingError) verificationErrors.push(
  recordingError instanceof Error ? recordingError.stack ?? recordingError.message : String(recordingError),
);
if (!Number.isFinite(finalDuration)) verificationErrors.push("Final duration is not finite");
if (finalDuration >= 240) verificationErrors.push(`Take is ${finalDuration}s; cap is under 240s`);
if (durationDelta > 0.25) verificationErrors.push(`Transcode duration delta is ${durationDelta}s`);
if (browserErrors.length) verificationErrors.push(`Browser errors: ${browserErrors.join(" | ")}`);
const multimodalReceipt = finalSnapshot?.model_receipts?.find(
  (item) => item.kind === "GEMINI_ADJUSTER_REJECTION_EXTRACTION",
);
const report = {
  status: verificationErrors.length ? "FAILED" : "PASSED",
  app_url: appUrl,
  slack_channel_url: slackChannelUrl,
  slack_proof_url: slackProofUrl,
  started_at: new Date(startedAt).toISOString(),
  finished_at: new Date().toISOString(),
  viewport,
  continuous: true,
  continuous_from_human_gate_to_slack: true,
  trigger_captured: false,
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
    multimodal_extraction: multimodalReceipt ? {
      truth_mode: multimodalReceipt.truth_mode,
      validation_outcome: multimodalReceipt.validation_outcome,
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
  throw new Error(`V3 continuous proof failed verification: ${verificationErrors.join(" | ")}`);
}
console.log(`v3 continuous proof passed: ${finalDuration.toFixed(2)}s, sha256:${sha256}`);
console.log(finalVideoPath);
