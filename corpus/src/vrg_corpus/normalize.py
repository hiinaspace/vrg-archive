"""Field-level normalization of both sources into one `Post` shape.

Source kinds (the ``source`` column):
  legacy - parquet rows with subnum IS NULL: 4chan API HTML (entities, <br>, spans). Carries no
           deleted flag, no spoiler flag (media_spoiler is junk, see schema-diff.md), no thumb.
  b4k    - plain-text foolfuuka rows: parquet rows with subnum = 0, and live-DB rows with
           capcode = 'N' (the scraper's b4k backfill).
  live   - live-DB rows from the 4chan API (capcode NULL): HTML, real deleted flags.
"""

from __future__ import annotations

import base64
import binascii
import html
import re
from collections import Counter
from typing import Any, NamedTuple

from . import html2text

CUTOFF = 520649835  # first live post; parquet is authoritative below, live DB from here
DEFAULT_NAME = "Anonymous"

# foolfuuka capcode letters -> the 4chan API words the live HTML rows use
CAPCODES = {
    "N": None,
    "": None,
    "M": "mod",
    "A": "admin",
    "D": "developer",
    "V": "verified",
    "F": "founder",
    "G": "manager",
    "mod": "mod",
    "admin": "admin",
    "admin_highlight": "admin",
    "manager": "manager",
    "developer": "developer",
    "founder": "founder",
}

# Some backfilled (capcode 'N') rows from 2026-05 hold raw 4chan HTML instead of foolfuuka text.
HTML_SIGNS = re.compile(r"<br>|</a>|</span>|<wbr>|&gt;|&#039;|&quot;")

QUOTE_RE = re.compile(r">>(\d{7,12})")


class Post(NamedTuple):
    no: int
    thread_no: int
    time: int
    name: str
    trip: str | None
    capcode: str | None
    sub: str | None
    body: str
    file_name: str | None
    file_ext: str | None
    file_w: int | None
    file_h: int | None
    file_size: int | None
    file_md5: str | None
    file_spoiler: int | None
    file_deleted: int
    deleted: int
    source: str


POST_COLS = Post._fields


class Counters:
    """Things worth reporting from a build; mutated by the normalizers."""

    def __init__(self) -> None:
        self.html = html2text.Stats()
        self.capcode_unknown: Counter[str] = Counter()
        self.bad_md5 = 0
        self.ghosts = 0
        self.empty_name = 0
        self.ext_mismatch = 0
        self.rows: Counter[str] = Counter()


def md5_hex(b64: str | None, c: Counters) -> str | None:
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        c.bad_md5 += 1
        return None
    if len(raw) != 16:
        c.bad_md5 += 1
        return None
    return raw.hex()


def capcode(v: str | None, c: Counters) -> str | None:
    if v is None:
        return None
    if v in CAPCODES:
        return CAPCODES[v]
    c.capcode_unknown[v] += 1
    return v


def text_field(v: str | None, is_html: bool) -> str | None:
    if v is None or v == "":
        return None
    return html.unescape(v) if is_html else v


def _int(v: Any) -> int | None:
    return None if v is None else int(v)


def split_filename(full: str | None, ext: str | None, c: Counters) -> tuple[str | None, str | None]:
    """parquet media_filename is 'name.ext'; return (name, '.ext' lowercase)."""
    if not full:
        return None, None
    if ext is None:
        i = full.rfind(".")
        if i <= 0:
            return full, None
        return full[:i], full[i:].lower()
    if full.lower().endswith(ext.lower()):
        return full[: -len(ext)], ext.lower()
    c.ext_mismatch += 1
    return full, ext.lower()


def from_parquet(r: dict[str, Any], c: Counters) -> Post | None:
    """r is a parquet row as a dict. Returns None for ghost posts (subnum > 0)."""
    sub_num = r["subnum"]
    if sub_num:
        c.ghosts += 1
        return None
    plain = sub_num == 0
    src = "b4k" if plain else "legacy"
    no = int(r["post_num"])
    comment = r["comment"]
    if comment is None:
        body = ""
    elif plain:
        body = comment
    else:
        body = html2text.convert(comment, c.html, ref=no)
    name = text_field(r["name"], not plain)
    if name is None:
        c.empty_name += 1
        name = DEFAULT_NAME
    fname = text_field(r["media_filename"], not plain)
    file_name, file_ext = split_filename(fname, None, c)
    has_file = file_name is not None
    return Post(
        no=no,
        thread_no=int(r["thread_num"]),
        time=int(r["timestamp"]),
        name=name,
        trip=text_field(r["trip"], not plain),
        capcode=capcode(r["capcode"], c),
        sub=text_field(r["thread_title"], not plain) if r["is_op"] else None,
        body=body,
        file_name=file_name,
        file_ext=file_ext,
        file_w=_int(r["media_w"]),
        file_h=_int(r["media_h"]),
        file_size=_int(r["media_size"]),
        file_md5=md5_hex(r["media_hash"], c),
        # legacy media_spoiler is 1 on every OP and NULL elsewhere: not a real flag
        file_spoiler=_int(r["media_spoiler"]) if plain and has_file else None,
        file_deleted=0,
        deleted=int(r["deleted"] or 0) if plain else 0,
        source=src,
    )


def from_live(r: dict[str, Any], c: Counters) -> Post:
    """r is a live posts row. capcode 'N' marks b4k-backfilled rows (plain text, usually)."""
    backfilled = r["capcode"] == "N"
    plain = backfilled and not (r["com"] and HTML_SIGNS.search(r["com"]))
    if backfilled and not plain:
        c.rows["backfill_html"] += 1
    no = int(r["no"])
    com = r["com"]
    if com is None:
        body = ""
    elif plain:
        body = com
    else:
        body = html2text.convert(com, c.html, ref=no)
    name = text_field(r["name"], not plain)
    if name is None:
        c.empty_name += 1
        name = DEFAULT_NAME
    has_file = r["tim"] is not None
    file_name = file_ext = None
    if has_file:
        fname = text_field(r["filename"], not plain)
        file_ext = (r["ext"] or "").lower() or None
        file_name = fname
    return Post(
        no=no,
        thread_no=int(r["thread_op_id"]),
        time=int(r["time"]),
        name=name,
        trip=text_field(r["trip"], not plain),
        capcode=capcode(r["capcode"], c),
        sub=text_field(r["sub"], not plain) if r["resto"] == 0 else None,
        body=body,
        file_name=file_name,
        file_ext=file_ext,
        file_w=_int(r["w"]),
        file_h=_int(r["h"]),
        file_size=_int(r["fsize"]),
        file_md5=md5_hex(r["md5"], c),
        # custom_spoiler is the OP-only "number of custom spoilers on the board" field, not a flag
        file_spoiler=int(r["spoiler"] or 0) if has_file else None,
        file_deleted=int(r["filedeleted"] or 0),
        deleted=int(r["is_deleted"] or 0),
        source="b4k" if backfilled else "live",
    )


def quotes(body: str) -> list[int]:
    """Distinct `>>N` targets in order of appearance. `>>>/board/N` has no digits after `>>`."""
    seen: dict[int, None] = {}
    for m in QUOTE_RE.finditer(body):
        seen.setdefault(int(m.group(1)), None)
    return list(seen)
