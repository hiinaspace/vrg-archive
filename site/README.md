# archive.vrg.party site (R1)

Static, client-side search over the /vrg/ archive. `./build.sh [out]` builds everything.

- `src/vrg_site/` Python build: corpus filter (settle window, deleted posts, `excluded_ids.txt`), sharded index, thread pages, thumbnail packs.
- `web/` search page (TypeScript, esbuild): engine, query language, facets, over-time chart. `npm test` runs the node tests.
- `static/` thread CSS/JS, about page, robots, headers. `serve.mjs` is a Range-capable preview server.
- `oracle/` `check_counts.py` (engine vs brute force over SQLite), `smoke_targets.json`, `queries.txt` (owner queries).
- Facet counts are conjunctive over the current result set; the month chart ignores the date filter. Phrase queries are verified against text blocks (exact up to 400 blocks, else flagged upper bounds).
