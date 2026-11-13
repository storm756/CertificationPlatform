// Journeys 5-11 (architecture section 18): attempts, locks, results, and what the browser may see.
import { test, expect, type Page } from "@playwright/test";
import { signIn } from "../support/auth";
import { manifest } from "../support/data";
import { answer, answerAll, next, start, submit, tokens } from "../support/attempt";

const mcq = `/assess/${manifest.parts.mcq}/`;
const FORBIDDEN = /\bcorrect\b|is_correct|\[\[!|gate_if_missed|"gate"|"ok"\s*:|"answer"/i;

async function newPhone(browser: import("@playwright/test").Browser, key: string) {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, key);
  return page;
}

test.describe.serial("attempts", () => {
  let attemptUrl = "";

  test("5. the connection drops mid-quiz; resuming on another phone keeps the same attempt and answers", async ({ browser }) => {
    const phone1 = await newPhone(browser, "work");
    attemptUrl = await start(phone1, mcq);
    await answer(phone1);
    await next(phone1);
    await answer(phone1);
    await phone1.context().setOffline(true); // the connection drops
    await phone1.context().setOffline(false);

    const phone2 = await newPhone(browser, "work");
    await phone2.goto(mcq);
    await expect(phone2.getByRole("button", { name: /Resume where you left off/ })).toBeVisible();
    await phone2.getByRole("button", { name: /Resume where you left off/ }).click();
    await expect(phone2).toHaveURL(attemptUrl);
    await phone2.goto(attemptUrl + "q/1/");
    await expect(phone2.locator("label.opt input:checked")).toHaveCount(1); // the first answer is still there
    await phone2.goto(attemptUrl + "q/2/");
    await expect(phone2.locator("label.opt input:checked")).toHaveCount(1);
    await phone1.context().close();
    await phone2.context().close();
  });

  test("6. a double tap on Submit gives one result", async ({ browser }) => {
    const page = await newPhone(browser, "work");
    await page.goto(mcq);
    await page.getByRole("button", { name: /Resume where you left off/ }).click();
    await page.goto(attemptUrl + "q/3/");
    await answerAll(page);
    const csrf = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
    const post = () => page.request.post(attemptUrl + "submit/", { headers: { "X-CSRFToken": csrf, Referer: page.url() }, maxRedirects: 0 });
    const [a, b] = await Promise.all([post(), post()]);
    expect([a.status(), b.status()].every((s) => s === 302 || s === 303 || s === 200)).toBeTruthy();
    await page.goto(mcq);
    await expect(page.getByRole("heading", { name: "Your attempts" })).toBeVisible();
    await expect(page.locator(".result-list li")).toHaveCount(1); // one attempt, one result
    await page.goto(attemptUrl + "result/");
    await expect(page.getByRole("heading", { name: /Passed|Not yet|doesn.t count/ })).toBeVisible();
    await page.context().close();
  });

  test("9. a result page shows right/wrong marks and hints, never the correct options", async ({ browser }) => {
    const page = await newPhone(browser, "work");
    await page.goto(attemptUrl + "result/");
    await expect(page.getByRole("heading", { name: /Question by question/ })).toBeVisible();
    await expect(page.getByText("Hint").first()).toBeVisible();
    await expect(page.getByText("E2E hint.").first()).toBeVisible();
    await expect(page.locator(".status--done, .status--todo").first()).toBeVisible();
    const body = await page.locator("body").innerText();
    expect(body).not.toMatch(/The RIGHT answer|A WRONG answer/); // no option text at all
    expect(await page.content()).not.toMatch(FORBIDDEN);
    await page.context().close();
  });

  test("10. any assessment page, inspected, carries no keys or markers", async ({ browser }) => {
    const page = await newPhone(browser, "fresh");
    const seen: string[] = [];
    page.on("response", async (r) => {
      const type = r.headers()["content-type"] ?? "";
      if (/html|json/.test(type) && /\/attempt\//.test(r.url())) seen.push(await r.text().catch(() => ""));
    });
    const url = await start(page, mcq);
    for (let n = 1; n <= 5; n++) {
      await page.goto(`${url}q/${n}/`);
      seen.push(await page.content());
      const t = await tokens(page);
      expect(t).toHaveLength(4);
      for (const token of t) expect(token).toMatch(/^[A-Za-z0-9_-]{8,}$/); // random, never o1, o2 ...
      expect(new Set(t).size).toBe(4);
    }
    await page.goto(`${url}review/`);
    seen.push(await page.content());
    // the interactive gate question: the projection the engine draws from
    const gate = await start(page, `/assess/${manifest.parts.gate}/`);
    seen.push(await page.content());
    const qjson = await page.locator("[data-q]").first().getAttribute("data-q");
    expect(qjson).toBeTruthy();
    seen.push(qjson ?? "");
    const data = await page.request.get(`${gate}q/1/data/`);
    seen.push(await data.text());
    for (const text of seen) {
      const m = text.match(FORBIDDEN);
      expect(m ? text.slice(Math.max(0, (m.index ?? 0) - 80), (m.index ?? 0) + 80) : null).toBeNull();
    }
    expect(qjson).not.toMatch(/"gate"|gate_message|"why"|endanger|"correct"|"hint"/i); // no gate flag, reason, key or hint
    await page.context().close();
  });
});

test("7. one part submitted with blanks: the final stays locked, with the reason", async ({ browser }) => {
  const page = await newPhone(browser, "locked");
  await page.goto("/exam/final/");
  await expect(page.getByText(/submit it once with every question answered/i).first()).toBeVisible();
  await expect(page.locator('main form[action$="/start/"] button')).toHaveCount(0);
  const csrf = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  const res = await page.request.post("/exam/final/start/", { headers: { "X-CSRFToken": csrf, Referer: page.url() }, maxRedirects: 0 });
  expect(res.status()).toBe(302);
  expect(res.headers()["location"] ?? "").not.toMatch(/attempt\/\d+/); // no attempt was made
  await page.context().close();
});

test("8. a gate choice in an interactive attempt: scored, not counted, with the hint", async ({ browser }) => {
  const page = await newPhone(browser, "other");
  await start(page, `/assess/${manifest.parts.gate}/`);
  await expect(page.locator("[data-engine]")).toBeVisible();
  await page.getByText("Share the code", { exact: true }).click(); // the gate option
  await expect(page.locator("#save-status")).toHaveAttribute("data-state", "saved");
  await page.locator("#question-panel").getByRole("link", { name: /Review and submit/ }).click();
  await submit(page);
  await expect(page.getByRole("heading", { name: /doesn.t count/ })).toBeVisible();
  await expect(page.getByText("Safety gate")).toBeVisible();
  await expect(page.getByText("E2E gate hint.")).toBeVisible();
  await expect(page.getByText(/^counts$/)).toHaveCount(0); // not counted
  await page.context().close();
});

async function takeFinal(page: Page, which: "right" | "wrong" = "right") {
  await start(page, "/exam/final/");
  await answerAll(page, which);
  await submit(page);
}

test("11. a final attempt shows the overall percentage and bands only", async ({ browser }) => {
  const page = await newPhone(browser, "final");
  await takeFinal(page);
  await expect(page.getByRole("heading", { name: /How each module went/ })).toBeVisible();
  await expect(page.getByText(/100/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Question by question/ })).toHaveCount(0);
  await expect(page.getByText("E2E hint.")).toHaveCount(0);
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/The RIGHT answer|A WRONG answer|E2E question/);
  await page.context().close();
});

test("extra: a signed-in learner who opens /admin/ gets a 403, not an endless redirect", async ({ browser }) => {
  const page = await newPhone(browser, "fresh");
  const response = await page.goto("/admin/");
  expect(response?.status()).toBe(403);
  await page.context().close();
});
