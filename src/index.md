---
title: /vrg/ Archive
toc: false
---

# /vrg/ Archive

Welcome to the archive of Virtual Reality General threads from 4chan's /vg/ board.

While the [b4k archive](https://b4k.dev) also has the /vg/ archived, it's slow
and is missing data before ~august 2019. Thanks to an anon from Bibliotheca
Anonoma, I got a copy of the text archive that goes back all the way to the
first thread in ~2016. And thanks to the industrial revolution and its
consequences, you can actually query the entire archive pretty efficiently in
your browser.

I don't have thumbnails or images (yet), but I'm working on it. Until then,
enjoy the data.

<div class="warning">All queries in your browser, which means you'll download a
fair amount (~100MB) of data. So probably don't browse this your phone.</div>

## Pages

<div class="grid grid-cols-3">
  <a class="card" href="thread-browser">
    <h2>Thread Browser</h2>
    <p>Browse old threads in a somewhat faithful format.</p>
  </a>
  <a class="card" href="substring-search">
      <h2>Substring Search</h2>
      <p>See how freqently certain substrings occur in the posts over time, a la google's ngram thing.</p>
  </a>
  <a class="card" href="full-text-search">
      <h2>Full-text Search</h2>
      <p>Search posts with an inverted index. Freakishly fast.</p>
  </a>
</div>

```js
const archive_href = FileAttachment("data/vrgarchive.parquet").href;
```

## FAQ

### wtf is this

it's an archive of [/vrg/](https://boards.4chan.org/vg/catalog#s=vrg) with a
bunch of javascript so you can query it efficiently in your browser.

### Where did you get the archive data?

Data after august 2019 is scraped from b4k, and the older data is from an anon
on the Bibliotheca Anonoma matrix channel who happened to have a private
archiver. Thanks anon for uploading it for me.

### Where are the images?

Don't have them yet, but I'm working on it. 2 more weeks.

### Can I get the raw data?

Yeah, download the ${html`<a href=${archive_href}>vrgarchive.parquet</a>`} file. It's not quite
raw as from the 4chan API, but it is easier to query and it's only ~90MB or so.

### How is the data so small?

The data compresses extremely well with ZSTD and parquet. The uncompresed data is ~1.5GB, but
I guess after all these years we've only posted ~80MB of insightful, original text.

### How does it work?

This site uses [Observable Framework](https://observablehq.com), which includes
a [DuckDB](https://duckdb.org) wasm build, which queries the archive as parquet
files. It's kind of horrifying yeah but also cool.

### Can you add X feature?

Maybe, post in the thread about it. If you don't want to wait, you can also just
download the raw data and query it yourself, with duckDB or whatever.

### archives are bad

Yeah, I'm kind of ambivalent, but I have autism for data visualization and
awful javascript frameworks, so I did it anyway.

### How can I contact you?

Post in the thread, I'll see it.
