"""Sonde 8 : donnees d'un relais (resultats par relayeur, temps par tour, tirs, pioches)."""
import json
import sys

sys.path.insert(0, ".")
from tdp.ibu import Client  # noqa: E402

c = Client()
rid = None
for season in ("2526",):
    for ev in c.events(season):
        for comp in c.competitions(ev["EventId"]):
            if comp.get("DisciplineId") == "RL" and comp.get("StatusText") == "Final":
                rid = comp["RaceId"]; break
        if rid: break
print("RACE", rid)
res = c.get("Results", RaceId=rid)
rows = res["Results"]
team = next(r for r in rows if r.get("IsTeam"))
legs = [r for r in rows if not r.get("IsTeam") and r.get("Nat") == team.get("Nat")]
print("TEAM", json.dumps(team, ensure_ascii=False)[:1500])
for l in legs[:4]:
    print("LEG", json.dumps(l, ensure_ascii=False)[:1200])
for t in ["LAP1", "LAP2", "LAP3", "LAP12", "CRS1", "RNG1", "STTM", "CRST", "RNGT", "FINN"]:
    try:
        a = c.get("AnalyticResults", RaceId=rid, TypeId=t)
    except Exception as exc:  # noqa: BLE001
        print(t, "ERR", exc); continue
    rr = a.get("Results") or []
    print(t, len(rr), json.dumps(rr[:2], ensure_ascii=False)[:700])
