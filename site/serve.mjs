#!/usr/bin/env node
// Static file server with HTTP Range support (like the Cloudflare custom domain) and gzip for text types.
// usage: node serve.mjs <dist> [port=8796] [host=0.0.0.0]
import { createServer } from "node:http";
import { createReadStream, statSync, existsSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { readFileSync } from "node:fs";
import { join, extname, normalize } from "node:path";

const root = process.argv[2];
const port = +(process.argv[3] ?? 8796), host = process.argv[4] ?? "0.0.0.0";
if (!root) { console.error("usage: serve.mjs <dist> [port] [host]"); process.exit(1); }
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".txt": "text/plain; charset=utf-8", ".xml": "application/xml", ".bin": "application/octet-stream" };
const TEXT = new Set([".html", ".js", ".css", ".json", ".txt", ".xml"]);
export const log = [];

const server = createServer((req, res) => {
  try {
    let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let f = normalize(join(root, p));
    if (!f.startsWith(normalize(root))) { res.writeHead(403).end(); return; }
    if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
    if (!existsSync(f)) { res.writeHead(404, { "content-type": "text/plain" }).end("not found"); return; }
    const st = statSync(f), ext = extname(f);
    const h = { "content-type": TYPES[ext] ?? "application/octet-stream", "accept-ranges": "bytes", "cache-control": "no-cache", "access-control-allow-origin": "*" };
    const range = req.headers.range && /^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
    if (range) {
      let a = range[1] === "" ? st.size - +range[2] : +range[1], b = range[1] === "" || range[2] === "" ? st.size - 1 : Math.min(+range[2], st.size - 1);
      if (a > b || a >= st.size) { res.writeHead(416, { "content-range": `bytes */${st.size}` }).end(); return; }
      res.writeHead(206, { ...h, "content-range": `bytes ${a}-${b}/${st.size}`, "content-length": b - a + 1 });
      createReadStream(f, { start: a, end: b }).pipe(res);
      return;
    }
    if (TEXT.has(ext) && /\bgzip\b/.test(req.headers["accept-encoding"] ?? "")) {
      const z = gzipSync(readFileSync(f), { level: 6 });
      res.writeHead(200, { ...h, "content-encoding": "gzip", "content-length": z.length, vary: "accept-encoding" }).end(z);
      return;
    }
    res.writeHead(200, { ...h, "content-length": st.size });
    createReadStream(f).pipe(res);
  } catch (e) { res.writeHead(500).end(String(e)); }
});
server.listen(port, host, () => console.log(`serving ${root} on http://${host}:${port}/`));
