"""Convert 4chan API comment HTML to foolfuuka-style plain text.

Conventions (verified against the 65,399 b4k-sourced plain-text rows in the parquet):
  <br> -> newline, <wbr> -> nothing, entities unescaped, quotelink/deadlink anchors -> their
  text (">>N", ">>>/board/N"), greentext spans -> raw ">" lines (the ">" is already in the
  text), <s> -> [spoiler]...[/spoiler], <pre class="prettyprint"> -> [code]...[/code].
  The result is stripped (b4k rows never have leading/trailing whitespace or CR).

Known 4chan-injected decorations (like-perk badges, April Fools wrappers, emote images) are
dropped. Any other tag is stripped but recorded in ``Stats.unknown`` so it shows up in the
build report; ``strict=True`` raises instead.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field

TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)((?:\s[^<>]*?)?)\s*(/?)>")
CLASS_RE = re.compile(r'class="([^"]*)"')

# Elements whose whole content is dropped (4chan-injected decoration, not post text).
DROP_CLASSES = {"like-perk-cnt", "xa24desu", "xa23b", "xa23t", "xa23i"}
# Elements whose tag is stripped but whose text is kept.
PASS_CLASSES = {"quote", "deadlink", "fortune", "quotelink", "xae"}
PASS_TAGS = {"a", "span", "b", "strong", "i", "em", "u", "div"}
VOID_TAGS = {"br", "wbr", "img"}


class UnknownMarkup(ValueError):
    pass


@dataclass
class Stats:
    """Counts of what the converter saw, for the build report."""

    tags: Counter = field(default_factory=Counter)  # known tags handled
    dropped: Counter = field(default_factory=Counter)  # decoration elements removed
    unknown: Counter = field(default_factory=Counter)  # unrecognised (tag, class) keys
    unknown_examples: dict = field(default_factory=dict)


def _classes(attrs: str) -> set[str]:
    m = CLASS_RE.search(attrs)
    return set(m.group(1).split()) if m else set()


def convert(raw: str, stats: Stats | None = None, strict: bool = False, ref: int = 0) -> str:
    """Convert comment HTML to plain text. ``ref`` is the post number, for error reports."""
    st = stats if stats is not None else Stats()
    out: list[str] = []
    stack: list[tuple[str, str | None]] = []  # (tag, close_text or "DROP")
    drop_depth = 0
    pos = 0

    def emit(s: str) -> None:
        if drop_depth == 0 and s:
            out.append(s)

    for m in TAG_RE.finditer(raw):
        if m.start() > pos:
            emit(html.unescape(raw[pos : m.start()]))
        pos = m.end()
        closing, tag, attrs, selfclose = (
            m.group(1) == "/",
            m.group(2).lower(),
            m.group(3),
            m.group(4),
        )
        if closing:
            # find the nearest matching open tag
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    _, close = stack[i]
                    del stack[i:]
                    if close == "DROP":
                        drop_depth -= 1
                    elif close:
                        emit(close)
                    break
            continue
        classes = _classes(attrs)
        if tag == "br":
            emit("\n")
            st.tags["br"] += 1
        elif tag == "wbr":
            st.tags["wbr"] += 1
        elif tag == "img":
            if drop_depth == 0:
                st.dropped["img"] += 1
        elif tag == "s":
            emit("[spoiler]")
            stack.append((tag, "[/spoiler]"))
            st.tags["s"] += 1
        elif tag == "pre" and "prettyprint" in classes:
            emit("[code]")
            stack.append((tag, "[/code]"))
            st.tags["pre.prettyprint"] += 1
        elif classes & DROP_CLASSES and tag in ("div", "span"):
            if drop_depth == 0:
                st.dropped[f"{tag}.{sorted(classes & DROP_CLASSES)[0]}"] += 1
            drop_depth += 1
            stack.append((tag, "DROP"))
        elif tag in PASS_TAGS and (tag not in ("span", "div") or classes <= PASS_CLASSES):
            stack.append((tag, None))
            key = tag + ("." + ".".join(sorted(classes)) if classes else "")
            st.tags[key] += 1
        else:
            key = tag + ("." + ".".join(sorted(classes)) if classes else "")
            if drop_depth == 0:
                if strict:
                    raise UnknownMarkup(f"post {ref}: unknown tag {m.group(0)!r}")
                st.unknown[key] += 1
                st.unknown_examples.setdefault(key, ref)
            if tag not in VOID_TAGS and not selfclose:
                stack.append((tag, None))
    if pos < len(raw):
        emit(html.unescape(raw[pos:]))
    return "".join(out).replace("\r", "").strip()
