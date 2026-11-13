import { expect, type Page } from "@playwright/test";

/** Start (or resume) from an intro page: /assess/<id>/ or /exam/<kind>/. Returns the attempt URL. */
export async function start(page: Page, introUrl: string): Promise<string> {
  await page.goto(introUrl);
  await page.locator('main form[action$="/start/"] button[type=submit]').click();
  await expect(page).toHaveURL(/\/attempt\/\d+\//);
  await page.waitForLoadState("load");
  return page.url();
}

const saved = (page: Page) =>
  page.waitForResponse((r) => /\/attempt\/\d+\/answer\//.test(r.url()) && r.request().method() === "POST");

/** Position and total from the "3 / 50" label. */
export async function where(page: Page): Promise<{ position: number; total: number }> {
  const raw = (await page.locator(".qcard__meta .muted").innerText()).trim();
  const text = raw.replace(/[०-९]/g, (d) => String(d.charCodeAt(0) - 0x0966)); // Devanagari digits
  const [position, total] = text.split("/").map((s) => parseInt(s.trim(), 10));
  return { position, total };
}

/** Answer the multiple-choice question on screen: `right` clicks the invented RIGHT option. */
export async function answer(page: Page, which: "right" | "wrong" = "right") {
  const label = page.locator("label.opt", { hasText: which === "right" ? "RIGHT answer" : "WRONG answer" }).first();
  await expect(label).toBeVisible();
  if (await label.locator("input").isChecked()) return; // already saved (a resumed attempt)
  const [response] = await Promise.all([saved(page), label.click()]);
  expect(response.headers()["x-answer-saved"]).toBe("1");
}

/** Go to the next question and wait until it is on screen. */
export async function next(page: Page) {
  const { position, total } = await where(page);
  await page.locator("#question-panel .qnav a.btn-primary").click(); // "Next" in any language
  await expect(async () => expect((await where(page)).position).toBe(position + 1)).toPass();
}

/** Answer every multiple-choice question from the one on screen to the last, ending on the review page. */
export async function answerAll(page: Page, which: "right" | "wrong" = "right") {
  for (;;) {
    const { position, total } = await where(page);
    await answer(page, which);
    if (position === total) {
      await page.locator("#question-panel .qnav a.btn-primary").click(); // "Review and submit" on the last one
      await expect(page).toHaveURL(/\/review\//);
      return;
    }
    await next(page);
  }
}

/** Press Submit on the review page and accept the confirmation. */
export async function submit(page: Page) {
  await page.locator('form[action$="/submit/"] button[type=submit]').click();
  await page.locator("#confirm-dialog [data-confirm-yes]").click();
  await expect(page).toHaveURL(/\/result\//);
}

/** The option values (random per-attempt tokens) on screen, in order. */
export const tokens = (page: Page) =>
  page.locator("input[name=choice]").evaluateAll((els) => els.map((e) => (e as HTMLInputElement).value));
