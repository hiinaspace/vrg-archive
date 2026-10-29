import sqlite3, os, shutil, pyarrow.parquet as pq, hashlib
N_OLD = 1375527 - 4000
os.makedirs("out/sqlite_inc", exist_ok=True); p = "out/sqlite_inc/old.db"
if os.path.exists(p): os.remove(p)
db = sqlite3.connect(p); db.execute("pragma page_size=4096"); db.execute("pragma journal_mode=off"); db.execute("pragma synchronous=off")
db.execute("create table post(id integer primary key, ts integer, no integer, text text)")
db.execute("create virtual table fts using fts5(idx, content='', tokenize='porter unicode61 remove_diacritics 2', detail=full)")
t = pq.read_table("data/corpus.parquet").to_pydict()
def ins(lo, hi):
    db.executemany("insert into post values(?,?,?,?)", zip(t["id"][lo:hi], t["ts"][lo:hi], t["no"][lo:hi], t["text"][lo:hi]))
    db.executemany("insert into fts(rowid, idx) values(?,?)", zip(t["id"][lo:hi], t["idx"][lo:hi]))
for lo in range(0, N_OLD, 50000): ins(lo, min(N_OLD, lo + 50000))
db.commit(); db.execute("insert into fts(fts) values('optimize')"); db.commit(); db.execute("vacuum"); db.close()
shutil.copy(p, "out/sqlite_inc/new.db"); db = sqlite3.connect("out/sqlite_inc/new.db"); ins(N_OLD, 1375527); db.commit(); db.close()
a, b = open(p, "rb").read(), open("out/sqlite_inc/new.db", "rb").read()
PS = 4096; CH = 16 * 1024 * 1024
pages = sum(1 for i in range(0, len(b), PS) if a[i:i+PS] != b[i:i+PS])
chunks = sum(1 for i in range(0, len(b), CH) if a[i:i+CH] != b[i:i+CH])
print("old", len(a), "new", len(b), "pages changed", pages, "=", pages * PS, "bytes; 16MiB chunks changed", chunks, "of", (len(b) + CH - 1)//CH)
