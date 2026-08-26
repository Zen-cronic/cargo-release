import { expect, test } from "@playwright/test";

const controllerPort = process.env.CARGO_RELEASE_E2E_CONTROLLER_PORT ?? "8095";

test("releases cargo only after adjuster acceptance and carrier read-back", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Cargo held at North Harbor" })).toBeVisible();
  const action = page.getByTestId("primary-action");

  for (const label of ["Start autonomous mission", "Approve bond & resume"]) {
    await expect(action).toHaveText(new RegExp(label));
    await action.click();
  }

  await expect(page.getByRole("heading", { name: "Cargo released" })).toBeVisible();
  await expect(page.getByText("Carrier read-back verified")).toBeVisible();
  await expect(page.getByTestId("adjustment-state")).toContainText("OPEN");
  await expect(page.getByText("RELEASED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("COMPLETED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Evidence 5", exact: true }).click();
  await page.getByRole("button", { name: /Adjuster rejection scan/ }).click();
  await expect(page.getByAltText(/Synthetic scanned adjuster rejection/)).toBeVisible();
  await expect(page.getByText("ACCEPTED", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/Security pack v2 populated declaration_reference = GA\/NST\/0819/),
  ).toBeVisible();
  await page.screenshot({
    path: "../.playwright-mcp/ui-iteration/multimodal-correction.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Documents 3", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Full security submission pack" })).toBeVisible();
});

test("architecture truth and quarantined evidence stay inspectable", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("primary-action").click();
  await page.getByRole("button", { name: "Evidence 5", exact: true }).click();
  await expect(page.getByText(/Broker email · TEXT/)).toBeVisible();
  await page.getByRole("button", { name: /Broker email/ }).click();
  await expect(page.getByText("QUARANTINED", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../.playwright-mcp/ui-iteration/quarantined-email.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /Architecture/ }).click();
  await expect(page.getByRole("heading", { name: "Transition ownership" })).toBeVisible();
  await expect(page.locator(".architecture-rule")).toContainText(
    "Model output and managed memory never write release state",
  );
  await expect(page.getByText("Fail-closed IAP authorization", { exact: false })).toBeVisible();
  await expect(page.getByText(/route proof pending|enforcement remains pending/)).toHaveCount(0);
});

test("authority map exposes real worker scopes and a duplicate-safe friction metric", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Authority map", exact: true }).click();

  await expect(
    page.getByRole("heading", { name: "Authority moves. Agents do not own it." }),
  ).toBeVisible();
  await expect(page.getByText("release_authority=false for every model and worker")).toBeVisible();
  await expect(page.getByText("Evidence worker", { exact: true })).toBeVisible();
  await expect(page.getByText("Security worker", { exact: true })).toBeVisible();
  await expect(page.getByText("Authority worker", { exact: true })).toBeVisible();
  await expect(page.getByText("Recovery worker", { exact: true })).toBeVisible();
  await expect(page.getByTestId("human-attestations")).toHaveText("0");
  await expect(page.getByTestId("friction-metric")).toContainText("0 / 8");

  const action = page.getByTestId("primary-action");
  await action.click();
  await action.click();
  await expect(page.getByTestId("human-attestations")).toHaveText("1");
  await expect(page.getByTestId("friction-metric")).toContainText("7 / 8");
  await expect(page.getByTestId("friction-metric")).toContainText("Marked notice 0/1");

  await page.getByRole("button", { name: /Agent fleet/ }).click();
  await expect(
    page.getByRole("heading", { name: "Agents versus deterministic actors" }),
  ).toBeVisible();
  await expect(page.getByText("Manifest Evidence Worker", { exact: true })).toBeVisible();
  await expect(page.getByText("Deterministic Receipt Saga", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await page.getByRole("button", { name: "Use light theme" }).click();
  await expect(page.locator(".app-shell")).toHaveClass(/theme-light/);
  await expect(page.getByRole("button", { name: "Use dark theme" })).toBeVisible();

  const lightThemeContrast = await page.evaluate(() => {
    const heading = document.querySelector<HTMLElement>(".panel-heading h1");
    const stage = document.querySelector<HTMLElement>(".workspace-stage");
    if (!heading || !stage) return 0;

    const canvas = document.createElement("canvas");
    canvas.width = 1;
    canvas.height = 1;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return 0;
    const linearSrgb = (color: string) => {
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      return [...context.getImageData(0, 0, 1, 1).data]
        .slice(0, 3)
        .map((channel) => channel / 255)
        .map((channel) => channel <= 0.04045
          ? channel / 12.92
          : ((channel + 0.055) / 1.055) ** 2.4);
    };
    const luminance = (channels: number[]) => channels
      .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);

    const foreground = luminance(linearSrgb(getComputedStyle(heading).color));
    const background = luminance(linearSrgb(
      getComputedStyle(stage).getPropertyValue("--background"),
    ));
    return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
  });
  expect(lightThemeContrast).toBeGreaterThanOrEqual(4.5);

  await page.setViewportSize({ width: 390, height: 844 });
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});

test("advisory models are visible but cannot authorize cargo", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("primary-action").click();
  await page.getByRole("button", { name: "AI checks 3", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Second opinion, zero authority" })).toBeVisible();
  await expect(page.getByText("google/gemma-4-26b-a4b-it-maas", { exact: true })).toBeVisible();
  const authorityBoundaries = page.getByText(/release_authority=false/);
  await expect(authorityBoundaries).toHaveCount(3);
  await expect(authorityBoundaries.first()).toBeVisible();
  await expect(authorityBoundaries.nth(1)).toBeVisible();
  await expect(
    page.getByText("SECURITY_AMOUNT_PROVENANCE_MISSING", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("gemini-embedding-2", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Nearest reviewed synthetic examples—not precedent or recommendation", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("reviewed-provenance-005", { exact: true })).toBeVisible();
  await expect(page.getByText("8 reviewed cases", { exact: true })).toBeVisible();
  await expect(page.getByText("scores withheld", { exact: true })).toBeVisible();
  await expect(page.getByText("PHYSICAL RELEASE: HELD", { exact: false })).toBeVisible();
  await expect(page.getByTestId("primary-action")).toContainText("Approve bond & resume");
});

test("Veo replay is generated only after release and stays training-only", async ({ page }) => {
  await page.goto("/");
  const action = page.getByTestId("primary-action");
  await action.click();
  await action.click();
  await expect(page.getByRole("heading", { name: "Cargo released" })).toBeVisible();

  await page.getByRole("button", { name: "AI checks 3", exact: true }).click();
  await page.getByTestId("generate-replay").click();

  await expect(page.getByText("veo-3.1-fast-generate-001", { exact: true })).toBeVisible();
  await expect(
    page.getByText("SYNTHETIC REPLAY — NOT EVIDENCE — GENERATED AFTER RELEASE", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("training only", { exact: false })).toBeVisible();
  await expect(page.getByText("PHYSICAL RELEASE: RELEASED", { exact: false })).toBeVisible();
  await expect(page.getByText(/release_authority=false/)).toHaveCount(4);
  await expect(page.getByRole("button", { name: "AI checks 4", exact: true })).toBeVisible();
});

test("an existing mission can be reopened from the recording URL", async ({ page, request }) => {
  const response = await request.post(
    `http://127.0.0.1:${controllerPort}/v1/missions/demo`,
  );
  expect(response.ok()).toBeTruthy();
  const snapshot = await response.json() as { mission: { id: string; case_ref: string } };

  await page.goto(`/?mission=${encodeURIComponent(snapshot.mission.id)}`);
  await expect(page.getByText(snapshot.mission.case_ref, { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset exact fixture" })).toBeVisible();
});
