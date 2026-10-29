// Cold-load measurements in Chromium against a Range-capable server (CDP network accounting).
// usage: node test/measure.mjs <base url> <out.json>
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const base = process.argv[2] ?? "http://localhost:8796/";
const out = process.argv[3] ?? "measure.json";
const exe = "/home/s/.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell";
const browser = await chromium.launch({ executablePath: exe });

async function scenario(url, ready, { after } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1300, height: 1000 } });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  const reqs = new Map();
  cdp.on("Network.requestWillBeSent", (e) => reqs.set(e.requestId, { url: e.request.url, range: e.request.headers.Range ?? e.request.headers.range ?? null, bytes: 0 }));
  cdp.on("Network.responseReceived", (e) => { const r = reqs.get(e.requestId); if (r) r.status = e.response.status; });
  cdp.on("Network.loadingFinished", (e) => { const r = reqs.get(e.requestId); if (r) r.bytes = e.encodedDataLength; });
  const t0 = Date.now();
  await page.goto(url);
  await page.waitForFunction(ready, null, { timeout: 90000 });
  const ms = Date.now() - t0;
  await page.waitForTimeout(600);
  const mark = [...reqs.keys()].length;
  let phase2 = null;
  if (after) {
    const before = new Set(reqs.keys());
    const t1 = Date.now();
    await after(page);
    await page.waitForTimeout(800);
    const added = [...reqs.entries()].filter(([k]) => !before.has(k)).map(([, v]) => v);
    phase2 = { ms: Date.now() - t1, requests: added.length, bytes: added.reduce((a, r) => a + r.bytes, 0), urls: added.map((r) => r.url.replace(base, "")) };
  }
  const all = [...reqs.values()];
  const sum = (f) => all.filter(f).reduce((a, r) => a + r.bytes, 0);
  const res = {
    url: url.replace(base, "/"), ms, requests: all.length, bytes: sum(() => true),
    static_bytes: sum((r) => !r.url.includes("/data/")), data_bytes: sum((r) => r.url.includes("/data/")),
    thumb_requests: all.filter((r) => r.url.includes("/thumbs/")).length, thumb_bytes: sum((r) => r.url.includes("/thumbs/")),
    range_responses: all.filter((r) => r.status === 206).length, phase2,
    top: all.sort((a, b) => b.bytes - a.bytes).slice(0, 6).map((r) => `${r.bytes} ${r.url.replace(base, "")}`),
    mark,
  };
  await ctx.close();
  return res;
}
const ready = () => document.querySelector("#results li") && !/loading/.test(document.querySelector("#status").textContent);
const results = {};
results.cold_first_view = await scenario(base, ready);
results.cold_first_view_with_chart = results.cold_first_view;
const typeQ = (q) => async (p) => { await p.fill("#q", q); await p.waitForFunction((q) => new URLSearchParams(location.search).get("q") === q && document.querySelector("#summary")?.textContent && !document.querySelector("#results li.empty-state") , q, { timeout: 60000 }).catch(() => {}); };
const common = ["vrchat", "quest", "game", "avatar", "index", "headset", "steam", "world", "people", "valve", "event", "video", "price", "anyone", "pc", "thread", "play", "anon", "friends", "shit"];
const rare = ["mindgames", "sneedup", "deckard", "teambeef", "sunao", "barnwarming", "bigscreen", "lynx", "outer wilds", "wolfenstein"];
results.queries = {};
for (const q of [...common, "the", ...rare, '"headset latency"', '"na tea"', "vrchat -quest has:image", "slop | llm", "thread:1500 quest", ">>585059289"]) {
  results.queries[q] = await scenario(base, ready, { after: typeQ(q) });
  const r = results.queries[q];
  console.log(q.padEnd(28), "incremental", r.phase2.requests, "req", r.phase2.bytes, "B", r.phase2.ms, "ms");
}
// thread page weight
results.thread_page = await scenario(base + "t/585059270.html", () => document.querySelectorAll(".th img").length >= 3);
// permalink redirect
results.permalink = await scenario(base + "p/?585059289", () => location.pathname.includes("/t/"));
writeFileSync(out, JSON.stringify(results, null, 1));
console.log("cold first view:", JSON.stringify({ ...results.cold_first_view, top: undefined }));
console.log("thread page:", JSON.stringify({ ...results.thread_page, top: undefined }));
console.log("permalink:", JSON.stringify({ ...results.permalink, top: undefined }));
await browser.close();
