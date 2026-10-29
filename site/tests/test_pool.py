import sqlite3
from pathlib import Path

from vrg_site import thumbs

JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffc0000b080003000401011100ffd9"
)  # SOF0 only: enough for jpeg_size (4x3)


def test_pool_packing(tmp_path: Path):
    pool = tmp_path / "pool"
    for md5, body in (("aa" + "0" * 30, JPEG + b"1"), ("bb" + "0" * 30, JPEG + b"22")):
        d = pool / "raw" / md5[:2]
        d.mkdir(parents=True)
        (d / f"{md5}.jpg").write_bytes(body)
    st = sqlite3.connect(pool / "state.sqlite")
    st.execute("CREATE TABLE thumb (no INTEGER, md5 TEXT, status TEXT)")
    st.executemany(
        "INSERT INTO thumb VALUES (?,?,?)",
        [(1, "aa" + "0" * 30, "ok"), (2, "aa" + "0" * 30, "dup"), (3, "bb" + "0" * 30, "404")],
    )
    st.commit()
    st.close()
    snap = tmp_path / "s.sqlite"
    c = sqlite3.connect(snap)
    c.execute("CREATE TABLE posts (no INTEGER PRIMARY KEY, thumbnail BLOB)")
    c.execute("INSERT INTO posts VALUES (9, ?)", (JPEG,))
    c.commit()
    c.close()
    have = thumbs.pool_md5s(pool / "state.sqlite")
    assert have == {"aa" + "0" * 30}
    md5 = {1: "aa" + "0" * 30, 2: "aa" + "0" * 30, 3: "bb" + "0" * 30, 4: "aa" + "0" * 30}
    # post 4 is not wanted (deleted upstream): it must get nothing
    loc, stats = thumbs.pack(snap, {1, 2, 3, 9}, tmp_path / "out", pool, md5, have)
    assert set(loc) == {1, 2, 9}
    assert loc[1] == loc[2]  # repost shares one copy
    assert stats["thumb_blob_posts"] == 1 and stats["thumb_pool_posts"] == 2
    assert loc[1][3:] == (4, 3)
    pk = (tmp_path / "out" / f"pack{loc[1][0]}.bin").read_bytes()
    assert pk[loc[1][1] : loc[1][1] + loc[1][2]] == JPEG + b"1"
