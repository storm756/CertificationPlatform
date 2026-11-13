import { expect, type Page } from "@playwright/test";
import { manifest } from "./data";

/** Open or close registration for a batch, through the mentor's real settings form. */
export async function setRegistration(page: Page, batch: string, open: boolean) {
  await page.goto(`/mentor/batches/${manifest.batches[batch]}/`);
  const form = page.locator('form[action$="/settings/"]');
  const box = form.locator("input[name=accepting]");
  if (open) await box.check();
  else await box.uncheck();
  await form.locator("button[type=submit]").click();
  await expect(page.getByText("Registration settings saved")).toBeVisible();
}
