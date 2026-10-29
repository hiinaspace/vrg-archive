// Run queries through the engine and dump exact totals, monthly series and facet counts as JSON.
// usage: node build.mjs --run test/dump.ts <data dir> <queries.json> <out.json>
import { readFileSync, writeFileSync } from "node:fs";
import { Engine } from "../src/engine";
import { FileStore } from "./filestore";

const [dir, qfile, out] = process.argv.slice(2);
const e = await Engine.load(new FileStore(dir));
const queries: string[] = JSON.parse(readFileSync(qfile, "utf8"));
const res: Record<string, unknown> = {};
for (const q of queries) {
  const r = await e.run(q, { exact: true });
  const bk = e.bucketsIn("month", e.m.day0, e.m.day0 + e.m.ndays - 1);
  const f = e.facets(r);
  res[q] = {
    total: r.total, pending: r.pending,
    months: Object.fromEntries(bk.days.map((d, i) => [new Date(d * 86400000).toISOString().slice(0, 7), 0 + e.seriesCounts(r.bits, bk)[i]]).filter((x) => x[1] !== 0)),
    image: f.image, op: f.op, ext: f.ext, rep: f.rep, link: f.link, green: f.green,
    top_thread: [...f.thread].map((c, i) => [e.threads[i].no, c]).filter((x) => (x[1] as number) > 0).sort((a, b) => (b[1] as number) - (a[1] as number) || (a[0] as number) - (b[0] as number)).slice(0, 5),
    domain: Object.fromEntries(f.domain.filter((d) => d[1] > 0)),
  };
}
writeFileSync(out, JSON.stringify(res));
console.log("wrote", out, "bytes fetched", (e.store as FileStore).stats.bytes);
