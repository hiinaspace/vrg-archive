import json, glob, os, statistics as st
def load(p): return [json.loads(l) for l in open(p) if l.startswith("{")]
def kb(x): return f"{x/1024:,.0f}" if x < 1e6 else f"{x/1048576:,.1f}M"
rows = []
files = [("SQLite FTS5 + sql.js-httpvfs, newest-first", "out/sqlite_newest.jsonl"), ("SQLite FTS5 + sql.js-httpvfs, bm25 rank", "out/sqlite_rank.jsonl"),
 ("Custom A (6 partitions x128 buckets), newest-first","out/custA_new.jsonl"),("Custom A, relevance","out/custA_rel.jsonl"),
 ("Custom B (1 partition x1024), newest-first","out/custB_new.jsonl"),("Custom B, relevance","out/custB_rel.jsonl"),
 ("Custom C (6 partitions x512), newest-first","out/custC_new.jsonl"),("Custom C, relevance","out/custC_rel.jsonl"),
 ("Custom E (2 partitions x1024), newest-first","out/custE_new.jsonl"),("Custom E, relevance","out/custE_rel.jsonl"),
 ("DuckDB-wasm + Parquet range (rg 30k/4096), newest-first","out/duck_new.jsonl"),("DuckDB-wasm + Parquet range (rg 8k/1024), newest-first","out/duck2_new.jsonl")]
print("| config | startup (br) | rare avg | common avg | phrase avg | substr | date | reqs rare/common/phrase/substr/date | local ms (query, excl. startup) rare/common |")
print("|---|---|---|---|---|---|---|---|---|")
for name, p in files:
    if not os.path.exists(p): continue
    r = load(p)
    if len(r) < 15: continue
    g = lambda k, f: [x[f] for x in r if x["kind"] == k]
    m = lambda k: st.mean(g(k, "data")); q = lambda k: round(st.mean(g(k, "data_reqs")))
    startup = r[0]["static_br"]
    print(f"| {name} | {kb(startup)} | {kb(m('rare'))} | {kb(m('common'))} | {kb(m('phrase'))} | {kb(m('substring'))} | {kb(m('date'))} | {q('rare')}/{q('common')}/{q('phrase')}/{q('substring')}/{q('date')} | |")
