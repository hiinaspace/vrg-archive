"""Tokenizer shared (by contract) with web/src/tok.ts. Keep the two in sync.

Adapted from worldsearch (vrcwscrape search/build/tok.py, WTFPL). Terms are
NFKC-lowercased latin/digit words and CJK bigrams. ``>>N`` quote numbers and
``[spoiler]`` markers never reach the index. Latin words get a tiny plural
stemmer so "headsets" finds "headset".
"""

from __future__ import annotations

import unicodedata

import regex

CJK = "々-〇぀-ヿㇰ-ㇿ㐀-䶿一-鿿豈-﫿가-힯\U00020000-\U0002fa1f"
WORD = r"[\p{L}\p{N}\p{M}]"
_TOK = regex.compile(rf"([{CJK}]+)|((?:(?![{CJK}]){WORD})+)")
# a live ``>>N`` quote, a dead one (U+2060-prefixed by the build), spoiler tags, URL schemes
_STRIP = regex.compile(r"⁠?>>\d+|\[/?spoiler\]|https?://|www\.")

# field channels share the shard files; the first character separates them
CH_GREEN = "\u0001"
CH_NAME = "\u0002"
CH_TRIP = "\u0003"
CH_FILE = "\u0004"
MARKS = (CH_GREEN, CH_NAME, CH_TRIP, CH_FILE)
MAX_WORD = 32

CONFUSABLES = str.maketrans({"‚": ",", "․": "."})


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower().translate(CONFUSABLES)


def stem(w: str) -> str:
    """Plural folding for ASCII alphabetic words of 4+ letters. Mirrors stem() in tok.ts."""
    if len(w) < 4 or not (w.isascii() and w.isalpha()):
        return w
    if w.endswith(("sses", "xes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def clean(text: str) -> str:
    return _STRIP.sub(" ", text)


def tokens(text: str) -> list[str]:
    """Index tokens of a post body (or any field)."""
    out: list[str] = []
    for m in _TOK.finditer(norm(clean(text))):
        cjk, word = m.group(1), m.group(2)
        if cjk is not None:
            if len(cjk) == 1:
                out.append(cjk)
            else:
                out.extend(cjk[i : i + 2] for i in range(len(cjk) - 1))
        else:
            out.append(stem(word[:MAX_WORD]))
    return out


def greentext(body: str) -> str:
    """Greentext lines of a body ('>' but not '>>'), newline-joined."""
    return "\n".join(
        ln for ln in body.split("\n") if ln.startswith(">") and not ln.startswith(">>")
    )


def fnv1a16(s: str) -> int:
    """FNV-1a 32 over UTF-16 code units (matches the JS charCodeAt loop)."""
    h = 0x811C9DC5
    b = s.encode("utf-16-le")
    for i in range(0, len(b), 2):
        h ^= b[i] | (b[i + 1] << 8)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def bucket_of(term: str, nbuckets: int) -> int:
    return fnv1a16(term) % nbuckets
