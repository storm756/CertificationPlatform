// Side-by-side visual check against the original standalone prototype (a local server, default :4180).
//   cd tools && node compare_pages.mjs [--proto http://localhost:4180] [--site http://localhost:8000] [--out ../screenshots/stage4-compare]
// It saves a full-page screenshot of each Django page and of its prototype page at 390, 1366 and 1920px
// wide, named <name>-<width>-proto.png and <name>-<width>-django.png. (The prototype is the visual
// reference only; it is not part of the repository's runtime.)
import fs from "node:fs";
import { chromium } from "playwright-core";

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i >= 0 ? process.argv[i + 1] : d; };
const proto = arg("proto", "http://localhost:4180");
const site = arg("site", "http://localhost:8000");
const out = arg("out", "../screenshots/stage4-compare");
fs.mkdirSync(out, { recursive: true });
const pairs = [
  ["catalogue", "/modules.html", "/learn/"],
  ["module-1", "/module.html?m=1", "/learn/m1/"],
  ["module-4", "/module.html?m=4", "/learn/m4/"],
  ["lesson", "/unit.html?m=1&u=t1", "/learn/m1/t1/"],
];
const widths = [[390, 844], [1366, 900], [1920, 1080]];
const browser = await chromium.launch({ channel: "msedge" });
for (const [w, h] of widths) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  for (const [name, p, d] of pairs) {
    await page.goto(proto + p, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3500);
    await page.screenshot({ path: `${out}/${name}-${w}-proto.png`, fullPage: true, animations: "disabled", timeout: 90000 });
    await page.goto(site + d, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${out}/${name}-${w}-django.png`, fullPage: true, animations: "disabled", timeout: 90000 });
    console.log("saved", name, w);
  }
  await ctx.close();
}
await browser.close();
