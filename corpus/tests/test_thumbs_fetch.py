import base64
import io
import json
from pathlib import Path

from PIL import Image

from vrg_corpus import thumbs_fetch as tf


def jpeg(w=4, h=3) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), (200, 10, 10)).save(b, "JPEG")
    return b.getvalue()


def test_md5_path_and_b64():
    md5 = "7fecf7d49380442308bb8c118277771a"
    assert tf.md5_path(Path("/s"), md5) == Path(f"/s/raw/7f/{md5}.jpg")
    assert tf.b64_to_hex("f+z31JOARCMIu4wRgnd3Gg==") == md5
    assert tf.b64_to_hex("!!") is None


def test_verify_jpeg():
    assert tf.verify_jpeg(jpeg(), 4, 3) == (4, 3, "")
    assert tf.verify_jpeg(jpeg(), None, None)[2] == ""
    assert "size" in tf.verify_jpeg(jpeg(), 5, 3)[2]
    assert "undecodable" in tf.verify_jpeg(b"junk", 4, 3)[2]
    b = io.BytesIO()
    Image.new("RGB", (4, 3)).save(b, "PNG")
    assert "format" in tf.verify_jpeg(b.getvalue(), 4, 3)[2]


class FakeClient:
    def __init__(self, body: bytes, status: int = 200):
        self.body, self.status = body, status

    def get(self, path):
        return self.status, self.body


def test_load_thread():
    md5 = "7fecf7d49380442308bb8c118277771a"
    media = {
        "media_hash": base64.b64encode(bytes.fromhex(md5)).decode(),
        "thumb_link": "https://arch.b4k.dev/media/vg/thumb/1/2/3s.jpg",
        "preview_w": "116",
        "preview_h": "125",
        "banned": "0",
    }
    j = {"10": {"op": {"media": None}, "posts": {"11": {"media": media}, "12": {"media": None}}}}
    st, _, rows = tf.load_thread(FakeClient(json.dumps(j).encode()), 10, [(11, md5), (12, md5)])
    assert st == "ok"
    assert rows[0][6] == "pending" and rows[0][4:6] == (116, 125)
    assert rows[1][6] == "nolink"
    # md5 disagreement with the corpus is never fetched
    _, _, rows = tf.load_thread(FakeClient(json.dumps(j).encode()), 10, [(11, "0" * 32)])
    assert rows[0][6] == "bad"
    st, _, rows = tf.load_thread(FakeClient(b'{"error":"Thread not found."}'), 10, [(11, md5)])
    assert st == "notfound" and rows[0][6] == "nolink"


def test_fetch_one_dup_and_ok(tmp_path):
    md5 = "ab" + "0" * 30
    c = FakeClient(jpeg())
    st, _, n, _ = tf.fetch_one(c, tmp_path, 1, md5, "https://arch.b4k.dev/x.jpg", 4, 3)
    assert st == "ok" and tf.md5_path(tmp_path, md5).exists() and n > 0
    st, *_ = tf.fetch_one(c, tmp_path, 2, md5, "https://arch.b4k.dev/x.jpg", 4, 3)
    assert st == "dup"
    st, *_ = tf.fetch_one(
        FakeClient(b"", 404), tmp_path, 3, "cd" + "0" * 30, "https://arch.b4k.dev/y", 1, 1
    )
    assert st == "404"
