import * as pagefind from 'pagefind'; import fs from 'node:fs'; import { execFileSync } from 'node:child_process';
const N = +process.argv[2]; const out = process.argv[3];
// dump N docs (evenly sampled) from the corpus
execFileSync('duckdb', ['-c', `copy (select id, ts, idx from 'data/corpus.parquet' using sample ${N} rows (reservoir, 1)) to '/tmp/claude-1000/pf_${N}.json' (format json, array true)`], {cwd: '..'});
const docs = JSON.parse(fs.readFileSync(`/tmp/claude-1000/pf_${N}.json`));
const t = Date.now();
const { index } = await pagefind.createIndex({});
for (const d of docs) await index.addCustomRecord({ url: '/p/' + d.id, content: d.idx, language: 'en', meta: { ts: String(d.ts) } });
await index.writeFiles({ outputPath: out });
console.log(JSON.stringify({ N, build_s: (Date.now() - t) / 1000 }));
await pagefind.close();
