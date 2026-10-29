import json
from pathlib import Path

from vrg_site import tok

V = json.loads((Path(__file__).parent / "tok_vectors.json").read_text())


def test_tokens_match_vectors():
    for s, want in V["tokens"]:
        assert tok.tokens(s) == want, s


def test_stem_and_hash_match_vectors():
    for w, want in V["stem"]:
        assert tok.stem(w) == want
    for s, want in V["fnv"]:
        assert tok.fnv1a16(s) == want
    assert tok.greentext(V["green"][0]) == V["green"][1]


def test_semantics():
    assert tok.tokens("Quest 3 headsets") == ["quest", "3", "headset"]
    assert tok.tokens(">>123 hello") == ["hello"]
    assert tok.tokens("[spoiler]x[/spoiler]") == ["x"]
    assert tok.tokens("ミラー") == ["ミラ", "ラー"]
