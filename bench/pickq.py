import duckdb, random
c = duckdb.connect()
c.execute("create view p as select * from 'data/corpus.parquet'")
for w in ["vrchat","game","anyone","headset","quest"]:
    print(w, c.execute("select count(*) from p where regexp_matches(lower(idx), '\\b"+w+"\\b')").fetchone())
for ph in ["quest pro","index controllers","full body","mic spam","public avatars","oculus link","avatar world","steam sale"]:
    print(ph, c.execute("select count(*) from p where lower(idx) like ?",[f"%{ph}%"]).fetchone())
print(c.execute("select count(*) from p where text like '%wrld_%'").fetchone())
# rare words: df between 5 and 30
c.execute("create table w as select w, count(distinct id) df from (select id, unnest(regexp_extract_all(lower(idx),'[a-z]{6,}')) w from p) group by w")
print(c.execute("select count(*) from w where df between 5 and 20").fetchone())
random.seed(7)
rows=c.execute("select w, df from w where df between 5 and 20 order by hash(w) limit 12").fetchall(); print(rows)
print(c.execute("select count(*) from p where ts>=1672531200 and ts<1704067200 and regexp_matches(lower(idx), '\\bvrchat\\b')").fetchone())
