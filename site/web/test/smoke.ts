// Known-item smoke test: rank of a target post for a vague query, under newest and relevance sort.
// Also runs oracle/queries.txt (owner's private lines: "description ||| query" runs the query; otherwise quoted phrases in the
// line, if any, else the line itself) and prints totals and top rows for eyeballing.
// usage: node build.mjs --run test/smoke.ts <data dir> <out.json>
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { Engine } from "../src/engine";
import { relaxedQuery } from "../src/query";
import { FileStore } from "./filestore";

const [dir, out] = process.argv.slice(2);
const e = await Engine.load(new FileStore(dir));
const targets: { no: number; q: string; note: string }[] = JSON.parse(readFileSync("../oracle/smoke_targets.json", "utf8"));
const year = (t: number) => new Date(t * 1000).getUTCFullYear();

async function rankOf(q: string, no: number, sort: "newest" | "relevance", max = 200) {
  const r = await e.run(q);
  const pg = await e.page(r, sort, 0, max);
  const rows = await e.rows(pg.docs);
  const i = rows.findIndex((x) => x.no === no);
  return { rank: i < 0 ? null : i + 1, total: r.total };
}
const results = [];
for (const t of targets) {
  const a = await rankOf(t.q, t.no, "newest"), b = await rankOf(t.q, t.no, "relevance");
  const rq = a.total < 5 ? relaxedQuery(t.q) : null;
  const ra = rq ? await rankOf(rq, t.no, "newest") : null, rb = rq ? await rankOf(rq, t.no, "relevance") : null;
  results.push({ ...t, total: a.total, rank_newest: a.rank, rank_relevance: b.rank, relaxed: rq ? { total: ra!.total, rank_newest: ra!.rank, rank_relevance: rb!.rank } : null });
}
console.log("no\ttotal\tnewest\trelev\t| relaxed(total/newest/relev)\tquery");
for (const r of results) console.log(`${r.no}\t${r.total}\t${r.rank_newest ?? ">200"}\t${r.rank_relevance ?? ">200"}\t| ${r.relaxed ? `${r.relaxed.total}/${r.relaxed.rank_newest ?? ">200"}/${r.relaxed.rank_relevance ?? ">200"}` : "-"}\t${r.q}`);

const owner: unknown[] = [];
if (existsSync("../oracle/queries.txt")) {
  for (const line of readFileSync("../oracle/queries.txt", "utf8").split("\n").map((l) => l.trim()).filter(Boolean)) {
    let q = line;
    if (line.includes(" ||| ")) q = line.split(" ||| ")[1].trim();
    else { const m = [...line.matchAll(/"([^"]+)"/g)].map((x) => `"${x[1]}"`); if (m.length) q = m.join(" "); }
    const r = await e.run(q);
    const pg = await e.page(r, "relevance", 0, 3);
    const rows = await e.rows(pg.docs);
    owner.push({ line, q, total: r.total, top: rows.map((x) => `${year(x.time)} No.${x.no} ${x.body.slice(0, 90).replace(/\n/g, " / ")}`) });
  }
}
writeFileSync(out, JSON.stringify({ results, owner }, null, 1));
console.log(JSON.stringify(owner, null, 1));
