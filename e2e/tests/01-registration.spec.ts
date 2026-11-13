// Journeys 1-4 (architecture section 18): registration, closing batches, guardian consent.
import { test, expect } from "@playwright/test";
import { signInIfAsked, staffPage } from "../support/auth";
import { manifest } from "../support/data";
import { mailpit, linkFor } from "../support/mail";
import { setRegistration } from "../support/mentor";
import { fillRegistration, stamp, submitRegistration } from "../support/register";

const domain = manifest.domain;
const CONFIRM = /https?:\/\/\S*confirm-email\/\S+/;

test.describe.serial("registration", () => {
  test.afterAll(async ({ browser }) => {
    // leave the invented batches as the seed made them: B03 and B04 open
    const page = await staffPage(browser, "mentor1");
    await setRegistration(page, "E2E-B03", true);
    await setRegistration(page, "E2E-B04", true);
    await page.context().close();
  });

  test("1. no batch is accepting: no form, and a direct post is refused", async ({ page, browser }) => {
    const mentor = await staffPage(browser, "mentor1");
    await setRegistration(mentor, "E2E-B03", false);
    await setRegistration(mentor, "E2E-B04", false);

    await page.goto("/register/");
    const select = page.locator("select[name=batch]");
    if ((await select.count()) === 0) {
      // nothing at all is open (a clean database): the page says so and shows no form
      await expect(page.getByRole("heading", { name: /Registrations are closed/ })).toBeVisible();
      await expect(page.locator("input[name=email]")).toHaveCount(0);
    } else {
      // some other, real batch is open on this database: ours must not be offered
      await expect(select).not.toContainText("E2E batch three");
      await expect(select).not.toContainText("E2E batch four");
    }
    // a direct post for the closed batch must not create an account
    await page.goto("/accounts/login/");
    const csrf = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
    const email = `direct.${stamp()}@${domain}`;
    const res = await page.request.post("/register/", {
      headers: { "X-CSRFToken": csrf, Referer: page.url() },
      form: {
        certificate_name: "Direct Post",
        email,
        password: manifest.password,
        preferred_language: "en",
        date_of_birth: "2000-01-01",
        batch: String(manifest.batches["E2E-B03"]),
        accept_privacy: "on",
      },
    });
    expect(await res.text()).not.toMatch(/Check your inbox|check your email/i);
    await page.fill("input[name=login]", email);
    await page.fill("input[name=password]", manifest.password);
    await page.click("main button[type=submit]");
    await expect(page).toHaveURL(/\/accounts\/login/); // no such account
    await mentor.context().close();
  });

  test("2. an adult registers and verifies, lands on the pre-test prompt, mentor sees them", async ({ page, browser }) => {
    test.skip(!mailpit, "needs MAILPIT_URL to read the verification e-mail");
    const mentor = await staffPage(browser, "mentor1");
    await setRegistration(mentor, "E2E-B03", true);

    const email = `adult.${stamp()}@${domain}`;
    await fillRegistration(page, { email, batch: "E2E-B03", name: "Adult Journey" });
    await submitRegistration(page);
    await expect(page.getByRole("heading").first()).toBeVisible();
    await page.goto(await linkFor(email, CONFIRM));
    await page.locator("main button[type=submit]").click(); // allauth's "Confirm" button
    await signInIfAsked(page, email);
    await expect(page).toHaveURL(/exam\/pretest/);

    await mentor.goto(`/mentor/batches/${manifest.batches["E2E-B03"]}/`);
    await expect(mentor.getByText(email).first()).toBeVisible();
    await mentor.context().close();
  });

  test("3. a 17-year-old stays pending until the guardian confirms; no time is counted", async ({ page, browser }) => {
    test.skip(!mailpit, "needs MAILPIT_URL to read the e-mails");
    const email = `minor.${stamp()}@${domain}`;
    const guardian = `guardian.${stamp()}@${domain}`;
    const year = new Date().getFullYear() - 17;
    await fillRegistration(page, {
      email,
      batch: "E2E-B03",
      name: "Minor Journey",
      dob: `${year}-01-15`,
      guardian: { name: "Guardian Person", email: guardian },
    });
    await submitRegistration(page);
    await page.goto(await linkFor(email, CONFIRM));
    await page.locator("main button[type=submit]").click();
    await signInIfAsked(page, email);
    await expect(page).toHaveURL(/waiting/);
    await expect(page.getByRole("heading", { name: /Waiting for your guardian/ })).toBeVisible();

    // no time is counted while pending: the learning heartbeat never reports any
    const csrf = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
    const beat = await page.request.post("/learn/heartbeat/", { headers: { "X-CSRFToken": csrf }, form: { unit: "x" } });
    if ((beat.headers()["content-type"] ?? "").includes("json")) expect((await beat.json()).counted ?? 0).toBe(0);

    // the guardian confirms from the e-mailed link, in their own browser
    const other = await (await browser.newContext()).newPage();
    await other.goto(await linkFor(guardian, /https?:\/\/\S*guardian\/\S+/));
    await other.fill("input[name=guardian_name]", "Guardian Person");
    await other.check("input[name=declaration]");
    await other.locator("main form button[type=submit]").click();
    await expect(other.getByRole("heading").first()).toBeVisible();
    await other.context().close();

    await page.goto("/start/");
    await expect(page).not.toHaveURL(/waiting/);
  });

  test("4. batch closes while the form is open: refused, with the input kept", async ({ page, browser }) => {
    const mentor = await staffPage(browser, "mentor1");
    await setRegistration(mentor, "E2E-B03", true);
    await setRegistration(mentor, "E2E-B04", true);

    const email = `late.${stamp()}@${domain}`;
    await fillRegistration(page, { email, batch: "E2E-B03", name: "Late Journey" });
    await setRegistration(mentor, "E2E-B03", false); // B04 stays open, so the form can come back
    await submitRegistration(page);
    await expect(page.getByText(/not accepting registrations/i)).toBeVisible();
    await expect(page.locator("input[name=email]")).toHaveValue(email);
    await expect(page.locator("input[name=certificate_name]")).toHaveValue("Late Journey");
    await expect(page.getByText(/Check your inbox/i)).toHaveCount(0);
    await mentor.context().close();
  });
});
