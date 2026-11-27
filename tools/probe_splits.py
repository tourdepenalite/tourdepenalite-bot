"""Sonde 2 : coherence des temps par tour / par tir (CRSn, RNGn, STTn) avec le temps total."""
import json
import sys

sys.path.insert(0, ".")
from tdp.ibu import Client  # noqa: E402

c = Client()
TYPES = ["CRST", "RNGT", "STTM", "FINN", "SKIT"] + [f"{p}{i}" for p in ("CRS", "RNG", "STT", "PEN", "PNL", "PRN", "LAP", "INT", "FIN") for i in range(1, 6)] + ["PENT", "PNLT", "PRNT", "LAPT"]


def races(season, discs):
    out = {}
    for ev in c.events(season):
        for comp in c.competitions(ev["EventId"]):
            d = comp.get("DisciplineId")
            if d in discs and d not in out and comp.get("StatusText") == "Final":
                out[d] = comp["RaceId"]
    return out


todo = races("2627", {"IN", "SP", "PU", "MS"})
prev = races("2526", {"SP", "PU", "MS", "IN"})
for d, r in prev.items():
    todo.setdefault(d, r)
print("RACES", json.dumps(todo))
for d, rid in todo.items():
    res = c.get("Results", RaceId=rid)
    rows = [x for x in res["Results"] if x.get("Rank")][:4]
    comp = res.get("Competition") or {}
    print(f"\n=== {d} {rid} start={comp.get('StartMode')} shootings={comp.get('NrShootings')} pos={comp.get('ShootingPositions')} pen={comp.get('PenaltySeconds')}")
    data = {}
    for t in TYPES:
        try:
            a = c.get("AnalyticResults", RaceId=rid, TypeId=t)
        except Exception:
            continue
        rr = a.get("Results") or []
        if rr:
            data[t] = {x.get("IBUId"): (x.get("Result") or x.get("TotalTime"), x.get("Rank"), x.get("Behind")) for x in rr}
    print("TYPES", sorted(data))
    for x in rows:
        i = x["IBUId"]
        print(f"- {x['Rank']} {x['ShortName']} total={x['TotalTime']} shoot={x['Shootings']} start={x.get('StartTime')} pursuitDist={x.get('PursuitStartDistance')}")
        print("   ", " | ".join(f"{t}={data[t].get(i, ('-',))[0]}/{data[t].get(i, ('', '-'))[1]}" for t in data))
