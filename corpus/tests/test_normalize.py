from vrg_corpus import normalize
from vrg_corpus.normalize import Counters

PQ = dict(
    post_num=1,
    thread_num=1,
    thread_title=None,
    subnum=None,
    is_op=0,
    timestamp=1500000000,
    timestamp_expired=None,
    capcode=None,
    name="Anonymous",
    trip=None,
    comment="a&#039;b<br>&gt;c",
    deleted=0,
    media_filename="9kdUkGU.JPG",
    media_w=2048.0,
    media_h=1367.0,
    media_size=146396.0,
    media_hash="nhdlbXYagvu2uUHkom3x/w==",
    media_spoiler=None,
)


def test_legacy_row():
    c = Counters()
    p = normalize.from_parquet(dict(PQ), c)
    assert p is not None
    assert p.body == "a'b\n>c"
    assert (p.file_name, p.file_ext) == ("9kdUkGU", ".jpg")
    assert len(p.file_md5 or "") == 32 and p.file_md5 == p.file_md5.lower()
    assert p.file_size == 146396 and p.file_w == 2048
    assert p.source == "legacy" and p.deleted == 0 and p.file_spoiler is None


def test_legacy_op_spoiler_flag_is_ignored():
    # every legacy OP has media_spoiler=1: it is the OP-only custom_spoiler count, not a flag
    p = normalize.from_parquet(dict(PQ, is_op=1, thread_title="T", media_spoiler=1), Counters())
    assert p and p.file_spoiler is None and p.sub == "T"


def test_plain_row_kept_verbatim_and_flags_trusted():
    row = dict(PQ, subnum=0, capcode="N", comment="x &amp; y\n>z", media_spoiler=1, deleted=1)
    p = normalize.from_parquet(row, Counters())
    assert p and p.body == "x &amp; y\n>z"  # not unescaped: plain rows are already text
    assert p.capcode is None and p.source == "b4k"
    assert p.file_spoiler == 1 and p.deleted == 1


def test_ghost_post_skipped():
    c = Counters()
    assert normalize.from_parquet(dict(PQ, subnum=3), c) is None and c.ghosts == 1


def test_default_name():
    c = Counters()
    p = normalize.from_parquet(dict(PQ, name=None), c)
    assert p and p.name == "Anonymous" and c.empty_name == 1


LIVE = dict(
    no=520650000,
    thread_op_id=520649835,
    resto=520649835,
    time=1743945000,
    name="Anonymous",
    trip=None,
    capcode=None,
    sub=None,
    com="&gt;&gt;1234567<br>hi",
    is_deleted=0,
    tim=1743945000123,
    filename="a&amp;b",
    ext=".PNG",
    fsize=10,
    md5="nhdlbXYagvu2uUHkom3x/w==",
    w=1,
    h=2,
    filedeleted=0,
    spoiler=0,
    custom_spoiler=None,
)


def test_live_html_row():
    p = normalize.from_live(dict(LIVE), Counters())
    assert p.body == ">>1234567\nhi" and p.source == "live"
    assert (p.file_name, p.file_ext, p.file_spoiler) == ("a&b", ".png", 0)


def test_live_custom_spoiler_is_not_a_spoiler_flag():
    p = normalize.from_live(dict(LIVE, resto=0, custom_spoiler=1, sub="t&amp;u"), Counters())
    assert p.file_spoiler == 0 and p.sub == "t&u"


def test_live_backfill_row_plain_vs_html():
    plain = normalize.from_live(dict(LIVE, capcode="N", com="x &amp; y"), Counters())
    assert plain.body == "x &amp; y" and plain.source == "b4k"
    c = Counters()
    html_row = normalize.from_live(dict(LIVE, capcode="N", com="it&#039;s<br>ok"), c)
    assert html_row.body == "it's\nok" and html_row.source == "b4k"
    assert c.rows["backfill_html"] == 1


def test_quotes():
    body = ">>12345678\n>>>/trash/25327945\n>>12345678 >>87654321\n>>1\n>>>/vg/vrg"
    assert normalize.quotes(body) == [12345678, 87654321]


def test_capcode_unknown_reported():
    c = Counters()
    assert normalize.capcode("Z", c) == "Z" and c.capcode_unknown["Z"] == 1
    assert normalize.capcode("N", c) is None and normalize.capcode("mod", c) == "mod"
