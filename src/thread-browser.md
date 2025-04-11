---
title: Thread Browser
toc: false
sql:
  posts: ./data/vrgarchive.parquet
---

# Thread Browser

Browser posts in old threads in a somewhat faithful format. It takes a bit to load and this framework is bad about indicating loading progress, so wait around if you don't see anything.

There are no thumbnails or full images (yet).

```sql id=threads
select
first(thread_num) as thread_num,
any_value(thread_title) as thread_title,
first(epoch_ms(timestamp * 1000)) as thread_time,
count(*) as num_comments
from posts
group by thread_num;
```

```js
const search = view(
  Inputs.search(threads,
    {label: "filter threads: ",
      placeholder: "filter",
      filter: (query) => (c) => c.thread_title.toLowerCase().includes(query.toLowerCase())}));
```

Click the radio button on the left of each column to select a thread to display.

```js
const thread = view(Inputs.table(search, {
  format: {
    "thread_time": (v) => new Date(v).toLocaleString()
  },
  value: threads[0], multiple: false, width: {thread_title: 300, thread_time: 200}}));
````

```js
import {Post} from "./components/post.js";

let rows = thread == null ? []: await sql`select * from posts where thread_num = ${thread.thread_num}`;

const posts = [...rows];

let b4k_url = `https://arch.b4k.dev/vg/post/${thread.thread_num}/`;
```

${posts.length} posts.

${html`<a href=${b4k_url} target="_blank">View on b4k archive (for threads after ~#613)</a>`}.

```jsx
display(posts.map(p => <Post postData={p} />))
```

<style>
  div.post {
	margin: 4px 0;
	overflow: hidden;
	color: light-dark(black, #c5c8c6);
  font-family: arial, helvetica, sans-serif;
  font-size: 10pt;
  }

  div.thread>div:nth-of-type(2)>div.reply {
	margin-top: 2px !important;
  }

  div.op {
	display: inline;
  }

  div.reply {
	background-color: light-dark(#D6DAF0, #282a2e);
	border: 1px solid light-dark(#B7C5D9, #282a2e);
	display: table;
	padding: 2px;
  }

  div.reply input {
	float: none;
  }

  div.post div.postInfo {
	display: block;
	width: 100%;
  }

  .fileText {
    max-width: 600px;
    white-space: nowrap;
  }

  div.post div.postInfo span.postNum {
  }

  div.post div.postInfo span.postNum > a {
	text-decoration: none;
	color: light-dark(black, #C5C8C6) !important;
  }

  div.post div.postInfo span.postNum a:hover, .posteruid .hand:hover {
	color: light-dark(black, #c5F89AC) !important;
  }

  div.post div.postInfo span.nameBlock {
	display: inline-block;
  }

  div.post div.postInfo span.nameBlock span.name {
	color: light-dark(#117743, #c5c8c6);
	font-weight: bold;
  }

  div.post div.postInfo span.nameBlock span.postertrip {
	color: light-dark(#117743, #c5c8c6);
	font-weight: normal !important;
  }

  div.post div.postInfo span.date {
  }

  div.post div.postInfo span.time {
  }

  div.post div.postInfo span.subject {
	color: #b294bb;
	font-weight: bold;
  }

  div.post blockquote.postMessage {
	display: block;
  }

  blockquote span.quote {
	color: light-dark(#789922, #b5bd68);
  }

  .quoteLink, .quotelink, .deadlink {
	color: light-dark(#DD0000, #5F89AC) !important;
	text-decoration: underline;
  }

  a.quoteLink:hover, a.quotelink:hover {
	color: #81a2be !important;
  }
  div.post div.file {
	display: block;
  }

  div.post div.file div.fileInfo {
	margin-right: 10px;
    word-break: break-all;
  }

  div.replyContainer div.post div.file div.fileInfo {
	margin-left: 20px;
  }

  div.post div.file .fileThumb {
	float: left;
	margin-left: 20px;
	margin-right: 20px;
	margin-top: 3px;
	margin-bottom: 5px;
  }

  span.fileThumb {
	margin-left: 0px !important;
	margin-right: 5px !important;
  }

  div.reply span.fileThumb, div.reply span.fileThumb img {
	float: none !important;
	margin-top: 0px !important;
	margin-bottom: 0px !important;
  }

  div.post div.file .fileThumb img {
	border: none;
	float: left;
  }
</style>
