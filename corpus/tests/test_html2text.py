"""Tests on real sampled rows (tests/fixtures_rows.json) plus a few synthetic forms."""

import json
from pathlib import Path

import pytest

from vrg_corpus import html2text
from vrg_corpus.html2text import Stats, UnknownMarkup, convert

ROWS = {r["no"]: r for r in json.loads((Path(__file__).parent / "fixtures_rows.json").read_text())}


def conv(no: int) -> str:
    return convert(ROWS[no]["raw"], Stats(), ref=no)


def test_greentext_spans_become_raw_lines():
    out = conv(148716486)
    assert out.endswith(
        ">no 'hurr durr gimmick' allowed\n"
        ">no 'mines better than urs' allowed\n"
        ">no 'hurr durr screen on face' allowed"
    )


def test_quotelink_and_entities_and_wbr():
    out = conv(243059963)
    assert out.startswith(">>243023540\nOh boy I've been")
    assert "\\ Space\\ Force" in out  # backslashes untouched
    assert "yuv420p" in out  # <wbr> inside "yuv42<wbr>0p" dropped
    assert "[code]" in out  # literal user-typed [code], no tag involved


def test_spoiler_tag():
    assert conv(520719905) == ">>520719768\n[spoiler]I do that unironically very often. [/spoiler]"


def test_deadlink_is_plain_quote():
    assert conv(520720291).startswith(">>520719309\nOLED > LCD\n")


def test_entities_unescaped_once():
    assert conv(521488367).count('"join on <X>"') == 1


def test_external_link_text_kept_wbr_removed():
    assert (
        conv(521518359)
        == ">>521516187\nhttps://boards.4chan.org/vg/catalog#s=/vrg/\nYou're welcome"
    )
    assert conv(201534763).endswith("\nhttp://i.4cdn.org/wsg/1515711568276.webm")


def test_fortune_keeps_text_drops_markup():
    assert conv(248793531) == ">>248793168\n>>248793369\n\nYour fortune: Average Luck"


@pytest.mark.parametrize("no", [248800986, 248833381, 471761217, 424283256, 248867583])
def test_injected_decoration_dropped(no):
    st = Stats()
    out = convert(ROWS[no]["raw"], st, ref=no)
    assert "<" not in out and "class" not in out
    assert not st.unknown  # the marquee inside like-perk-cnt is dropped, not "unknown"
    assert st.dropped


def test_emote_image_dropped_emoji_span_kept():
    assert conv(378414241) == ">>378408743\n\nwish I could've been there pypybros"
    assert conv(378498256) == "\U0001f62d" * 3


def test_numeric_entity_emoji():
    assert convert("a &#x1F62D; b") == "a \U0001f62d b"


def test_live_op_with_headings():
    out = conv(520649835)
    assert out.startswith('"Virtual Reality, Real Suffering"\nReady For Launch Edition\n')
    assert "\n>Game Resources\n" in out
    assert ">>>/vg/vrg" in out  # cross-board link text preserved
    assert ">>520375384" in out


def test_backfilled_html_row_converts():
    assert conv(566500046) == ">>566499729\nlmao hahaha"


def test_pre_prettyprint_to_code():
    # no such row exists in the /vrg/ corpus (checked: 0 occurrences); synthetic form
    assert convert('x<br><pre class="prettyprint">a\nb</pre>') == "x\n[code]a\nb[/code]"


def test_unknown_tag_is_reported_not_silent():
    st = Stats()
    out = convert("hi <blink>there</blink>", st, ref=7)
    assert out == "hi there"
    assert st.unknown == {"blink": 1} and st.unknown_examples["blink"] == 7
    with pytest.raises(UnknownMarkup):
        convert("hi <blink>x</blink>", strict=True, ref=7)


def test_module_exports():
    assert html2text.TAG_RE
