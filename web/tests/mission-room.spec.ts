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
