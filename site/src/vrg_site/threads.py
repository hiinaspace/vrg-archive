"""Static, JavaScript-optional thread pages: t/<thread_no>.html and the thread index."""

from __future__ import annotations

import html
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from . import corpus as C

SITE = "https://archive.vrg.party"
WORLDSEARCH = "https://worldsearch.hiina.space/?world="
_TOKEN = re.compile(
    r"(?P<dq>⁠>>\d+)"
    r"|(?<!⁠)>>(?P<qn>\d+)"
    r"|(?P<sp>\[/?spoiler\])"
    r"|(?P<url>https?://[^\s<>\"']+)"
    r"|(?P<w>wrld_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
esc = html.escape


def fmt_date(ts: int) -> tuple[str, str]:
    d = datetime.fromtimestamp(ts, UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ"), d.strftime(f"%m/%d/%y({_DAYS[d.weekday()]})%H:%M:%S")


def fmt_size(n: int | None) -> str:
    if not n:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def render_body(body: str, thread_no: int, op_no: int, thread_of: dict[int, int]) -> str:
    """Plain-text body -> HTML (greentext, quote links, spoilers, links, world ids)."""
    out: list[str] = []
    spoiler = False
    for line in body.split("\n"):
        green = line.startswith(">") and not line.startswith(">>")
        parts: list[str] = []
        if spoiler:
            parts.append('<s class="sp">')
        pos = 0
        for m in _TOKEN.finditer(line):
            if m.start() > pos:
                parts.append(esc(line[pos : m.start()], quote=False))
            pos = m.end()
            if m["dq"]:
                parts.append(esc(m[0][1:], quote=False))
            elif m["qn"]:
                no = int(m["qn"])
                tno = thread_of.get(no)
                if tno is None:
                    parts.append(esc(m[0], quote=False))
                elif tno == thread_no:
                    op = " (OP)" if no == op_no else ""
                    parts.append(f'<a class="ql" href="#p{no}">&gt;&gt;{no}</a>{op}')
                else:
                    parts.append(
                        f'<a class="ql" href="{tno}.html#p{no}">&gt;&gt;{no}</a> (Cross-thread)'
                    )
            elif m["sp"]:
                if m[0] == "[spoiler]":
                    if not spoiler:
                        parts.append('<s class="sp">')
                    spoiler = True
                elif spoiler:
                    parts.append("</s>")
                    spoiler = False
                else:
                    parts.append(esc(m[0], quote=False))
            elif m["url"]:
                url = m[0]
                tail = ""
                while url and url[-1] in ".,;:!?)]}'\"":
                    tail = url[-1] + tail
                    url = url[:-1]
                parts.append(
                    f'<a href="{esc(url)}" rel="nofollow noopener noreferrer ugc">{esc(url, quote=False)}</a>'
                    + esc(tail, quote=False)
                )
            else:
                w = m[0]
                parts.append(f'<a class="wr" href="{WORLDSEARCH}{w}" rel="noopener">{w}</a>')
        if pos < len(line):
            parts.append(esc(line[pos:], quote=False))
        if spoiler:
            parts.append("</s>")
        s = "".join(parts)
        out.append(f'<span class="gt">{s}</span>' if green else s)
    return "<br>".join(out)


def _post_html(
    p: tuple,
    thread_no: int,
    op_no: int,
    thread_of: dict[int, int],
    backlinks: list[int],
    thumb: tuple | None,
) -> str:
    no = p[C.NO]
    iso, label = fmt_date(p[C.TIME])
    name = esc(p[C.NAME] or "Anonymous")
    trip = f' <span class="tr">{esc(p[C.TRIP])}</span>' if p[C.TRIP] else ""
    s = [
        f'<div class="pc" id="pc{no}"><div class="post{" op" if no == op_no else ""}" id="p{no}">',
        f'<div class="pi"><span class="nm">{name}</span>{trip} '
        f'<time datetime="{iso}">{label}</time> '
        f'<a class="pn" href="#p{no}">No.{no}</a>',
    ]
    if backlinks:
        links = []
        for b in backlinks:
            tb = thread_of[b]
            href = f"#p{b}" if tb == thread_no else f"{tb}.html#p{b}"
            links.append(f'<a class="ql" href="{href}">&gt;&gt;{b}</a>')
        s.append(f' <span class="bl">Replies: {" ".join(links)}</span>')
    s.append("</div>")
    ext = p[C.FEXT]
    if ext:
        size = fmt_size(p[C.FSIZE])
        dims = f"{p[C.FW]}x{p[C.FH]}" if p[C.FW] else ""
        meta = ", ".join(x for x in (size, dims) if x)
        fname = esc((p[C.FNAME] or "") + ext)
        s.append(f'<div class="fl"><div class="ft">File: <span class="fn">{fname}</span>')
        if meta:
            s.append(f" ({meta})")
        s.append("</div>")
        sp = " sp" if p[C.FSPOILER] else ""
        if thumb:
            pk, off, ln, w, h = thumb
            s.append(
                f'<div class="th{sp}" data-t="{pk},{off},{ln}" style="width:{w}px;height:{h}px">'
                f'<span class="phn">{fname}</span></div>'
            )
        else:
            s.append(
                f'<div class="th ph{sp}"><span class="phn">{esc(p[C.FNAME] or "")}</span>'
                f'<span class="phe">{esc(ext)}</span>'
                + (f'<span class="phd">{dims}</span>' if dims else "")
                + "</div>"
            )
        s.append("</div>")
    s.append(
        f'<blockquote class="pm">{render_body(p[C.BODY], thread_no, op_no, thread_of)}</blockquote>'
    )
    s.append("</div></div>")
    return "".join(s)


def _nav(prev_t, next_t) -> str:
    def a(t, label):
        return f'<a href="{t.no}.html">{label}</a>' if t else f"<span>{label}</span>"

    return (
        '<nav class="nv">'
        '<a href="../">Search</a> <a href="./">Threads</a> <a href="../about.html">About</a> '
        f'<span class="sep">|</span> {a(prev_t, "&larr; previous thread")} '
        f"{a(next_t, 'next thread &rarr;')} "
        '<button type="button" id="theme" title="toggle dark mode" hidden>dark</button>'
        "</nav>"
    )


def render_all(
    cor: C.Corpus,
    quotes: list[tuple[int, int]],
    thumbs: dict[int, tuple[int, int, int, int, int]],
    out: Path,
    log=print,
) -> dict:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    thread_of = {p[C.NO]: p[C.THREAD] for p in cor.posts}
    back: dict[int, list[int]] = {}
    for a, b in quotes:
        back.setdefault(b, []).append(a)
    by_thread: dict[int, list[tuple]] = {t.no: [] for t in cor.threads}
    for p in cor.posts:
        by_thread[p[C.THREAD]].append(p)
    sizes: list[int] = []
    for i, t in enumerate(cor.threads):
        posts = by_thread[t.no]
        if not posts:
            continue
        prev_t = cor.threads[i - 1] if i > 0 else None
        next_t = cor.threads[i + 1] if i + 1 < len(cor.threads) else None
        op_no = t.no
        iso, label = fmt_date(t.first_time)
        first_text = ""
        for p in posts:
            if p[C.BODY]:
                first_text = re.sub(
                    r"\s+", " ", re.sub(r"\[/?spoiler\]|>>\d+", "", p[C.BODY])
                ).strip()
                break
        desc = esc(first_text[:200])
        head = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(t.subject)} - archive.vrg.party</title>"
            f'<meta name="description" content="{desc}">'
            f'<link rel="canonical" href="{SITE}/t/{t.no}.html">'
            '<link rel="stylesheet" href="thread.css">'
            "</head><body>"
        )
        parts = [head, _nav(prev_t, next_t)]
        parts.append(
            f'<header class="th-h"><h1>{esc(t.subject)}</h1>'
            f'<p class="sub">Thread {t.no} &middot; {label} UTC &middot; {t.n_posts} posts, '
            f"{t.n_images} images. Archived from 4chan /vrg/; deleted posts are not shown.</p>"
            '<form class="sf" action="../" method="get"><input name="q" type="search" '
            f'placeholder="search all threads" aria-label="search"><button>Search</button></form>'
            "</header>"
        )
        parts.append('<div class="thread">')
        for p in posts:
            bl = sorted(back.get(p[C.NO], ()))
            parts.append(
                _post_html(
                    p,
                    t.no,
                    op_no,
                    thread_of,
                    bl,
                    thumbs.get(p[C.NO]) if not p[C.FDELETED] else None,
                )
            )
        parts.append("</div>")
        parts.append(_nav(prev_t, next_t))
        parts.append('<script src="thread.js" defer></script></body></html>')
        doc = "".join(parts)
        data = doc.encode()
        sizes.append(len(data))
        (out / f"{t.no}.html").write_bytes(data)
        if i % 400 == 0:
            log(f"threads {i}/{len(cor.threads)} {time.time() - t0:.0f}s")
    # thread index
    rows = []
    for t in reversed(cor.threads):
        _, d = fmt_date(t.first_time)
        rows.append(
            f'<tr><td><a href="{t.no}.html">{esc(t.subject)}</a></td><td>{d[:8]}</td>'
            f"<td>{t.n_posts}</td><td>{t.n_images}</td></tr>"
        )
    (out / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>All threads - archive.vrg.party</title>"
        f'<link rel="canonical" href="{SITE}/t/"><link rel="stylesheet" href="thread.css"></head><body>'
        '<nav class="nv"><a href="../">Search</a> <a href="./">Threads</a> '
        '<a href="../about.html">About</a></nav>'
        '<header class="th-h"><h1>/vrg/ threads</h1></header>'
        '<table class="tl"><thead><tr><th>Thread</th><th>Started</th><th>Posts</th><th>Images</th></tr>'
        f"</thead><tbody>{''.join(rows)}</tbody></table></body></html>"
    )
    return {
        "thread_pages": len(sizes),
        "thread_html_total": sum(sizes),
        "thread_html_max": max(sizes) if sizes else 0,
        "thread_html_median": sorted(sizes)[len(sizes) // 2] if sizes else 0,
        "thread_s": time.time() - t0,
    }
