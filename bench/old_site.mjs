import { launch } from './lib.mjs';
const b = await launch(); const ctx = await b.newContext(); const page = await ctx.newPage();
const reqs = []; ctx.on('requestfinished', async r => { try { const s = await r.sizes(); reqs.push({url: r.url(), body: s.responseBodySize, hdr: s.responseHeadersSize}); } catch {} });
const t0 = Date.now(); let tFirst = null;
await page.goto('https://archive.vrg.party/full-text-search', {waitUntil: 'commit'});
try { await page.waitForFunction(() => /\d[\d,]* results\./.test(document.body.innerText), null, {timeout: 170000}); tFirst = Date.now() - t0; } catch (e) { console.log('timeout'); }
console.log('first results ms', tFirst, await page.evaluate(() => (document.body.innerText.match(/\d[\d,]* results\./)||[])[0]));
const tot = reqs.reduce((a, r) => a + r.body + r.hdr, 0);
console.log('requests', reqs.length, 'total bytes', tot);
for (const r of reqs.sort((a,b)=>b.body-a.body).slice(0,14)) console.log(r.body, r.url.slice(0,120));
await b.close();
