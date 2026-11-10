// Screenshots and checks for pages, used by every PR from Stage 1.5 on (docs/build-stages.md).
//
//   cd tools && npm install            (once)
//   node screenshots.mjs --base http://localhost:8000 --out ../screenshots /accounts/login/ /register/
//   node screenshots.mjs --auth mentor@example.com:password --totp BASE32SECRET --out ../screenshots /mentor/
//
// For each path it saves <out>/<slug>-390.png and <slug>-1366.png, checks that nothing scrolls
// sideways at 360px and 1366px, and runs the axe accessibility check (WCAG 2.x A and AA).
// It exits with 1 if axe finds a serious or critical issue or a page scrolls sideways.
// --totp is the account's authenticator secret (local test accounts only), so staff and mentors can sign in.
// --lang hi|mr|gu sets the language cookie first. --browser chromium|msedge|chrome picks the browser
// (default: msedge if installed, so no browser download is needed on Windows).
import { chromium } from "playwright-core";
import AxeBuilder from "@axe-core/playwright";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  if (i === -1) return fallback;
  const [v] = args.splice(i, 2).slice(1);
  return v;
};
const base = opt("base", "http://localhost:8000");
const out = opt("out", "screenshots");
const auth = opt("auth", "");
const lang = opt("lang", "");
const totp = opt("totp", "");
const browserName = opt("browser", "msedge");
const paths = args.filter((a) => !a.startsWith("--"));
if (!paths.length) {
  console.error("Give at least one path, e.g. /accounts/login/");
  process.exit(2);
}
fs.mkdirSync(out, { recursive: true });

const slug = (p) => (p.replace(/^\/|\/$/g, "").replace(/[^a-z0-9]+/gi, "-") || "home") + (lang ? `-${lang}` : "");
const launchOptions = browserName === "chromium" ? {} : { channel: browserName };
const browser = await chromium.launch(launchOptions);
let failed = false;

// RFC 6238 one-time code (30 s, 6 digits, SHA-1), enough for local test accounts.
function totpCode(secret) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac("sha1", key).update(counter).digest();
  const o = h[h.length - 1] & 15;
  const n = ((h[o] & 127) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3];
  return String(n % 1000000).padStart(6, "0");
}

async function signIn(context) {
  const [email, password] = auth.split(/:(.+)/);
  const page = await context.newPage();
  await page.goto(`${base}/accounts/login/`);
  await page.fill('input[name="login"]', email);
  await page.fill('input[name="password"]', password);
  await Promise.all([page.waitForLoadState("load"), page.click('main button[type="submit"]')]);
  for (let attempt = 0; totp && page.url().includes("/2fa/") && attempt < 2; attempt++) {
    if (attempt) await page.waitForTimeout(30000 - (Date.now() % 30000) + 500); // a used code can't be replayed
    await page.fill('input[name="code"]', totpCode(totp));
    await Promise.all([page.waitForLoadState("load"), page.click('main button[type="submit"]')]);
  }
  if (page.url().includes("/accounts/")) throw new Error(`Sign-in failed, ended on ${page.url()}`);
  await page.close();
}

// Sign in once and reuse the session for both widths (a one-time code can't be used twice).
let storageState;
if (auth) {
  const loginContext = await browser.newContext();
  await signIn(loginContext);
  storageState = await loginContext.storageState();
  await loginContext.close();
}

for (const width of [390, 1366]) {
  const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, storageState });
  if (lang) await context.addCookies([{ name: "django_language", value: lang, url: base }]);
  for (const p of paths) {
    const page = await context.newPage();
    await page.goto(base + p, { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(out, `${slug(p)}-${width}.png`), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 0) {
      console.log(`FAIL  ${p} @${width}: scrolls sideways by ${overflow}px`);
      failed = true;
    }
    if (width === 390) {
      await page.setViewportSize({ width: 360, height: 800 });
      const narrow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (narrow > 0) {
        console.log(`FAIL  ${p} @360: scrolls sideways by ${narrow}px`);
        failed = true;
      }
      await page.setViewportSize({ width, height: 844 });
    }
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const bad = results.violations.filter((v) => ["serious", "critical"].includes(v.impact));
    const minor = results.violations.length - bad.length;
    console.log(`${bad.length ? "FAIL" : "ok  "}  ${p} @${width}: axe ${bad.length} serious/critical, ${minor} minor`);
    for (const v of bad) {
      failed = true;
      console.log(`      [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} element(s))`);
      for (const n of v.nodes.slice(0, 3)) console.log(`        ${n.target.join(" ")}`);
    }
    await page.close();
  }
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
