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
    res = {"Results": [{"Rank": str(i)} for i in range(1, 6)]}
    assert stats.is_official({**res, "Competition": {"StatusText": "Official Results"}})
    assert not stats.is_official({**res, "Competition": {"StatusText": "Unofficial Results"}})
    assert not stats.is_official({**res, "Competition": {"StatusText": "Official Start List"}})
    assert not stats.is_official({"Results": [], "Competition": {"StatusText": "Official Results"}})


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


def test_retry_after_error():
    st = {"posts": {"a": {"status": "error", "attempts": 1}, "b": {"status": "error", "attempts": 3}, "c": {"status": "pending"}}}
    assert not tick.finished(st, "a") and tick.finished(st, "b") and tick.finished(st, "c") and not tick.finished(st, "d")


def test_weather_from_ibu():
    class C:
        def weather(self, rid):
            return {"AirTemperature_C": -4, "AirTemperatureDec_C": -4.4, "WeatherCondition": "Overcast",
                    "WindSpeed_KMH": 8, "SnowCondition": "Hard packed variable"}
    assert tick.weather({"race_id": "X", "site_key": None, "start": None}, C()) == "-4 °C · couvert · vent 8 km/h · neige dure"


def test_upcoming_ignores_training_days():
    # Etape A : publiee a partir du 22/11 (entrainements), 1re course le 26/11. Etape B : 1er/12, 1re course le 4/12.
    class C:
        def current_season(self): return "2627"
        def events(self, season, level): return [
            {"EventId": "A", "StartDate": "2026-11-22T00:00:00Z", "EndDate": "2026-11-29T00:00:00Z"},
            {"EventId": "B", "StartDate": "2026-12-01T00:00:00Z", "EndDate": "2026-12-07T00:00:00Z"}]
        def competitions(self, eid): return {
            "A": [{"RaceId": "A1", "DisciplineId": "IN", "catId": "SM", "StartTime": "2026-11-26T15:15:00Z"},
                  {"RaceId": "A2", "DisciplineId": "MS", "catId": "SM", "StartTime": "2026-11-29T13:00:00Z"}],
            "B": [{"RaceId": "B1", "DisciplineId": "SP", "catId": "SM", "StartTime": "2026-12-04T13:00:00Z"}]}[eid]
    at = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=config.TZ)
    assert tick.Season(C(), at("2026-11-25T09:05")).upcoming(days=6)["EventId"] == "A"
    assert tick.Season(C(), at("2026-11-27T13:00")).running()["EventId"] == "A"
    assert tick.Season(C(), at("2026-12-02T09:05")).upcoming(days=6)["EventId"] == "B"
    assert tick.Season(C(), at("2026-11-30T09:05")).just_ended()["EventId"] == "A"


def test_in_form():
    r = lambda ibu, rank, wc=None: {"ibu": ibu, "rank": rank, "wc": wc, "name": ibu, "nat": "NOR"}
    races = [({}, [r("a", 1), r("b", 2), r("c", 3)]), ({}, [r("b", 1), r("a", 5), r("c", 2)])]
    assert stats.in_form(races, set())["ibu"] == "b"          # 75 + 90 = 165 > 90 + 45
    assert stats.in_form(races, {"b"})["ibu"] == "a"          # a et c a 135 pts : a a le meilleur resultat (1er)
    assert stats.in_form([({}, [r("x", 1, wc=50)])], set())["pts"] == 50   # points IBU prioritaires


def test_penalty_counts():
    races = [({"disc": "SP", "penalty_s": 0}, [{"ibu": "a", "rank": 1, "misses_total": 2, "nat": "FRA", "name": "A"},
                                              {"ibu": "b", "rank": 2, "misses_total": 0, "nat": "NOR", "name": "B"}]),
             ({"disc": "IN", "penalty_s": 60}, [{"ibu": "a", "rank": 3, "misses_total": 1, "nat": "FRA", "name": "A"}])]
    r = stats.penalty_counts(races, [({}, [{"nat": "NOR", "penalties": 1}])])
    assert r["nations"][0] == {"nat": "FRA", "tours": 2, "minutes": 1.0}       # individuel = minutes, pas de tour
    assert r["nations"][1]["tours"] == 1                                      # tour de relais compte pour la nation
    a = r["athletes"][0]
    assert (a["tours"], a["minutes"], a["fautes"]) == (2, 1.0, 3)



def test_duel():
    gen = [{"rank": 1, "ibu": "A", "nat": "NOR", "score": 300, "name": "A A", "first": "A", "last": "A"},
           {"rank": 2, "ibu": "B", "nat": "SWE", "score": 250, "name": "B B", "first": "B", "last": "B"},
           {"rank": 3, "ibu": "C", "nat": "FRA", "score": 200, "name": "C C", "first": "C", "last": "C"}]
    r = lambda ibu, rank: {"ibu": ibu, "rank": rank, "shots": 20, "misses_total": 2, "ski": (None, rank)}
    races = [({}, [r("A", 1), r("C", 2)]), ({}, [r("C", 1), r("A", 4)]), ({}, [r("A", 2)])]
    d = stats.duel(gen, races)
    assert d["b"]["ibu"] == "C" and d["rule"] == "fr" and d["gap"] == 100
    assert d["h2h"] == [1, 1] and d["a"]["wins"] == 1 and d["a"]["podiums"] == 2
    gen[0]["nat"] = "FRA"
    d = stats.duel(gen, races)
    assert d["b"]["ibu"] == "B" and d["rule"] == "2e"

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
