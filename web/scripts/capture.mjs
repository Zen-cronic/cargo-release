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

const action = page.getByTestId("primary-action");
for (const label of ["Start autonomous mission", "Approve bond & resume"]) {
  await action.getByText(label, { exact: true }).waitFor();
  await action.click();
}
await page.getByRole("heading", { name: "Cargo released" }).waitFor();
await page.screenshot({ path: `${output}/released.png`, fullPage: true });
await browser.close();
console.log(`visual captures written to ${output}`);
