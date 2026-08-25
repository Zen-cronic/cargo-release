import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "@playwright/test";

const appUrl = process.env.APP_URL ??
  "https://cargo-release-web-1015646664425.us-central1.run.app";
const outputDirectory = path.resolve(
  process.env.REHEARSAL_OUTPUT ?? "../.playwright-mcp/demo-rehearsal",
);
const missions = {
  native: process.env.NATIVE_MISSION_ID ?? "mission-abe2d197faad",
  slack: process.env.SLACK_MISSION_ID ?? "mission-f29320b1dcd0",
  models: process.env.MODEL_MISSION_ID ?? "mission-f92f38ea26c6",
};

await mkdir(outputDirectory, { recursive: true });

const report = {
  app_url: appUrl,
  started_at: new Date().toISOString(),
  status: "RUNNING",
  viewport: { width: 1440, height: 900 },
  missions,
  native_eventarc_message_id:
    process.env.NATIVE_EVENTARC_MESSAGE_ID ?? "21085566718402962",
  assertions: [],
  captures: [],
};

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: report.viewport,
  deviceScaleFactor: 1,
});
const page = await context.newPage();

function recordAssertion(name, detail) {
  report.assertions.push({ name, detail, passed: true });
}

async function openMission(name, heading = "Cargo released") {
  const missionId = missions[name];
  const startedAt = Date.now();
  await page.goto(`${appUrl}/?mission=${encodeURIComponent(missionId)}`, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  await page.getByRole("heading", { name: heading }).waitFor({
    state: "visible",
    timeout: 45_000,
  });
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  assert.ok(
    overflow.scrollWidth <= overflow.innerWidth,
    `${name} mission has horizontal overflow: ${JSON.stringify(overflow)}`,
  );
  recordAssertion(`${name}_mission_loads`, {
    mission_id: missionId,
    elapsed_ms: Date.now() - startedAt,
  });
  recordAssertion(`${name}_viewport_has_no_horizontal_overflow`, overflow);
}

async function capture(name, fullPage = false) {
  const capturePath = path.join(outputDirectory, `${name}.png`);
  await page.screenshot({ path: capturePath, fullPage });
  report.captures.push(capturePath);
}

try {
  await openMission("native", "Cargo held at North Harbor");
  await page.getByText("Native Eventarc mission", { exact: true }).waitFor();
  await page.getByText("NATIVE", { exact: true }).first().waitFor();
  await page.getByTestId("primary-action").getByText(
    "Approve bond & resume",
    { exact: true },
  ).waitFor();
  recordAssertion("native_eventarc_truth_is_visible", {
    footer: "Native Eventarc mission",
    truth_mode: "NATIVE",
    release_state: "READY_FOR_SIGNATURE",
    human_gate: "Approve bond & resume",
  });
  await capture("01-native-eventarc");

  await openMission("slack");
  await page.getByText(
    "Marked synthetic notice delivered to operator-owned Slack #general.",
    { exact: false },
  ).waitFor();
  await page.getByRole("button", { name: "Authority map", exact: true }).click();
  await page.getByRole("heading", {
    name: "Authority moves. Agents do not own it.",
  }).waitFor();
  await page.getByText(
    "release_authority=false for every model and worker",
    { exact: true },
  ).waitFor();
  for (const worker of [
    "Evidence worker",
    "Security worker",
    "Authority worker",
    "Recovery worker",
  ]) {
    await page.getByText(worker, { exact: true }).waitFor();
  }
  await page.getByTestId("human-attestations").getByText(
    "1",
    { exact: true },
  ).waitFor();
  await page.getByTestId("friction-metric").getByText(
    "8 / 8",
    { exact: false },
  ).waitFor();
  recordAssertion("authority_map_and_friction_metric_are_visible", {
    human_attestations: 1,
    autonomous_downstream_actions: 8,
    workers: 4,
    release_authority: false,
  });
  await capture("02-authority-map", true);

  await page.getByRole("button", { name: /^Activity \d+$/ }).click();
  await page.getByText("Synthetic outbound proof · non-authoritative", {
    exact: true,
  }).waitFor();
  await page.getByText("slack-a86e1c8442bf4cf0", { exact: false }).waitFor();
  recordAssertion("slack_delivery_proof_is_visible", {
    endpoint: "operator-owned Slack #general",
    provider_ref: "slack-a86e1c8442bf4cf0",
  });
  await capture("03-slack-activity");

  await openMission("models");
  await page.getByRole("button", { name: /^AI checks \d+$/ }).click();
  for (const model of [
    "google/gemma-4-26b-a4b-it-maas",
    "gemini-embedding-2",
    "veo-3.1-fast-generate-001",
  ]) {
    await page.getByText(model, { exact: true }).waitFor();
  }
  await page.getByText(
    "SYNTHETIC REPLAY — NOT EVIDENCE — GENERATED AFTER RELEASE",
    { exact: true },
  ).waitFor();
  const authorityBoundaries = page.getByText(/release_authority=false/);
  assert.equal(
    await authorityBoundaries.count(),
    3,
    "Expected three visible model authority boundaries",
  );
  recordAssertion("three_bonus_models_and_authority_boundaries_are_visible", {
    models: [
      "Gemma 4",
      "Gemini Embedding 2",
      "Veo 3.1",
    ],
    release_authority_false_count: 3,
  });
  await capture("04-model-receipts", true);

  await page.getByRole("button", { name: "Architecture", exact: true }).click();
  const architecture = page.getByRole("dialog", { name: "Architecture" });
  await architecture.getByRole("heading", { name: "Transition ownership" }).waitFor();
  await architecture.getByText(
    "Model output and managed memory never write release state",
    { exact: false },
  ).waitFor();
  recordAssertion("deterministic_transition_boundary_is_visible", {
    heading: "Transition ownership",
  });
  await capture("05-architecture-boundary");

  report.status = "PASSED";
} catch (error) {
  report.status = "FAILED";
  report.error = error instanceof Error ? error.stack ?? error.message : String(error);
  throw error;
} finally {
  report.finished_at = new Date().toISOString();
  report.elapsed_ms = Date.parse(report.finished_at) - Date.parse(report.started_at);
  await writeFile(
    path.join(outputDirectory, "report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );
  await browser.close();
}

console.log(
  `production rehearsal ${report.status.toLowerCase()}: ${report.assertions.length} assertions, ${report.captures.length} captures in ${outputDirectory}`,
);
