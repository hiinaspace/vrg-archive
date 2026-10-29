// Playwright helper: open the site, run a query, report console errors, bytes and a screenshot.
import { chromium } from "playwright";
const url = process.argv[2] ?? "http://localhost:8796/";
const q = process.argv[3] ?? "";
const shot = process.argv[4];
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH });
const p = await b.newPage({ viewport: { width: 1300, height: 1000 } });
const errs = [];
p.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errs.push(m.text()); });
p.on("pageerror", (e) => errs.push("PAGEERROR " + e.message));
await p.goto(url + (q ? "?q=" + encodeURIComponent(q) : ""));
await p.waitForFunction(() => document.querySelector("#results li"), null, { timeout: 60000 }).catch(() => {});
await p.waitForTimeout(1500);
console.log("status:", await p.textContent("#status"));
console.log("summary:", await p.textContent("#summary"));
console.log("first rows:", (await p.$$eval("#results li", (l) => l.slice(0, 3).map((x) => x.innerText.replace(/\n+/g, " | ").slice(0, 200)))));
console.log("errors:", errs);
if (shot) await p.screenshot({ path: shot });
await b.close();
