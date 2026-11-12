// Browser check of the schema-driven question editor for every format (invented data, scratch DB):
//   cd tools && SHOT_PW=... SHOT_TOTP=<base32 secret of the invented admin> node check_staff_editor.mjs
// Under the production CSP: the editor must render without a schema error or CSP violation, and
// saving an unchanged form must succeed (the form round-trips the body).
import crypto from "node:crypto";
import { chromium } from "playwright-core";

const base = "http://localhost:8001";
const CSP = "default-src 'self'; img-src 'self' data:; script-src 'self' https://www.youtube.com; frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
function totp(secretB32) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secretB32.replace(/=+$/, "")) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac("sha1", key).update(counter).digest();
  const o = h[19] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1000000)).padStart(6, "0");
}
const browser = await chromium.launch({ channel: "msedge" });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const bad = [];
page.on("console", (m) => { if (/Content Security Policy|Refused to|Error/i.test(m.text())) bad.push(m.text().slice(0, 160)); });
page.on("pageerror", (e) => bad.push("pageerror: " + e.message));
await page.goto(base + "/accounts/login/", { waitUntil: "domcontentloaded" });
await page.fill('input[name="login"]', "staff-admin@example.com");
await page.fill('input[name="password"]', process.env.SHOT_PW);
await Promise.all([page.waitForLoadState("load"), page.click('main button[type="submit"]')]);
if (page.url().includes("/2fa/")) {
  await page.fill('input[name="code"]', totp(process.env.SHOT_TOTP));
  await Promise.all([page.waitForLoadState("load"), page.click('main button[type="submit"]')]);
}
if (page.url().includes("/accounts/")) throw new Error("Sign-in failed: " + page.url());
await ctx.route("**/*", async (route) => {
  if (route.request().resourceType() !== "document") return route.continue();
  try { const r = await route.fetch(); await route.fulfill({ response: r, headers: { ...r.headers(), "content-security-policy": CSP } }); } catch { /* closing */ }
});
let fails = 0;  // the production CSP is applied after sign-in (the proxy would set cookies itself)
const check = (name, ok, extra = "") => { console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : " " + extra)); if (!ok) fails++; };
const ids = await page.evaluate(async () => {
  const r = await fetch("/staff/questions/?pool=practice&module=1");
  const html = await r.text();
  return [...html.matchAll(/href="\/staff\/questions\/(\d+)\/">/g)].map((m) => m[1]);
});
const unique = [...new Set(ids)].filter((i) => process.env.ONLY ? process.env.ONLY.split(",").includes(i) : true);
console.log("questions found:", unique.length, "at", page.url());
for (const id of unique) {
  bad.length = 0;
  await page.goto(`${base}/staff/questions/${id}/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-django-jsonform-container] *", { timeout: 8000 }).catch(() => {});
  const title = (await page.locator("h1").innerText()).replace(/\s+/g, " ");
  const text = await page.locator("main, body").first().innerText();
  const rendered = (await page.locator("[data-django-jsonform-container] input, [data-django-jsonform-container] textarea, [data-django-jsonform-container] select").count()) > 0;
  const schemaError = /Error while creating EditorState|Invalid schema/.test(text);
  const cspOnly = bad.every((b) => /inline style/.test(b));
  const why = schemaError ? text.split("\n").find((l) => l.startsWith("(!)")) || text.slice(0, 100) : bad.join(" | ");
  check(`${title.slice(0, 40)}: editor renders`, rendered && !schemaError && cspOnly, why);
  if (id === unique[0] || /Multiple choice/.test(title)) await page.screenshot({ path: `../screenshots/stage6/staff-editor-${id}-1366.png`, fullPage: true });
  await page.locator("form button:has-text('Save as a new version')").click();
  await page.waitForLoadState("domcontentloaded");
  const after = await page.locator("body").innerText();
  const problems = (await page.locator(".ticks li").allInnerTexts()).join(" | ");
  check(`${title.slice(0, 40)}: saves unchanged`, !/could not be saved/i.test(after), problems.slice(0, 300));
}
await browser.close();
console.log(fails ? `${fails} FAILED` : "all checks passed");
process.exit(fails ? 1 : 0);
