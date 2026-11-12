// The final flow for the invented released-set learner (after seed_final.py): start, answer, submit,
// result bands, then the cooldown on the progress and final pages. Scratch DB only.
import fs from "node:fs";
import { chromium } from "playwright-core";

const base = "http://localhost:8001";
const out = "../screenshots/exam-sets";
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: "msedge" });
let fails = 0;
const check = (name, ok) => { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; };
const text = async (page) => (await page.locator("body").innerText()).replace(/\s+/g, " ");

for (const [w, h] of [[390, 844], [1366, 900]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.goto(base + "/accounts/login/");
  await page.fill("input[type=email]", "shots-set@example.com");
  await page.fill("input[type=password]", process.env.SHOT_PW);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForLoadState("domcontentloaded");
  await page.goto(base + "/exam/final/");
  const open = await Promise.resolve(await text(page));
  if (w === 1366 && /Before you start/.test(open)) {
    await page.screenshot({ path: `${out}/set-final-intro-unlocked-${w}.png`, fullPage: true });
    check("final intro: about 60 minutes guidance and no time limit", /about 60 minutes/.test(open) && /no time limit/.test(open));
    await page.locator("form[action*='/start/'] button[type=submit]").click();
    await page.waitForLoadState("domcontentloaded");
    check("final shows an elapsed timer", /\d+:\d\d/.test(await text(page)) || (await page.locator("[data-timer], .timer").count()) > 0);
    await page.screenshot({ path: `${out}/set-final-question-${w}.png`, fullPage: true });
    for (let i = 0; i < 6; i++) {
      await page.locator("input[name=choice]").first().check();
      await page.waitForTimeout(500);
      const next = page.locator("a:has-text('Next'), button:has-text('Next')");
      if (await next.count()) { await next.first().click(); await page.waitForLoadState("domcontentloaded"); }
    }
    const pk = page.url().match(/attempt\/(\d+)/)[1];
    await page.goto(`${base}/attempt/${pk}/review/`);
    await page.locator("form[action*='/submit/'] button[type=submit]").click();
    const confirm = page.locator("dialog button:has-text('Submit'), [role=dialog] button:has-text('Submit')");
    if (await confirm.count()) await confirm.first().click();
    await page.waitForURL(/result/, { timeout: 15000 });
    const result = await text(page);
    await page.screenshot({ path: `${out}/set-final-result-${w}.png`, fullPage: true });
    check("final result shows the score and module bands, no answers", /%/.test(result) && /Module 1/.test(result) && !/Invented option|Invented hint/.test(result));
  }
  await page.goto(base + "/start/");
  const dash = await text(page);
  await page.screenshot({ path: `${out}/set-progress-cooldown-${w}.png`, fullPage: true });
  check(`progress ${w}px shows the cooldown, not a start button`, /You can try again after/.test(dash) && !/Try the final again|Start the final/.test(dash));
  await page.goto(base + "/exam/final/");
  const intro = await text(page);
  await page.screenshot({ path: `${out}/set-final-intro-cooldown-${w}.png`, fullPage: true });
  check(`final page ${w}px shows the cooldown and no start button`, /Please wait before your next try/.test(intro) && (await page.locator("form[action*='/start/']").count()) === 0);
  check(`no sideways scroll ${w}px`, await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await ctx.close();
}
await browser.close();
console.log(fails ? `${fails} FAILED` : "all checks passed");
process.exit(fails ? 1 : 0);
