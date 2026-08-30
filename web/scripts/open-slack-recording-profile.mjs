import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { chromium } from "@playwright/test";

const slackChannelUrl = process.env.SLACK_CHANNEL_URL ??
  "https://app.slack.com/client/E0BSJNGCZHU/C0BSJNEE1HC";
const profileDirectory = path.resolve(
  process.env.SLACK_RECORDING_PROFILE ?? "../.playwright-mcp/slack-recording-profile",
);
const readyPath = path.resolve(
  process.env.SLACK_RECORDING_READY ?? "../.playwright-mcp/slack-recording-profile-ready.json",
);
const screenshotPath = path.resolve(
  process.env.SLACK_RECORDING_SCREENSHOT ?? "../.playwright-mcp/slack-recording-profile-ready.png",
);
const expectedMissionId = process.env.SLACK_EXPECTED_MISSION_ID;
const channelId = new URL(slackChannelUrl).pathname.split("/").filter(Boolean).at(-1);

await mkdir(profileDirectory, { recursive: true });
const context = await chromium.launchPersistentContext(profileDirectory, {
  executablePath: process.env.SLACK_CHROME_EXECUTABLE ?? "/usr/bin/google-chrome",
  headless: false,
  viewport: { width: 1440, height: 900 },
  colorScheme: "light",
  args: ["--no-first-run", "--disable-session-crashed-bubble", "--disable-infobars"],
});
const page = context.pages()[0] ?? await context.newPage();
for (const extra of context.pages().slice(1)) await extra.close();

console.log("Dedicated Slack recording window opened.");
console.log("Sign in if prompted and leave the target channel visible; this helper will close automatically when a synthetic Cargo Release message is detected.");
await page.goto(slackChannelUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });

try {
  await page.getByText("SYNTHETIC DEMO — NO REAL CARGO ACTION", { exact: false }).first().waitFor({
    timeout: 10 * 60_000,
  });
  let proofUrl = slackChannelUrl;
  if (expectedMissionId) {
    const missionText = page.getByText(expectedMissionId, { exact: false }).first();
    await missionText.waitFor({ state: "attached", timeout: 60_000 });
    const messageTextId = await missionText.getAttribute("id");
    const messageTimestamp = messageTextId?.match(/-(\d+\.\d+)-message_text$/)?.[1];
    if (!messageTimestamp || !channelId) {
      throw new Error(`Could not derive a Slack message timestamp for ${expectedMissionId}`);
    }
    proofUrl = `${slackChannelUrl}/thread/${channelId}-${messageTimestamp}`;
    await page.goto(proofUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.getByText(expectedMissionId, { exact: false }).filter({ visible: true }).first().waitFor({
      timeout: 60_000,
    });
  }
  await page.waitForTimeout(2_500);
  await page.screenshot({ path: screenshotPath });
  await writeFile(readyPath, `${JSON.stringify({
    status: "READY",
    channelUrl: slackChannelUrl,
    proofUrl,
    expectedMissionId: expectedMissionId ?? null,
    profileDirectory,
    verifiedAt: new Date().toISOString(),
  }, null, 2)}\n`, "utf8");
  console.log(`Slack recording profile ready: ${readyPath}`);
} finally {
  await context.close();
}
