// Browser check of the catalogue and module pages: search, filters, tabs, outline and navigation,
// under the production CSP at 390px, 1366px and 1920px. Needs the dev stack with the lessons imported.
//   cd tools && node e2e_catalogue.mjs [--base http://localhost:8000]
import { chromium } from "playwright-core";

const at = process.argv.indexOf("--base");
const base = at >= 0 ? process.argv[at + 1] : "http://localhost:8000";
const CSP = "default-src 'self'; img-src 'self' data:; script-src 'self' https://www.youtube.com; frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
const browser = await chromium.launch({ channel: "msedge" });
const bad = [];
let fails = 0;
const check = (n, ok, x = "") => { console.log((ok ? "ok   " : "FAIL ") + n + (ok ? "" : " " + x)); if (!ok) fails++; };

for (const [w, h] of [[390, 844], [1366, 900], [1920, 1080]]) {
  const tag = `${w}px `;
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.route("**/*", async (r) => { if (r.request().resourceType() !== "document") return r.continue(); try { const x = await r.fetch(); await r.fulfill({ response: x, headers: { ...x.headers(), "content-security-policy": CSP } }); } catch { /* closing */ } });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) bad.push(m.text().slice(0, 140)); });
  page.on("pageerror", (e) => bad.push("pageerror: " + e.message));

  await page.goto(base + "/learn/", { waitUntil: "networkidle" });
  const visible = () => page.locator(".mod-card:not([hidden])").count();
  check(tag + "catalogue: ten cards (nine modules and the capstone)", (await page.locator(".mod-card").count()) === 10);
  check(tag + "catalogue: the navy banner, the five-part journey strip, search and filters are there", (await page.locator(".band h1").count()) === 1 && (await page.locator(".journey-step").count()) === 5 && (await page.locator("#cat-search").count()) === 1 && (await page.locator("[data-filter]").count()) === 4);
  check(tag + "catalogue: the capstone card and the practice-mock callout are in place", (await page.locator('.mod-card[data-mod="10"]').count()) === 1 && (await page.locator(".mock-callout").count()) === 1);
  await page.locator(".mod-card__poster").first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  const posterOk = await page.locator(".mod-card__poster").first().evaluate((i) => i.complete && i.naturalWidth > 0);
  check(tag + "catalogue: the card artwork loads", posterOk);
  await page.fill("#cat-search", "deepfake");
  check(tag + "search finds the module by a topic word", (await visible()) >= 1 && (await visible()) < 10, String(await visible()));
  await page.fill("#cat-search", "zzzzqq");
  check(tag + "search with no match shows the empty message", (await visible()) === 0 && !(await page.locator("[data-cat-empty]").isHidden()));
  await page.fill("#cat-search", "");
  await page.locator('[data-filter="done"]').click();
  check(tag + "filter Completed hides every not-started module", (await visible()) === 0);
  await page.locator('[data-filter="todo"]').click();
  check(tag + "filter Not started shows them again", (await visible()) === 10);
  await page.locator('[data-filter="all"]').click();

  await page.locator('.mod-card[data-mod="1"]').click();
  await page.waitForURL(/\/learn\/m1\/$/);
  check(tag + "a card opens its module page", (await page.locator("h1").first().textContent()).includes("Cyber hygiene"));
  check(tag + "module: banner, progress ring, Start and Assessments, outline and three tabs", (await page.locator(".band--mod .ring").count()) === 1 && (await page.locator(".hero-actions .btn").count()) === 2 && (await page.locator("[data-outline]").count()) === 1 && (await page.locator('[role="tab"]').count()) === 3);
  await page.locator("#tab-content").click();
  check(tag + "tab Course content shows the units", !(await page.locator("#panel-content").isHidden()) && (await page.locator("#panel-overview").isHidden()));
  await page.locator("#tab-assess").click();
  check(tag + "tab Assessments is shown", !(await page.locator("#panel-assess").isHidden()));
  await page.locator("#tab-overview").focus();
  await page.keyboard.press("ArrowRight");
  check(tag + "arrow keys move between tabs", (await page.locator("#tab-content").getAttribute("aria-selected")) === "true");
  await page.locator("#tab-overview").click();
  if (w < 1024) {
    check(tag + "outline is collapsed on small screens and opens with its button", await page.locator(".outline__body").isHidden());
    await page.locator("[data-outline-toggle]").click();
    check(tag + "outline opened", !(await page.locator(".outline__body").isHidden()));
  }
  await page.goto(base + "/learn/", { waitUntil: "networkidle" });
  await page.goto(base + "/learn/m1/#assess", { waitUntil: "networkidle" });
  check(tag + "the #assess link opens the Assessments tab", !(await page.locator("#panel-assess").isHidden()));
  await page.goto(base + "/learn/m1/", { waitUntil: "networkidle" });
  await page.locator(".unit-row").first().click();
  await page.waitForURL(/\/learn\/m1\/t\d\/$/);
  check(tag + "a topic opens the lesson player", (await page.locator(".outline [aria-current=page]").count()) === 1);
  await page.locator(".unit-nav a").last().click();
  check(tag + "Next goes to the next lesson", /\/learn\/m1\/(t2|handout|film)\/$/.test(page.url()), page.url());
  await page.goto(base + "/learn/m4/", { waitUntil: "networkidle" });
  const band = await page.locator(".band--mod").evaluate((e) => getComputedStyle(e).backgroundImage);
  check(tag + "module 4 uses its own colour in the banner", /gradient/.test(band));
  await page.goto(base + "/learn/m10/", { waitUntil: "networkidle" });
  check(tag + "the capstone page shows a clear not-available state", (await page.content()).includes("Not available yet"));
  await ctx.close();
}
check("no CSP violations or page errors", bad.length === 0);
if (bad.length) console.log([...new Set(bad)].join("\n"));
await browser.close();
process.exit(fails ? 1 : 0);
