---
title: Full Text Search
---

# Full Text Search

This uses [DuckDB's full text search extention](https://duckdb.org/docs/stable/extensions/full_text_search.html)
to search through all the post comments. It's freakishly fast for running entirely in your browser. The index
is built offline and loaded as parquet files.

It is a bit limited, in that it only searches stems of common words, and no search operators (I think).
But still, very fast for ~1.3 million posts.

If you see errors, try a different browser, or turn off the "advanced tracking protection". Not sure why it
breaks this script particularly when the javascript is just as horrifying on the other pages, but oh well.

```js
const schema_sql = `
LOAD fts;
CREATE SCHEMA fts_main_posts;
create table fts_main_posts.dict AS FROM '${FileAttachment("data/vrgindex/fts_main_posts_dict.parquet").href}';
create table fts_main_posts.docs AS FROM '${FileAttachment("data/vrgindex/fts_main_posts_docs.parquet").href}';
create table fts_main_posts.fields AS FROM '${FileAttachment("data/vrgindex/fts_main_posts_fields.parquet").href}';
create table fts_main_posts.stats AS FROM '${FileAttachment("data/vrgindex/fts_main_posts_stats.parquet").href}';
create table fts_main_posts.stopwords AS FROM '${FileAttachment("data/vrgindex/fts_main_posts_stopwords.parquet").href}';
create table fts_main_posts.terms AS FROM '${FileAttachment("data/vrgindex/fts_main_posts_terms.parquet").href}';
create table posts as from '${FileAttachment("data/vrgarchive.parquet").href}';
CREATE MACRO if not exists fts_main_posts.tokenize (s) AS (string_split_regex(regexp_replace(lower(strip_accents(CAST(s AS VARCHAR))), '[0-9!@#$%^&*()_+={}\\[\\]:;<>,.?~\\\/\\|''''"\`-]+', ' ', 'g'), '\\s+'));;
CREATE MACRO if not exists fts_main_posts.match_bm25 (docname, query_string, b := 0.75, conjunctive := false, k := 1.2, fields := NULL) AS ((WITH tokens AS (SELECT DISTINCT stem(unnest(fts_main_posts.tokenize(query_string)), 'porter') AS t), fieldids AS (SELECT fieldid FROM fts_main_posts.fields WHERE CASE  WHEN ((fields IS NULL)) THEN (1) ELSE (field = ANY(SELECT * FROM (SELECT unnest(string_split(fields, ','))) AS fsq)) END), qtermids AS (SELECT termid FROM fts_main_posts.dict AS dict , tokens WHERE (dict.term = tokens.t)), qterms AS (SELECT termid, docid FROM fts_main_posts.terms AS terms WHERE (CASE  WHEN ((fields IS NULL)) THEN (1) ELSE (fieldid = ANY(SELECT * FROM fieldids)) END AND (termid = ANY(SELECT qtermids.termid FROM qtermids)))), term_tf AS (SELECT termid, docid, count_star() AS tf FROM qterms GROUP BY docid, termid), cdocs AS (SELECT docid FROM qterms GROUP BY docid HAVING CASE  WHEN (conjunctive) THEN ((count(DISTINCT termid) = (SELECT count_star() FROM tokens))) ELSE 1 END), subscores AS (SELECT docs.docid, len, term_tf.termid, tf, df, (log((((((SELECT num_docs FROM fts_main_posts.stats) - df) + 0.5) / (df + 0.5)) + 1)) * ((tf * (k + 1)) / (tf + (k * ((1 - b) + (b * (len / (SELECT avgdl FROM fts_main_posts.stats)))))))) AS subscore FROM term_tf , cdocs , fts_main_posts.docs AS docs , fts_main_posts.dict AS dict WHERE ((term_tf.docid = cdocs.docid) AND (term_tf.docid = docs.docid) AND (term_tf.termid = dict.termid))), scores AS (SELECT docid, sum(subscore) AS score FROM subscores GROUP BY docid)SELECT score FROM scores , fts_main_posts.docs AS docs WHERE ((scores.docid = docs.docid) AND (docs."name" = docname))));;
`;
const db = await DuckDBClient.of();
await db.sql([schema_sql]);
const sql = db.sql.bind(db);
```

```js
import DOMPurify from 'npm:dompurify';
````


```js
const search_term = view(
  Inputs.text({
    label: "Search",
    placeholder: "search for something",
    value: "sneed"
  })
);
```

```js
const search_results = await sql`
select post_num, epoch_ms(timestamp * 1000) as post_time, comment from (select *, fts_main_posts.match_bm25(post_num, ${search_term}) as score from posts) sq where score is not null order by score desc`;
```

${search_results.numRows} results.

```js
Plot.plot({
  width: width,
  x: {
    interval: "month"
  },
  marks: [
    Plot.barY(search_results, Plot.binX({"y": "count"}, { x: "post_time" , interval: "month", "tip": true}))
  ]
})
```

```js
Inputs.table(search_results, { width: {"comment": 500 },
format: {
  "comment": (v) => {
    let p = DOMPurify.sanitize(v);
    let span = document.createElement("span");
    span.innerHTML = p;
    return span
  }
}})
```
