// Browser check: a failed answer save stays tied to its own question and is retried for it (Stage 2).
//
//   docker compose -f deploy/compose.dev.yml up -d db web
//   cd tools && node e2e_save_retry.mjs [--base http://localhost:8000]
//
// Before every scenario it re-runs tools/seed_e2e.py in the dev web container (invented data, a fresh
// attempt, nothing answered). Set E2E_COMPOSE if your compose command differs. Every check reads what the
// SERVER holds by loading the question again, never only what the page shows. Pages run under the
// production CSP.
import { execSync } from "node:child_process";
import { chromium } from "playwright-core";

const args = process.argv.slice(2);
const at = args.indexOf("--base");
const base = at >= 0 ? args[at + 1] : "http://localhost:8000";
const compose = process.env.E2E_COMPOSE ?? "docker compose -f ../deploy/compose.dev.yml";
const seedFile = new URL("./seed_e2e.py", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
function reseed() {
  const out = execSync(`${compose} exec -T web python manage.py shell < "${seedFile}"`, { encoding: "utf8", shell: true, stdio: ["ignore", "pipe", "inherit"] });
  return JSON.parse(out.trim().split(/\r?\n/).filter((l) => l.startsWith("{")).pop());
}
let seed = reseed();
const CSP = "default-src 'self'; img-src 'self' data:; frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
const ANSWER = "**/attempt/*/answer/";
const browser = await chromium.launch({ channel: "msedge" });
const bad = [];
let fails = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : ` ${extra}`)); if (!ok) fails++; };

async function fresh(viewport) {
  seed = reseed();
  const ctx = await browser.newContext({ viewport });
  await ctx.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    try { const r = await route.fetch(); await route.fulfill({ response: r, headers: { ...r.headers(), "content-security-policy": CSP } }); } catch { /* closing */ }
  });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) bad.push(m.text().slice(0, 140)); });
  page.on("pageerror", (e) => bad.push("pageerror: " + e.message));
  await page.addInitScript(() => {  // every state the save pill goes through, with the time
    window.__pill = [];
    const note = () => { const el = document.getElementById("save-status"); const s = el && el.dataset.state; const last = window.__pill[window.__pill.length - 1]; if (s && (!last || last.state !== s)) window.__pill.push({ state: s, at: Date.now() }); };
    new MutationObserver(note).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-state"] });
    document.addEventListener("DOMContentLoaded", note);
  });
  await page.goto(base + "/accounts/login/");
  await page.fill("input[name=login]", seed.email);
  await page.fill("input[name=password]", seed.password);
  await Promise.all([page.waitForLoadState("load"), page.click("main button[type=submit]")]);
  return { ctx, page };
}
const pill = (page) => page.locator("#save-status").getAttribute("data-state");
const open = (page, n) => page.goto(`${base}/attempt/${seed.attempt}/q/${n}/`, { waitUntil: "networkidle" });
const waitPill = (page, state, ms = 15000) => page.waitForFunction((s) => document.getElementById("save-status")?.dataset.state === s, state, { timeout: ms });
const next = (page) => page.locator(".qnav a.btn-primary").click();
const onQuestion = (page, n) => page.waitForFunction((x) => document.querySelector("#answer-form input[name=position]")?.value === String(x), n, { timeout: 8000 });
const choose = (page, i) => page.locator(".opt").nth(i).click();

// What the server holds for a question: the saved choice, read from a fresh page load.
async function serverChoice(page, n) {
  const html = await (await page.request.get(`${base}/attempt/${seed.attempt}/q/${n}/`)).text();
  const m = /<input type="radio" name="choice" value="([^"]+)" checked/.exec(html);
  return m ? m[1] : null;
}
const checked = (page) => page.locator(".opt input:checked").inputValue().catch(() => null);

for (const viewport of [{ width: 390, height: 844 }, { width: 1366, height: 900 }]) {
  const tag = `${viewport.width}px `;

  // --- 1. Question 1's save fails, the learner clicks Next, the connection comes back -------------
  {
    const { ctx, page } = await fresh(viewport);
    await open(page, 1);
    const posts = [];
    page.on("request", (r) => { if (r.method() === "POST" && /\/answer\/$/.test(r.url())) posts.push({ at: Date.now(), body: new URLSearchParams(r.postData() ?? "") }); });
    await page.route(ANSWER, (route) => route.abort("internetdisconnected"));
    await choose(page, 1);
    const q1Choice = await checked(page);
    await waitPill(page, "offline");
    check(tag + "a failed save shows Offline, never Saved", (await pill(page)) === "offline");
    await next(page);
    await onQuestion(page, 2);
    check(tag + "on question 2 the pill still says the answer is not saved", (await pill(page)) === "offline");
    await choose(page, 2);  // question 2 fails as well
    const q2Choice = await checked(page);
    await page.waitForTimeout(400);
    const recoveredAt = Date.now();
    await page.unroute(ANSWER);
    await waitPill(page, "saved", 20000);
    check(tag + "question 1's own answer reached the server", (await serverChoice(page, 1)) === q1Choice, String(await serverChoice(page, 1)));
    check(tag + "question 2's answer is its own, not question 1's", (await serverChoice(page, 2)) === q2Choice && q1Choice !== q2Choice);
    const after = posts.filter((p) => p.at >= recoveredAt);
    const sent1 = after.find((p) => p.body.get("position") === "1");
    check(tag + "the retry for question 1 was sent as question 1, with its own choice", !!sent1 && sent1.body.get("choice") === q1Choice, JSON.stringify(after.map((p) => [p.body.get("position"), p.body.get("choice")])));
    check(tag + "no retry sent question 1's choice as question 2", after.every((p) => p.body.get("position") !== "2" || p.body.get("choice") === q2Choice));
    const states = await page.evaluate(() => window.__pill);
    const firstOffline = states.find((s) => s.state === "offline");
    const savedTooEarly = states.filter((s) => s.state === "saved" && firstOffline && s.at > firstOffline.at && s.at < recoveredAt);
    check(tag + "Saved was never shown while the server had not accepted the answers", savedTooEarly.length === 0, JSON.stringify(states));
    await ctx.close();
  }

  // --- 2. a quick Next, before the save has even started ---------------------------------------------
  {
    const { ctx, page } = await fresh(viewport);
    await open(page, 1);
    await choose(page, 1);
    const want = await checked(page);
    await next(page);
    await onQuestion(page, 2);
    await waitPill(page, "saved");
    check(tag + "a quick Next still saves question 1", (await serverChoice(page, 1)) === want);
    await ctx.close();
  }

  // --- 3. the server refuses the answer: Not saved, never Saved --------------------------------------
  {
    const { ctx, page } = await fresh(viewport);
    await open(page, 1);
    await page.route(ANSWER, (route) => route.fulfill({ status: 400, body: "" }));
    await choose(page, 1);
    await waitPill(page, "error");
    check(tag + "a refused answer shows Not saved", (await page.locator("#save-status [data-pill-text]").textContent()).trim() === "Not saved");
    check(tag + "a refused answer is not on the server", (await serverChoice(page, 1)) === null);
    await page.unroute(ANSWER);
    await ctx.close();
  }

  // --- 4. a refused answer, then "Review and submit": the learner stays on the quiz -------------------
  {
    const { ctx, page } = await fresh(viewport);
    await open(page, seed.count);
    const quiz = page.url();
    await page.route(ANSWER, (route) => route.fulfill({ status: 400, body: "" }));
    await choose(page, 1);
    await waitPill(page, "error");
    await page.locator(".qnav a.btn-primary").click();  // "Review and submit"
    await page.waitForTimeout(2500);
    check(tag + "Review is not opened while an answer was refused", page.url() === quiz && !/\/review\//.test(page.url()), page.url());
    await ctx.close();
  }

  // --- 5. Review and submit straight after the last answer waits for it to be saved -------------------
  {
    const { ctx, page } = await fresh(viewport);
    await open(page, seed.count);
    await choose(page, 1);
    const want = await checked(page);
    await page.locator(".qnav a.btn-primary").click();
    await page.waitForURL(/\/review\//, { timeout: 12000 });
    check(tag + "Review waits for the last answer to be saved", (await serverChoice(page, seed.count)) === want);
    await ctx.close();
  }

  // --- 6. closing the tab with an unsaved answer: the browser asks first -------------------------------
  {
    const { ctx, page } = await fresh(viewport);
    await open(page, 1);
    await page.route(ANSWER, (route) => route.abort("internetdisconnected"));
    await choose(page, 1);
    await waitPill(page, "offline");
    let asked = false;
    page.on("dialog", async (d) => { if (d.type() === "beforeunload") asked = true; await d.dismiss(); });
    await page.close({ runBeforeUnload: true });
    await new Promise((r) => setTimeout(r, 800));
    check(tag + "leaving with an unsaved answer asks the learner first", asked);
    await ctx.close();
  }
}

check("no CSP violations or page errors", bad.length === 0);
if (bad.length) console.log([...new Set(bad)].join("\n"));
await browser.close();
process.exit(fails ? 1 : 0);
