import { expect, test } from "@playwright/test";

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
  await page.getByRole("button", { name: "Documents 3", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Full security submission pack" })).toBeVisible();
});

test("architecture truth and quarantined evidence stay inspectable", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("primary-action").click();
  await page.getByRole("button", { name: "Evidence 4", exact: true }).click();
  await expect(page.getByText("Broker email", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Broker email/ }).click();
  await expect(page.getByText("QUARANTINED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Architecture/ }).click();
  await expect(page.getByRole("heading", { name: "Transition ownership" })).toBeVisible();
  await expect(page.locator(".architecture-rule")).toContainText(
    "Model output and managed memory never write release state",
  );
});

test("Gemma review is visible but cannot authorize cargo", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("primary-action").click();
  await page.getByRole("button", { name: "AI checks 1", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Second opinion, zero authority" })).toBeVisible();
  await expect(page.getByText("google/gemma-4-26b-a4b-it-maas", { exact: true })).toBeVisible();
  await expect(page.getByText(/release_authority=false/)).toBeVisible();
  await expect(
    page.getByText("SECURITY_AMOUNT_PROVENANCE_MISSING", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("PHYSICAL RELEASE: HELD", { exact: false })).toBeVisible();
  await expect(page.getByTestId("primary-action")).toContainText("Approve bond & resume");
});

test("an existing mission can be reopened from the recording URL", async ({ page, request }) => {
  const response = await request.post("http://127.0.0.1:8095/v1/missions/demo");
  expect(response.ok()).toBeTruthy();
  const snapshot = await response.json() as { mission: { id: string; case_ref: string } };

  await page.goto(`/?mission=${encodeURIComponent(snapshot.mission.id)}`);
  await expect(page.getByText(snapshot.mission.case_ref, { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset exact fixture" })).toBeVisible();
});
