// Journeys 12-16 (architecture section 18): certificates, mentor scoping, mark changes, language.
import { test, expect, type Browser, type Page } from "@playwright/test";
import { signIn, staffPage } from "../support/auth";
import { answer, answerAll, next, start, submit, tokens, where } from "../support/attempt";
import { manifest } from "../support/data";

async function learner(browser: Browser, key: string) {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, key);
  return page;
}

async function takeFinal(page: Page) {
  await start(page, "/exam/final/");
  await answerAll(page);
  await submit(page);
}

async function certificateCount(browser: Browser, email: string) {
  const admin = await staffPage(browser, "admin");
  await admin.goto(`/admin/certificates/certificate/?q=${encodeURIComponent(email)}`);
  const rows = await admin.locator("#result_list tbody tr").count();
  await admin.context().close();
  return rows;
}

test.describe.serial("certificates", () => {
  test("12. eligible with auto-issue on: the last submit issues a certificate, and its public page says Valid + grade", async ({ browser }) => {
    const page = await learner(browser, "cert");
    await takeFinal(page);
    await page.goto("/certificate/");
    await expect(page.getByRole("heading", { name: /Your certificate is ready/ })).toBeVisible();
    await expect(page.getByText(/CCFR-\d{4}-E2E-\d{6}/)).toBeVisible();
    const verify = await page.locator('a[href^="/verify/"]').first().getAttribute("href");
    expect(verify).toBeTruthy();

    const visitor = await (await browser.newContext()).newPage(); // anyone, not signed in
    await visitor.goto(verify ?? "/verify/");
    await expect(visitor.getByText("Valid").first()).toBeVisible();
    await expect(visitor.getByText("Grade").first()).toBeVisible();
    await expect(visitor.getByText(/Certificate Learner/)).toBeVisible();
    await visitor.context().close();
    await page.context().close();
  });

  test("13. two tabs submit together: still one certificate", async ({ browser }) => {
    const tabA = await learner(browser, "race");
    await start(tabA, "/exam/final/");
    await answerAll(tabA);
    const review = tabA.url();
    const tabB = await tabA.context().newPage();
    await tabB.goto(review);
    await Promise.all([submit(tabA), submit(tabB)]);
    await tabA.goto("/certificate/");
    await expect(tabA.getByRole("heading", { name: /Your certificate is ready/ })).toBeVisible();
    expect(await certificateCount(browser, manifest.users["race"])).toBe(1);
    await tabA.context().close();
  });

  test("14. a mentor of B01 asking for B02 data or a final-pool question gets 403, and it is logged", async ({ browser }) => {
    const admin = await staffPage(browser, "admin");
    const denied = async () => {
      await admin.goto("/admin/audit/auditevent/?q=access.denied");
      return admin.locator("#result_list tbody tr").count();
    };
    const before = await denied();

    const mentor = await staffPage(browser, "mentor1");
    const own = await mentor.goto(`/mentor/batches/${manifest.batches["E2E-B01"]}/`);
    expect(own?.status()).toBe(200); // their own batch is fine
    const b02 = await mentor.goto(`/mentor/batches/${manifest.batches["E2E-B02"]}/`);
    expect(b02?.status()).toBe(403);
    const learnerOfB02 = await mentor.goto(`/mentor/learners/${manifest.learner_ids["cert"]}/`);
    expect(learnerOfB02?.status()).toBe(403);
    const csrf = (await mentor.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
    const exportB02 = await mentor.request.post(`/mentor/batches/${manifest.batches["E2E-B02"]}/export/`, {
      headers: { "X-CSRFToken": csrf, Referer: mentor.url() },
    });
    expect(exportB02.status()).toBe(403);
    expect(manifest.final_question_id).toBeTruthy();
    const finalQuestion = await mentor.goto(`/staff/questions/${manifest.final_question_id}/`);
    expect(finalQuestion?.status()).toBe(403);
    await mentor.context().close();

    expect(await denied()).toBeGreaterThan(before); // logged as access.denied
    await admin.context().close();
  });

  test("15. an admin makes a new part counted: preview, confirm; results change, issued certificates do not", async ({ browser }) => {
    const admin = await staffPage(browser, "admin");
    const marks = async () => {
      await admin.goto("/staff/marks/1/");
      const rows = admin.locator("table tbody tr");
      const extra = rows.filter({ hasText: "E2E-J extra part" });
      const others = rows.filter({ hasNotText: "E2E-J extra part" }).filter({ has: admin.locator("input[type=checkbox]:checked") });
      return { extra, other: others.first() };
    };
    const change = async (extraCounted: boolean, delta: number) => {
      const { extra, other } = await marks();
      const field = other.locator("input[type=number]");
      const was = parseInt(await field.inputValue(), 10);
      await field.fill(String(was + delta));
      const box = extra.locator("input[type=checkbox]");
      if (extraCounted) await box.check();
      else await box.uncheck();
      await extra.locator("input[type=number]").fill(String(extraCounted ? 10 : 0));
      await admin.getByRole("button", { name: "Preview the impact" }).click();
      await expect(admin.getByRole("heading", { name: "Impact preview" })).toBeVisible();
      return was;
    };

    const original = await change(true, -10);
    const text = await admin.locator(".impact").innerText();
    expect(text).toMatch(/Issued certificates never change/);
    const changed = parseInt(text.match(/Overall score changes for (\d+) learners/)?.[1] ?? "0", 10);
    expect(changed).toBeGreaterThan(0); // the results change for learners who have finished the modules
    await admin.getByRole("button", { name: "Confirm and save" }).click();
    await expect(admin.locator("table tbody tr").filter({ hasText: "E2E-J extra part" }).locator("input[type=checkbox]")).toBeChecked();

    // a certificate issued before the change is still valid
    const cert = await learner(browser, "cert");
    await cert.goto("/certificate/");
    await expect(cert.getByRole("heading", { name: /Your certificate is ready/ })).toBeVisible();
    await cert.context().close();

    // put it back, through the same screen
    const { other } = await marks();
    const field = other.locator("input[type=number]");
    await field.fill(String(original));
    const extraRow = admin.locator("table tbody tr").filter({ hasText: "E2E-J extra part" });
    await extraRow.locator("input[type=checkbox]").uncheck();
    await extraRow.locator("input[type=number]").fill("0");
    await admin.getByRole("button", { name: "Preview the impact" }).click();
    await admin.getByRole("button", { name: "Confirm and save" }).click();
    await expect(admin.locator("table tbody tr").filter({ hasText: "E2E-J extra part" }).locator("input[type=checkbox]")).not.toBeChecked();
    await admin.context().close();
  });

  test("16. a Marathi learner switches language mid-final: same tokens, same score", async ({ browser }) => {
    const page = await learner(browser, "marathi");
    await expect(page.locator("html")).toHaveAttribute("lang", "mr");
    const attempt = await start(page, "/exam/final/");
    await page.goto(`${attempt}q/1/`); // a resumed attempt may open further on
    await answer(page);
    await next(page);
    await answer(page);
    await next(page);
    const before = await tokens(page);
    expect(before.length).toBe(4);

    const menu = page.locator(".nav-toggle");
    if (await menu.isVisible()) await menu.click(); // on a phone the language box is in the menu
    await page.locator("select[data-lang-select]").selectOption("en");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await page.goto(`${attempt}q/3/`);
    expect(await tokens(page)).toEqual(before); // the same random tokens in the other language

    for (;;) {
      const { position, total } = await where(page);
      await answer(page);
      if (position === total) break;
      await next(page);
    }
    await page.locator("#question-panel .qnav a.btn-primary").click();
    await submit(page);
    await expect(page.getByText(/100/).first()).toBeVisible(); // every answer was right: the same score
    await page.context().close();
  });
});
