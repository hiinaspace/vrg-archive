"""Regenerate tok_vectors.json (run by hand after an intentional tokenizer change)."""

import json
from pathlib import Path

from vrg_site import tok

INPUTS = [
    "Quest 3 headsets are 2x better than the Index",
    ">>12345678 who asked? [spoiler]Boxes and glasses[/spoiler]",
    "https://www.youtube.com/watch?v=abc123 and www.rentry.org/vrghmds",
    "ミラーワールド is fun. 睡眠 sleep 日本語のテキスト",
    "ＦＵＬＬＷＩＤＴＨ ｶﾀｶﾅ Straße naïve café",
    "it's don't half-life e621.net wrld_01234567-89ab-cdef-0123-456789abcdef",
    "status lens bus virus analysis class glass movies stories boxes",
    "한국어 텍스트 vrchat's 😀 emoji",
    "⁠>>99 dead quote stays out",
    "",
]
GREEN = ">implying\n>>123 reply\nplain\n>another green"

out = {
    "tokens": [[s, tok.tokens(s)] for s in INPUTS],
    "stem": [
        [w, tok.stem(w)]
        for w in [
            "headsets",
            "headset",
            "glasses",
            "glass",
            "boxes",
            "movies",
            "status",
            "lens",
            "bus",
            "ab",
            "abc",
            "abcs",
            "q3s",
        ]
    ],
    "green": [GREEN, tok.greentext(GREEN)],
    "fnv": [[s, tok.fnv1a16(s)] for s in ["vrchat", "ミラー", "\u0001impl", "😀x", ""]],
}
Path(__file__).with_name("tok_vectors.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1)
)
