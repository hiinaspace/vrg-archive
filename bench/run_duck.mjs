import { launch, QUERIES, summarize } from './lib.mjs'; import fs from 'node:fs';
const base = process.argv[2], sort = process.argv[3] || 'rel';
const RANGES = JSON.parse(fs.readFileSync('out/ranges.json'));
const b = await launch(); const specs = [];
for (const w of QUERIES.rare) specs.push(['rare', w, {words:[w]}]);
for (const w of QUERIES.common) specs.push(['common', w, {words:[w]}]);
for (const w of QUERIES.phrase) specs.push(['phrase', w, {words:w.split(' '), phrase:w}]);
specs.push(['substring','wrld_',{words:['wrld'], substr:'wrld_'}]);
specs.push(['date','vrchat 2023',{words:['vrchat'], lo:RANGES['2023'][0], hi:RANGES['2023'][1]}]);
for (const [kind,label,q] of specs) {
  const ctx = await b.newContext(); const page = await ctx.newPage();
  await fetch('http://127.0.0.1:8099/__reset');
  await page.goto('http://127.0.0.1:8099/web/duck.html');
  const t0 = Date.now(); await page.evaluate(c => window.init(c), base);
  const res = await page.evaluate(q => window.q(q), {...q, sort}); const tQ = Date.now() - t0;
  const s = summarize(await (await fetch('http://127.0.0.1:8099/__log')).json());
  console.log(JSON.stringify({kind,label,rows:res.n,cand:res.cand,total_ms:tQ,...s})); await ctx.close();
}
await b.close();
