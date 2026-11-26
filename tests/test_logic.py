"""Tests rapides : python -m pytest tests/ (ou python tests/test_logic.py)."""
import datetime as dt
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["TDP_DRY_RUN"] = "1"
from tdp import config, publish, stats, tick  # noqa: E402


def test_parse_time():
    assert stats.parse_time("24:31.4") == 24 * 60 + 31.4
    assert stats.parse_time("+1:02.5") == 62.5
    assert stats.parse_time("1:02:03.0") == 3723.0
    assert stats.parse_time("") is None


def test_ordinals_and_names():
    assert stats.ordinal(1) == "1er" and stats.ordinal_f(1) == "1re" and stats.ordinal(3) == "3e"
    assert stats.person({"FamilyName": "FILLON MAILLET", "GivenName": "Quentin"}) == ("Quentin", "Fillon Maillet")
    assert stats.person({"FamilyName": "JEANMONNOT-LAURENT", "GivenName": "X"})[1] == "Jeanmonnot-Laurent"


def test_movers():
    before = {"a": 1, "b": 2, "c": 10}
    after = [{"ibu": "b", "rank": 1, "name": "B", "nat": "FRA"}, {"ibu": "a", "rank": 2, "name": "A", "nat": "NOR"}, {"ibu": "c", "rank": 3, "name": "C", "nat": "SWE"}]
    m = stats.movers(before, after)
    assert [d["ibu"] for d in m["up"]] == ["c", "b"] and m["down"][0]["ibu"] == "a"


def test_official_status():
    assert stats.is_official({"Competition": {"StatusText": "Official"}})
    assert not stats.is_official({"Competition": {"StatusText": "Unofficial"}})


def test_approval_flow(monkeypatch=None):
    now = dt.datetime(2026, 12, 17, 15, 0, tzinfo=config.TZ)
    tick.NOW = now
    st = {"posts": {"post:X": {"status": "pending", "urls": ["u1"], "caption": "c", "expires": (now + dt.timedelta(hours=1)).isoformat()},
                    "post:Y": {"status": "pending", "urls": ["u2"], "caption": "c", "expires": (now - dt.timedelta(hours=1)).isoformat()}},
          "tg_offset": 0}
    orig = publish.read_decisions
    publish.read_decisions = lambda off: ([("ok", "post:X")], off + 1)
    try:
        tick.handle_decisions(st, now)
    finally:
        publish.read_decisions = orig
    assert st["posts"]["post:X"]["status"] == "published"
    assert st["posts"]["post:Y"]["status"] == "expired"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
