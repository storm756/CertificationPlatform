// Screenshots and axe for saved HTML files (pages that need DEBUG off, like the 404 and 500 pages).
//   node shot_files.mjs ../screenshots/stage-9/_404-en.html ...   (files hold <base href> to the running site)
import { chromium } from "playwright-core";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
import { pathToFileURL } from "node:url";

const browser = await chromium.launch({ channel: "msedge" });
let failed = false;
for (const file of process.argv.slice(2)) {
  for (const width of [360, 390, 1366]) {
    const ctx = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(pathToFileURL(path.resolve(file)).href, { waitUntil: "networkidle" });
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const bad = axe.violations.filter((v) => ["serious", "critical"].includes(v.impact));
    if (width !== 360) await page.screenshot({ path: file.replace(".html", `-${width}.png`), fullPage: true });
    const ok = over <= 0 && !bad.length;
    failed ||= !ok;
    console.log(`${ok ? "ok  " : "FAIL"} ${path.basename(file)} @${width}: overflow ${over}px, axe ${bad.length} serious`);
    await ctx.close();
  }
}
await browser.close();
process.exit(failed ? 1 : 0);
