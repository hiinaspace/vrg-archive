# vrg-archive

Source for [archive.vrg.party](https://archive.vrg.party): a static, in-browser search over the 4chan /vg/ /vrg/ (Virtual Reality General) threads, with thread pages, trend charts and thumbnails. It is served from Cloudflare Pages and has no server.

- [`corpus/`](corpus/): merges the scraper database, the earlier archive export and b4k supplements into one normalized SQLite corpus, and fetches thumbnails and legacy flags from b4k (polite, rate-limited).
- [`site/`](site/README.md): builds the static site from the corpus: sharded search index, thread pages, thumbnail packs, and the search page (`site/web/`). Run `site/build.sh` to build it.
- `site/excluded_ids.txt`: the takedown list. See the site's [takedown policy](https://archive.vrg.party/takedown.html).

The top-level `src/`, `package.json` and `observablehq.config.js` are the previous version of the site (an Observable Framework app), kept for reference.

Not affiliated with 4chan or b4k. Post text and thumbnails belong to their posters.
