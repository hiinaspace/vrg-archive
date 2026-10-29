"""Body-text helpers shared by the index and the thread-page renderer."""

from __future__ import annotations

import re
from collections import Counter

import regex

WJ = "⁠"  # word joiner: prefixes a dead (excluded or missing) quote so it stays plain text
_QUOTE = re.compile(r"(?<!⁠)>>(\d+)")
QUOTE_RE = _QUOTE

_TLDS = [
    "com",
    "net",
    "org",
    "io",
    "gg",
    "me",
    "tv",
    "app",
    "dev",
    "co",
    "jp",
    "moe",
    "party",
    "space",
    "xyz",
    "be",
    "ly",
    "pm",
    "to",
    "st",
    "cc",
    "info",
    "uk",
    "de",
    "fr",
    "ru",
    "us",
    "ca",
    "gl",
    "fm",
    "ai",
    "one",
    "wtf",
    "lol",
    "pub",
    "site",
    "online",
    "cloud",
    "fun",
    "link",
    "social",
    "video",
    "vc",
    "cn",
    "kr",
    "eu",
    "nl",
    "edu",
    "pl",
    "live",
    "rip",
    "bar",
    "club",
    "world",
    "page",
    "art",
    "blog",
    "tech",
    "store",
    "shop",
    "codes",
    "ink",
    "icu",
    "top",
]
_URL = regex.compile(
    r"(?:https?://)?((?:[a-z0-9][a-z0-9-]*\.)+(?:"
    + "|".join(_TLDS)
    + r"))(?::\d+)?(?=[/?#\s)\]>]|$)",
    regex.I,
)
_ALIAS = {
    "youtu.be": "youtube.com",
    "x.com": "twitter.com",
    "fxtwitter.com": "twitter.com",
    "vxtwitter.com": "twitter.com",
    "fixupx.com": "twitter.com",
    "nitter.net": "twitter.com",
}
_SLD = {"co", "com", "org", "net", "ne", "or", "ac"}


def mark_dead_quotes(body: str, live: set[int]) -> str:
    """Prefix U+2060 to every ``>>N`` whose target is not a published post."""
    if ">>" not in body:
        return body
    return _QUOTE.sub(lambda m: m[0] if int(m[1]) in live else WJ + m[0], body)


def registrable(host: str) -> str:
    host = host.lower().removeprefix("www.")
    if host in _ALIAS:
        return _ALIAS[host]
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SLD:
        d = ".".join(parts[-3:])
    else:
        d = ".".join(parts[-2:])
    return _ALIAS.get(d, d)


def domains(body: str) -> set[str]:
    """Registrable domains of the links in a body (scheme optional, known TLDs only)."""
    if "." not in body:
        return set()
    return {registrable(m[1]) for m in _URL.finditer(body)}


def count_domains(bodies_domains: list[set[str]]) -> Counter[str]:
    c: Counter[str] = Counter()
    for ds in bodies_domains:
        c.update(ds)
    return c
