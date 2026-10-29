"""Normalize the history parquet into corpus.parquet: id (time order), no, ts, text (display), idx (indexed text, >>N stripped)."""
import re, html, sys, duckdb, pyarrow as pa, pyarrow.parquet as pq
SRC = "/home/s/code/vrg-archive-data/snap-20261029/vrgarchive-2025-04-11.parquet"
rows = duckdb.sql(f"select post_num, timestamp, comment from '{SRC}' where comment is not null and comment<>'' order by timestamp, post_num").fetchall()
tag = re.compile(r"<[^>]+>"); br = re.compile(r"<br\s*/?>", re.I)
q = re.compile(r">>\d+(?:,\d+)?")
no, ts, text, idx = [], [], [], []
for n, t, c in rows:
    s = html.unescape(tag.sub("", br.sub("\n", c))).strip()
    if not s: continue
    no.append(n); ts.append(t); text.append(s); idx.append(q.sub(" ", s))
tbl = pa.table({"id": pa.array(range(len(no)), pa.int32()), "no": no, "ts": ts, "text": text, "idx": idx})
pq.write_table(tbl, "data/corpus.parquet", compression="zstd", row_group_size=50000)
print(len(no), sum(map(len, text)), sum(map(len, idx)))
