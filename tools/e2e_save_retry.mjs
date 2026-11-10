// Browser check: a failed answer save is kept and retried for its own question (Stage 3 review fix).
//
//   docker compose -f deploy/compose.dev.yml up -d db web
//   cd tools && node e2e_save_retry.mjs [--base http://localhost:8000]
//
// Before every scenario it re-runs tools/seed_e2e.py in the dev web container (fresh invented attempts, nothing
// answered). Set E2E_COMPOSE if your compose command differs (default: docker compose -f ../deploy/compose.dev.yml).
// It uses invented data only. Pages run under the production CSP. For each scenario it checks what the
// SERVER holds afterwards (by loading the question again), never only what the page shows.
import { execSync } from "node:child_process";
import { chromium } from "playwright-core";

const args = process.argv.slice(2);
const baseAt = args.indexOf("--base");
const base = baseAt >= 0 ? args.splice(baseAt, 2)[1] : "http://localhost:8000";
const compose = process.env.E2E_COMPOSE ?? "docker compose -f ../deploy/compose.dev.yml";
const seedFile = new URL("./seed_e2e.py", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
function reseed() {
  const out = execSync(`${compose} exec -T web python manage.py shell < "${seedFile}"`, { encoding: "utf8", shell: true, stdio: ["ignore", "pipe", "inherit"] });
  return JSON.parse(out.trim().split(/\r?\n/).filter((l) => l.startsWith("{")).pop());
}
let seed = reseed();
const CSP = "default-src 'self'; img-src 'self' data:; frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";

const browser = await chromium.launch({ channel: "msedge" });
const bad = []; let fails = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : ` ${extra}`)); if (!ok) fails++; };
const ANSWER = "**/attempt/*/answer/";

async function fresh(viewport) {
  seed = reseed();  // new attempts, nothing answered
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
const open = (page, attempt, n) => page.goto(`${base}/attempt/${attempt}/q/${n}/`, { waitUntil: "networkidle" });
const position = (page) => page.locator("#answer-form input[name=position]").inputValue();
const waitPill = (page, state, ms = 15000) => page.waitForFunction((s) => document.getElementById("save-status")?.dataset.state === s, state, { timeout: ms });
const next = (page) => page.locator(".qnav a.btn-primary").click();
const onQuestion = (page, n) => page.waitForFunction((x) => document.querySelector("#answer-form input[name=position]")?.value === String(x), n, { timeout: 8000 });

// What the server holds for a question: the saved answer, read from a fresh page load.
async function serverAnswer(page, attempt, n) {
  const html = await (await page.request.get(`${base}/attempt/${attempt}/q/${n}/`)).text();
  const mcq = /<input type="radio" name="choice" value="([^"]+)" checked/.exec(html);
  if (mcq) return { choice: mcq[1] };
  const data = /data-q="([^"]*)"/.exec(html);
  if (!data) return {};
  const q = JSON.parse(data[1].replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">"));
  return q.response ?? {};
}
const hasAnswer = (r) => Object.values(r).some((v) => (Array.isArray(v) ? v.length : v && typeof v === "object" ? Object.keys(v).length : v === true || (typeof v === "string" && v)));

// Make an answer on whatever question is shown (a radio option, an engine choice, or a tick).
async function answerHere(page) {
  if (await page.locator(".engine").count()) {
    if (await page.locator(".engine [role=radio]").count()) { await page.locator(".engine [role=radio]").nth(1).click(); return; }
    if (await page.locator(".engine .tri__btn").count()) { await page.locator(".engine .tri__btn").nth(2).click(); return; }
    await page.locator(".engine .eng-tile").first().click(); await page.locator(".engine .eng-done").click(); return;
  }
  await page.locator(".opt").nth(1).click();
}

for (const viewport of [{ width: 390, height: 844 }, { width: 1366, height: 900 }]) {
  const tag = `${viewport.width}px `;
  for (const [kind, key] of [["multiple choice", "mcq"], ["interactive", "interactive"]]) {
    const label = `${tag}${kind}: `;

    // --- 1. the save fails, the learner clicks Next, the connection comes back -------------------
    {
      const { ctx, page } = await fresh(viewport);
      const attempt = seed[key];
      await open(page, attempt, 1);
      const posts = [];
      page.on("request", (r) => { if (r.method() === "POST" && /\/answer\/$/.test(r.url())) posts.push({ at: Date.now(), body: r.postData() ?? "", url: r.url() }); });
      await page.route(ANSWER, (route) => route.abort("internetdisconnected"));
      await answerHere(page);
      await waitPill(page, "offline");
      check(label + "a failed save shows Offline, never Saved", (await pill(page)) === "offline");
      await next(page);
      await onQuestion(page, 2);
      check(label + "after Next (question 2) the pill still says the answer is not saved", (await pill(page)) === "offline");
      await answerHere(page);  // question 2 fails as well
      await page.waitForTimeout(400);
      const recoveredAt = Date.now();
      await page.unroute(ANSWER);
      await waitPill(page, "saved", 20000);
      const one = await serverAnswer(page, attempt, 1), two = await serverAnswer(page, attempt, 2);
      check(label + "question 1's answer reached the server after recovery", hasAnswer(one), JSON.stringify(one));
      check(label + "question 2's own answer was saved too", hasAnswer(two), JSON.stringify(two));
      const after = posts.filter((p) => p.at >= recoveredAt);
      const positions = after.map((p) => new URLSearchParams(p.body).get("position"));
      check(label + "the retry for question 1 was sent for question 1", positions.includes("1"), JSON.stringify(positions));
      check(label + "no retry for question 1 was sent as question 2", after.every((p) => { const q = new URLSearchParams(p.body); return q.get("position") !== "2" || !q.get("choice") || q.get("choice") !== new URLSearchParams(after.find((x) => new URLSearchParams(x.body).get("position") === "1")?.body ?? "").get("choice"); }));
      const states = await page.evaluate(() => window.__pill);
      const firstOffline = states.find((s) => s.state === "offline");
      const savedWhileFailing = states.filter((s) => s.state === "saved" && firstOffline && s.at > firstOffline.at && s.at < recoveredAt);
      check(label + "Saved was never shown while the server had not accepted the answer", savedWhileFailing.length === 0, JSON.stringify(states));
      await ctx.close();
    }

    // --- 2. Next clicked at once, before the save has even started -------------------------------
    {
      const { ctx, page } = await fresh(viewport);
      const attempt = seed[key];
      await open(page, attempt, 1);
      await answerHere(page);  // no waiting: the very next action is Next
      await next(page);
      await onQuestion(page, 2);
      await waitPill(page, "saved");
      const one = await serverAnswer(page, attempt, 1);
      check(label + "a quick Next still saves question 1", hasAnswer(one), JSON.stringify(one));
      await ctx.close();
    }

    // --- 3. the server refuses the answer: it must not say Saved ----------------------------------
    {
      const { ctx, page } = await fresh(viewport);
      const attempt = seed[key];
      await open(page, attempt, 1);
      await page.route(ANSWER, (route) => route.fulfill({ status: 400, body: "" }));
      await answerHere(page);
      await waitPill(page, "error");
      check(label + "a refused answer shows Not saved, not Saved", (await page.locator("#save-status [data-pill-text]").textContent()).trim() === "Not saved");
      await ctx.close();
    }
  }

  // --- 5. a chat reply: the next message appears only once the reply has been saved ---------------------
  {
    const { ctx, page } = await fresh(viewport);
    const chat = seed.interactive_count;  // the chat is the last question of the interactive part
    await open(page, seed.interactive, chat);
    const before = await page.locator(".engine .eng-bub--them").count();
    await page.locator(".engine .eng-reply").first().click();
    await page.waitForFunction((n) => document.querySelectorAll(".engine .eng-bub--them").length > n, before, { timeout: 10000 }).catch(() => {});
    check(`${tag}chat: the next step appears after the reply is saved`, (await page.locator(".engine .eng-bub--them").count()) === before + 1);
    const saved = await serverAnswer(page, seed.interactive, chat);
    check(`${tag}chat: the reply is on the server`, hasAnswer(saved), JSON.stringify(saved));
    await ctx.close();
  }

  // --- 4. Review and submit clicked straight after answering the last question -----------------------
  {
    const { ctx, page } = await fresh(viewport);
    const last = seed.mcq_count;
    await open(page, seed.mcq, last);
    await page.locator(".opt").nth(1).click();
    await page.locator(".qnav a.btn-primary").click();  // "Review and submit", at once
    await page.waitForURL(/\/review\//, { timeout: 12000 });
    const html = await page.content();
    const saved = await serverAnswer(page, seed.mcq, last);
    check(`${tag}Review and submit waits for the last answer to be saved`, hasAnswer(saved) && /answered/i.test(html), JSON.stringify(saved));
    await ctx.close();
  }
}

check("no CSP violations or page errors", bad.length === 0);
if (bad.length) console.log([...new Set(bad)].join("\n"));
await browser.close();
process.exit(fails ? 1 : 0);
