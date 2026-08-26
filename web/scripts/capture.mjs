import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const target = process.env.APP_URL ?? "http://127.0.0.1:3024";
const output = process.env.VISUAL_OUTPUT ?? "../.playwright-mcp/ui-iteration";
await mkdir(output, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await page.goto(target);
await page.getByRole("heading", { name: "Cargo held at North Harbor" }).waitFor();
await page.screenshot({ path: `${output}/held.png`, fullPage: true });
await page.getByRole("button", { name: "Authority map", exact: true }).click();
await page.getByRole("heading", { name: "Authority moves. Agents do not own it." }).waitFor();
await page.screenshot({ path: `${output}/authority-held.png`, fullPage: true });

const action = page.getByTestId("primary-action");
for (const label of ["Start autonomous mission", "Approve bond & resume"]) {
  await action.getByText(label, { exact: true }).waitFor();
  await action.click();
}
await page.getByText("Container released", { exact: true }).waitFor();
await page.screenshot({ path: `${output}/authority-released.png`, fullPage: true });

await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({ path: `${output}/authority-mobile.png`, fullPage: true });
await page.setViewportSize({ width: 1440, height: 900 });
await page.getByRole("button", { name: "Mission", exact: true }).click();
await page.getByRole("heading", { name: "Cargo released" }).waitFor();
await page.screenshot({ path: `${output}/released.png`, fullPage: true });

await page.getByRole("button", { name: /^Evidence \d+$/ }).click();
await page.getByRole("button", { name: /Adjuster rejection scan/ }).click();
await page.getByAltText(/Synthetic scanned adjuster rejection/).waitFor();
await page.getByText(
  /Security pack v2 populated declaration_reference = GA\/NST\/0819/,
).waitFor();
await page.screenshot({ path: `${output}/multimodal-correction.png`, fullPage: true });

await page.getByRole("button", { name: /Broker email/ }).click();
await page.getByText("QUARANTINED", { exact: true }).waitFor();
await page.screenshot({ path: `${output}/quarantined-email.png`, fullPage: true });

await page.getByRole("button", { name: "Authority map", exact: true }).click();
await page.getByRole("button", { name: "Use light theme" }).click();
await page.screenshot({ path: `${output}/authority-light.png`, fullPage: true });
await browser.close();
console.log(`visual captures written to ${output}`);
