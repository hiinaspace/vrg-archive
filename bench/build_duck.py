import duckdb, time, os, sys
OUT = sys.argv[2] if len(sys.argv) > 2 else 'out/duck'; os.makedirs(OUT, exist_ok=True)
rg = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
t = time.time(); c = duckdb.connect()
c.execute("set threads=8")
c.execute("create view p as select * from 'data/corpus.parquet'")
c.execute(f"""copy (select w as term, id as doc, cast(least(count(*),255) as utinyint) as tf from
  (select id, unnest(regexp_extract_all(lower(strip_accents(idx)), '[\\p{{L}}\\p{{N}}]+')) w from p) group by w, id order by w, id)
  to '{OUT}/postings.parquet' (format parquet, compression zstd, row_group_size {rg})""")
print("postings", time.time() - t, os.path.getsize(OUT + "/postings.parquet"))
c.execute(f"copy (select id, ts, no, text from p order by id) to '{OUT}/docs.parquet' (format parquet, compression zstd, row_group_size {int(sys.argv[3]) if len(sys.argv) > 3 else 4096})")
print("docs", time.time() - t, os.path.getsize(OUT + "/docs.parquet"))
