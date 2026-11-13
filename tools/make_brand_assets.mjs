// Makes the PNG brand assets from the SVG favicon and the two partner logos (Stage 9).
//   cd tools && node make_brand_assets.mjs [--browser msedge]
// Writes ../static/img/favicon-32.png, apple-touch-icon.png and social-preview.png (1200x630).
// The emblem slot is the text "CCFR" until CCFR's own emblem exists (D23): replace the text
// block below with the emblem then and run this again.
import { chromium } from "playwright-core";
import fs from "node:fs";

const img = (f) => `data:image/png;base64,${fs.readFileSync(`../static/img/${f}`).toString("base64")}`;
const svg = fs.readFileSync("../static/img/favicon.svg", "utf8");
const i = process.argv.indexOf("--browser");
const browser = await chromium.launch({ channel: i > -1 ? process.argv[i + 1] : "msedge" });

async function shot(html, width, height, out) {
  const page = await browser.newPage({ viewport: { width, height } });
  await page.setContent(html);
  await page.screenshot({ path: out, omitBackground: false });
  await page.close();
}

const icon = (size) =>
  `<body style="margin:0;background:#071a3d">${svg.replace("<svg ", `<svg width="${size}" height="${size}" `)}</body>`;
await shot(icon(32), 32, 32, "../static/img/favicon-32.png");
await shot(icon(180), 180, 180, "../static/img/apple-touch-icon.png");

const social = `<body style="margin:0;width:1200px;height:630px;background:linear-gradient(120deg,#071a3d 0 60%,#12366f);color:#fff;font-family:Arial,Helvetica,sans-serif;display:flex;flex-direction:column;justify-content:space-between;box-sizing:border-box;padding:64px">
  <div style="display:flex;gap:10px"><i style="width:70px;height:12px;background:#19e1d2"></i><i style="width:50px;height:12px;background:#f2b705"></i><i style="width:30px;height:12px;background:#c75b3f"></i></div>
  <div>
    <div style="font-size:30px;letter-spacing:6px;color:#2fdcf5;font-weight:700">COMMUNITY CYBER FIRST RESPONDER</div>
    <div style="font-size:150px;font-weight:800;line-height:1.05;margin:10px 0">CCFR</div>
    <div style="font-size:38px;color:#d3e1f7">Learn, practise, assess, certify.</div>
  </div>
  <div style="display:flex;align-items:center;gap:28px;background:#fbf6e9;border-radius:20px;padding:18px 28px;width:max-content">
    <img src="${img("shah-anchor-logo.png")}" height="84">
    <span style="width:3px;height:70px;background:#c9bfa4"></span>
    <img src="${img("cyberpeace-logo.png")}" height="84">
  </div></body>`;
await shot(social, 1200, 630, "../static/img/social-preview.png");
await browser.close();
console.log("brand assets written");
