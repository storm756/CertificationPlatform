// Export the legacy interactive questions (setup/scorm/src/*/js/questions.js) to ONE private JSON
// file for `manage.py import_legacy_interactive`. Run once, locally:
//
//   node tools/legacy_export.mjs D:/csfr-lms/setup/scorm/src content-data/legacy/interactive.json
//
// The questions are private: the output goes to content-data/ (gitignored) and this script prints
// counts only, never question text. The legacy files are plain JavaScript assignments to
// window.CCFR_MODULE, so they are evaluated in an empty sandbox with no access to anything.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const [src, out] = process.argv.slice(2);
if (!src || !out) {
  console.error("usage: node tools/legacy_export.mjs <scorm/src dir> <output.json>");
  process.exit(2);
}
const modules = {};
for (const dir of fs.readdirSync(src).filter((d) => /^m\d\d$/.test(d)).sort()) {
  const file = path.join(src, dir, "js", "questions.js");
  if (!fs.existsSync(file)) continue;
  const sandbox = { window: {}, document: {} };
  sandbox.window.window = sandbox.window;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(file, "utf8"), sandbox, { timeout: 2000 });
  const mod = sandbox.window.CCFR_MODULE;
  const { questions, ...meta } = mod;
  modules[dir] = { meta: JSON.parse(JSON.stringify(meta)), questions: JSON.parse(JSON.stringify(questions)) };
}
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify({ modules }, null, 1));
const counts = Object.entries(modules).map(([k, v]) => `${k}:${v.questions.length}`).join(" ");
console.log(`exported ${Object.keys(modules).length} files (${counts}) to ${out}`);
