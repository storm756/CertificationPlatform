// Build the interactive engine: engine/src/index.ts -> static/js/engine.js (one file, no framework).
//   cd tools && npm install && node build_engine.mjs        (add --check to only type-check)
// The bundle is committed (the Docker image has no Node), so run this and commit the result
// whenever engine/src changes.
import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const tsc = path.join(here, "node_modules", "typescript", "bin", "tsc");
execFileSync(process.execPath, [tsc, "-p", path.join(root, "engine", "tsconfig.json")], { stdio: "inherit" });
console.log("types ok");
if (!process.argv.includes("--check")) {
  await build({
    entryPoints: [path.join(root, "engine", "src", "index.ts")],
    outfile: path.join(root, "static", "js", "engine.js"),
    bundle: true,
    format: "iife",
    target: "es2019",
    legalComments: "none",
    charset: "utf8",
    banner: { js: "/* CCFR interactive engine. Built from engine/src with tools/build_engine.mjs; do not edit. */" },
  });
  console.log("built static/js/engine.js");
}
