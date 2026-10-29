import { launch, QUERIES, Y2023, summarize } from './lib.mjs';
const mode = process.argv[2] || 'chunked'; // config
const cfg = process.argv[3] || '/out/sqlite/chunks/config.json';
const order = process.argv[4] || 'rowid DESC'; // or rank
import fs from 'node:fs'; const RANGES = JSON.parse(fs.readFileSync('out/ranges.json'));
const b = await launch(); const out = [];
const base = `SELECT p.id,p.ts,p.text FROM fts JOIN post p ON p.id=fts.rowid WHERE fts MATCH ? AND fts.rowid BETWEEN ? AND ?`;
const specs = [];
for (const w of QUERIES.rare) specs.push(['rare', w, `"${w}"`, 0, 1e9]);
for (const w of QUERIES.common) specs.push(['common', w, `"${w}"`, 0, 1e9]);
for (const w of QUERIES.phrase) specs.push(['phrase', w, `"${w}"`, 0, 1e9]);
specs.push(['substring', 'wrld_', null, 0, 1e9]);
specs.push(['date', 'vrchat 2023', '"vrchat"', 'Y', 'Y']);
for (const [kind, label, match, lo, hi] of specs) {
  const ctx = await b.newContext(); const page = await ctx.newPage();
  await fetch('http://127.0.0.1:8099/__reset');
  await page.goto('http://127.0.0.1:8099/web/sqlite.html');
  const t0 = Date.now(); await page.evaluate(c => window.init(c), cfg);
  const tInit = Date.now() - t0;
  let sql, params;
  let L = lo, H = hi;
  if (lo === 'Y') { [L, H] = RANGES['2023']; }
  if (kind === 'substring') { sql = `SELECT p.id,p.ts,p.text FROM fts JOIN post p ON p.id=fts.rowid WHERE fts MATCH 'wrld' AND p.text LIKE '%wrld\\_%' ESCAPE '\\' ORDER BY fts.rowid DESC LIMIT 20`; params = []; }
  else { sql = base + ` ORDER BY ${order === 'rank' ? 'rank' : 'fts.rowid DESC'} LIMIT 20`; params = [match, L, H]; }
  const t1 = Date.now(); const res = await page.evaluate(([s,p]) => window.q(s,p), [sql, params]); const tQ = Date.now() - t1;
  const log = await (await fetch('http://127.0.0.1:8099/__log')).json();
  const s = summarize(log);
  out.push({kind, label, rows: res.n, init_ms: tInit, query_ms: tQ, ...s});
  console.log(JSON.stringify(out.at(-1)));
  await ctx.close();
}
await b.close();
