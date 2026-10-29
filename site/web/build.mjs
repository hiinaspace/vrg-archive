// Bundles the search page (esbuild) into <out>/index.html + <out>/assets/. `--test` bundles and runs test/*.test.ts under node.
import { build } from "esbuild";
import { readFileSync, writeFileSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

const args = process.argv.slice(2);
const arg = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };

if (args.includes("--test")) {
  rmSync(".test", { recursive: true, force: true });
  const files = readdirSync("test").filter((f) => f.endsWith(".test.ts")).map((f) => "test/" + f);
  await build({ entryPoints: files, bundle: true, platform: "node", format: "esm", outdir: ".test", logLevel: "warning", target: "node22", outExtension: { ".js": ".mjs" } });
  const r = spawnSync("node", ["--test", ...readdirSync(".test").filter((f) => f.endsWith(".mjs")).map((f) => ".test/" + f)], { stdio: "inherit" });
  process.exit(r.status ?? 1);
}

if (args.includes("--run")) { // bundle one TS entry for node and run it: build.mjs --run test/x.ts [args...]
  const i = args.indexOf("--run"), file = args[i + 1];
  mkdirSync(".test", { recursive: true });
  const outfile = ".test/run-" + file.split("/").pop().replace(/\.ts$/, ".mjs");
  await build({ entryPoints: [file], bundle: true, platform: "node", format: "esm", outfile, logLevel: "warning", target: "node22" });
  const r = spawnSync("node", [outfile, ...args.slice(i + 2)], { stdio: "inherit" });
  process.exit(r.status ?? 1);
}

const out = arg("--out") ?? "../dist";
mkdirSync(out + "/assets", { recursive: true });
const res = await build({
  entryPoints: { app: "src/main.ts" }, bundle: true, minify: true, format: "esm", target: "es2022", outdir: out + "/assets",
  entryNames: "[name].[hash]", metafile: true, logLevel: "warning", sourcemap: false,
});
const files = Object.keys(res.metafile.outputs).map((p) => p.split("/").pop());
const js = files.find((f) => f.endsWith(".js")), css = files.find((f) => f.endsWith(".css"));
let html = readFileSync("src/index.html", "utf8");
html = html.replace("__JS__", "assets/" + js).replace("__CSS__", css ? `<link rel="stylesheet" href="assets/${css}">` : "");
writeFileSync(out + "/index.html", html);
console.log("web bundle:", js, css, createHash("sha1").update(html).digest("hex").slice(0, 8));
