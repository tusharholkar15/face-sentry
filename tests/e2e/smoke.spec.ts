import { test, expect } from "@playwright/test";

test.describe("FaceSentry Web HUD Smoke Test", () => {
  test("should render the header and HUD dashboard", async ({ page }) => {
    await page.goto("/");
    // Verify brand title is present
    await expect(page.locator("h1")).toContainText("FaceSentry");

    // Verify main navigation or HUD sections are present
    await expect(page.getByText("Real-time Video Feed & Face Presence")).toBeVisible();
    await expect(page.getByText("Policy & Hardware Controls")).toBeVisible();
    await expect(page.getByText("Security Event Audit History")).toBeVisible();
  });
});
