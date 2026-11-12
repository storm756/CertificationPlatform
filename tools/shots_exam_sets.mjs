// Screenshots + checks of the exam-set learner pages, invented data only (scratch DB csfr_shots).
//   cd tools && SHOT_PW=... node shots_exam_sets.mjs [--base http://localhost:8001]
import fs from "node:fs";
import { chromium } from "playwright-core";

const args = process.argv.slice(2);
const at = args.indexOf("--base");
const base = at >= 0 ? args[at + 1] : "http://localhost:8001";
const out = "../screenshots/exam-sets";
fs.mkdirSync(out, { recursive: true });
const PW = process.env.SHOT_PW;
const browser = await chromium.launch({ channel: "msedge" });
let fails = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : " " + extra)); if (!ok) fails++; };
const sizes = [[390, 844], [1366, 900]];

async function login(page, email) {
  await page.goto(base + "/accounts/login/");
  await page.fill("input[type=email]", email);
  await page.fill("input[type=password]", PW);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForLoadState("domcontentloaded");
}
const text = async (page) => (await page.locator("body").innerText()).replace(/\s+/g, " ");
const shot = (page, name, w) => page.screenshot({ path: `${out}/${name}-${w}.png`, fullPage: true, animations: "disabled" });
const noSideways = async (page, name) => check(name + " no sideways scroll", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));

async function pages(email, label, w, h, tag) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await login(page, email);
  const seen = {};
  for (const [name, url] of [["catalogue", "/learn/"], ["progress", "/start/"], ["pretest-intro", "/exam/pretest/"], ["final-intro", "/exam/final/"]]) {
    await page.goto(base + url);
    await page.waitForLoadState("domcontentloaded");
    seen[name] = await text(page);
    await shot(page, `${label}-${tag}${name}`, w);
    await noSideways(page, `${label} ${name} ${w}px`);
  }
  await ctx.close();
  return seen;
}

// 1. a learner whose batch has no exam set, 2. a learner whose batch has a released set
for (const [w, h] of sizes) {
  const none = await pages("shots-noset@example.com", "noset", w, h, "");
  check(`no set ${w}px: catalogue still says coming soon`, /Coming soon\. See what you know/.test(none.catalogue));
  check(`no set ${w}px: progress explains the pre-test is not available`, /Pre-test not available yet/.test(none.progress) && /has not been given a final exam set/.test(none.progress));
  check(`no set ${w}px: progress does not send them to the pre-test`, !/Take the pre-test|Welcome\. Start with the pre-test/.test(none.progress));
  check(`no set ${w}px: pre-test page says coming soon`, /Coming soon/.test(none["pretest-intro"]) && !/Before you start/.test(none["pretest-intro"]));
  const has = await pages("shots-set@example.com", "set", w, h, "before-");
  check(`released set ${w}px: catalogue no longer says coming soon for the exams`, !/Coming soon\. See what you know|Coming soon\. The final counts/.test(has.catalogue));
  check(`released set ${w}px: progress offers the pre-test`, /Welcome\. Start with the pre-test/.test(has.progress) && /Take the pre-test/.test(has.progress));
  check(`released set ${w}px: pre-test intro can start`, /Before you start/.test(has["pretest-intro"]));
  check(`released set ${w}px: final stays locked with reasons`, /Locked/.test(has.progress) && /Do the pre-test first/.test(has["final-intro"]));
}

// 3. the pre-test flow for the released-set learner (1366px), then the progress and final pages again
{
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await login(page, "shots-set@example.com");
  await page.goto(base + "/exam/pretest/");
  await page.locator("form[action*='/start/'] button[type=submit]").click();
  await page.waitForLoadState("domcontentloaded");
  await shot(page, "set-pretest-question", 1366);
  const body = await text(page);
  check("pre-test question page has no hint or answer key", !/Invented hint/.test(body) && !(await page.content()).includes('"correct"'));
  check("pre-test shows a count-up timer", /\d+:\d\d/.test(body) || (await page.locator("[data-timer], .timer").count()) > 0);
  for (let i = 0; i < 4; i++) {
    await page.locator("input[name=choice]").first().check();
    await page.waitForTimeout(500);
    const next = page.locator("a:has-text('Next'), button:has-text('Next')");
    if (await next.count()) { await next.first().click(); await page.waitForLoadState("domcontentloaded"); }
  }
  const pk = page.url().match(/attempt\/(\d+)/)[1];
  await page.goto(`${base}/attempt/${pk}/review/`);
  await page.waitForLoadState("domcontentloaded");
  await shot(page, "set-pretest-review", 1366);
  await page.locator("form[action*='/submit/'] button[type=submit]").click();
  const confirm = page.locator("dialog button:has-text('Submit'), [role=dialog] button:has-text('Submit')");
  if (await confirm.count()) await confirm.first().click();
  await page.waitForURL(/result/, { timeout: 15000 });
  const result = await text(page);
  await shot(page, "set-pretest-result", 1366);
  check("pre-test result shows the score and no answers", /%/.test(result) && /Pre-test done/.test(result) && !/Invented hint|Invented option/.test(result));
  await ctx.close();
}
for (const [w, h] of sizes) {
  const after = await pages("shots-set@example.com", "set", w, h, "after-");
  check(`after the pre-test ${w}px: progress no longer offers it`, !/Take the pre-test/.test(after.progress));
  check(`after the pre-test ${w}px: final still locked until the module parts are done`, /Locked/.test(after.progress) && /every question answered/.test(after["final-intro"]));
  check(`after the pre-test ${w}px: pre-test cannot be restarted`, /already done the pre-test/.test(after["pretest-intro"]));
}
await browser.close();
console.log(fails ? `${fails} FAILED` : "all checks passed");
process.exit(fails ? 1 : 0);
