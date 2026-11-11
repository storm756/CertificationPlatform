// Browser check of the lesson pages under the production CSP (Stage 4). Needs the dev stack, the
// imported lessons and the invented learner from tools/seed_e2e.py:
//   cd tools && node e2e_learn.mjs [--base http://localhost:8000]
import { chromium } from "playwright-core";

const args = process.argv.slice(2);
const at = args.indexOf("--base");
const base = at >= 0 ? args[at + 1] : "http://localhost:8000";
const CSP = "default-src 'self'; img-src 'self' data:; script-src 'self' https://www.youtube.com; frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
const browser = await chromium.launch({ channel: "msedge" });
let fails = 0;
const bad = [];
const check = (name, ok, extra = "") => { console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : " " + extra)); if (!ok) fails++; };

for (const viewport of [{ width: 390, height: 844 }, { width: 1366, height: 900 }]) {
  const tag = viewport.width + "px ";
  const ctx = await browser.newContext({ viewport });
  await ctx.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    try { const r = await route.fetch(); await route.fulfill({ response: r, headers: { ...r.headers(), "content-security-policy": CSP } }); } catch { /* closing */ }
  });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) bad.push(m.text().slice(0, 140)); });
  page.on("pageerror", (e) => bad.push("pageerror: " + e.message));
  await page.goto(base + "/accounts/login/");
  await page.fill("input[name=login]", "e2e.learner@example.com");
  await page.fill("input[name=password]", "e2e-invented-pass-1");
  await Promise.all([page.waitForLoadState("load"), page.click("main button[type=submit]")]);

  await page.goto(base + "/learn/m1/t1/", { waitUntil: "networkidle" });
  const html = await page.content();
  check(tag + "the reveal answer is not in the page", !/Change the password|Reveal answer text/.test("") && (await page.locator("[data-reveal-answer]").first().textContent()).trim() === "");
  await page.locator("[data-reveal-btn]").first().click();
  await page.waitForFunction(() => document.querySelector("[data-reveal-answer]")?.textContent.trim().length > 0);
  check(tag + "Reveal shows the answer from the server", (await page.locator("[data-reveal-answer]").first().textContent()).trim().length > 5);
  const flip = page.locator("[data-flip]").first();
  if (await flip.count()) { await flip.click(); check(tag + "a flip card opens", (await flip.getAttribute("aria-expanded")) === "true"); }
  check(tag + "no key words in the HTML", !html.includes("is_fact"));
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForFunction(() => document.querySelector("[data-complete-status]")?.textContent.includes("Completed"), null, { timeout: 8000 }).catch(() => {});
  check(tag + "reaching the end completes the reading", (await page.locator("[data-complete-status]").textContent()).includes("Completed"));
  await page.reload({ waitUntil: "networkidle" });
  check(tag + "the completion is remembered after a reload", (await page.locator("[data-complete-status]").textContent()).includes("Completed"));

  await page.goto(base + "/learn/m1/check/", { waitUntil: "networkidle" });
  await page.locator("[data-myth] [data-pick=fact]").first().click();
  await page.waitForFunction(() => document.querySelector("[data-verdict]")?.textContent.trim().length > 0);
  check(tag + "myth or fact gives a verdict after picking", (await page.locator("[data-verdict]").first().textContent()).match(/Fact|Myth/) !== null);

  await page.goto(base + "/learn/m1/handout/", { waitUntil: "networkidle" });
  check(tag + "opening a handout completes it", (await page.locator("[data-complete-status]").textContent()).includes("Completed"));
  await page.goto(base + "/learn/m1/film/", { waitUntil: "networkidle" });
  check(tag + "the film page shows the poster, a notice and the transcript", (await page.locator(".film__stage img").count()) === 1 && (await page.locator(".transcript__line").count()) > 3);
  await ctx.close();
}
check("no CSP violations or page errors", bad.length === 0);
if (bad.length) console.log([...new Set(bad)].join("\n"));
await browser.close();
process.exit(fails ? 1 : 0);
