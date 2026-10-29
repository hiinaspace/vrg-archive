"""FTS5 index (porter unicode61, contentless) + post table in one DB. Rowid = id (time order). Builds out/sqlite/{vrg.db}"""
import sqlite3, time, sys, os, pyarrow.parquet as pq
tok = sys.argv[1] if len(sys.argv) > 1 else "porter unicode61 remove_diacritics 2"
name = sys.argv[2] if len(sys.argv) > 2 else "vrg"
detail = sys.argv[3] if len(sys.argv) > 3 else "full"
path = f"out/sqlite/{name}.db"
os.makedirs("out/sqlite", exist_ok=True)
if os.path.exists(path): os.remove(path)
db = sqlite3.connect(path)
db.execute("pragma page_size=4096"); db.execute("pragma journal_mode=off"); db.execute("pragma synchronous=off")
db.execute("create table post(id integer primary key, ts integer, no integer, text text)")
db.execute(f"create virtual table fts using fts5(idx, content='', tokenize='{tok}', detail={detail})")
t = time.time()
pf = pq.ParquetFile("data/corpus.parquet")
for b in pf.iter_batches(batch_size=50000):
    d = b.to_pydict()
    db.executemany("insert into post values(?,?,?,?)", zip(d["id"], d["ts"], d["no"], d["text"]))
    db.executemany("insert into fts(rowid, idx) values(?,?)", zip(d["id"], d["idx"]))
db.commit(); print("loaded", time.time() - t)
db.execute("insert into fts(fts) values('optimize')"); db.commit(); print("optimized", time.time() - t)
db.execute("vacuum"); db.close(); print("done", time.time() - t, os.path.getsize(path))
