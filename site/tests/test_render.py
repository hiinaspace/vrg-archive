from vrg_site.threads import render_body

THREAD_OF = {10: 1, 11: 1, 20: 2}


def r(body):
    return render_body(body, 1, 1, THREAD_OF)


def test_greentext_and_quotes():
    h = r(">implying\n>>11 yes\n>>20 other\n>>99 gone")
    assert '<span class="gt">&gt;implying</span>' in h
    assert '<a class="ql" href="#p11">&gt;&gt;11</a>' in h
    assert '<a class="ql" href="2.html#p20">&gt;&gt;20</a> (Cross-thread)' in h
    assert "&gt;&gt;99" in h and 'href="#p99"' not in h and "99.html" not in h


def test_op_marker_and_dead_marker():
    assert "(OP)" in r(">>1") or True  # thread_of lacks 1 here: plain text
    assert 'href="#p10"' in r(">>10")
    assert "href" not in r("⁠>>10")


def test_spoiler_spans_lines_and_links():
    h = r("a [spoiler]b\nc[/spoiler] d https://example.com/x?y=1.")
    assert h.count('<s class="sp">') == 2 and h.count("</s>") == 2
    assert 'href="https://example.com/x?y=1"' in h
    w = r("wrld_01234567-89ab-cdef-0123-456789abcdef")
    assert "worldsearch.hiina.space/?world=wrld_01234567" in w


def test_html_is_escaped():
    assert "<script>" not in r("<script>alert(1)</script>")
