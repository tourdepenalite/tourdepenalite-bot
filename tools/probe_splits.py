"""Sonde 3 : donnees compactes de l'individuel hommes de Kontiolahti, pour le prototype de Reel."""
import json
import sys

sys.path.insert(0, ".")
from tdp.ibu import Client  # noqa: E402

c = Client()
RID = "BT2627SWRLCP01SMIN"
res = c.get("Results", RaceId=RID)
types = [f"LAP{i}" for i in range(1, 6)] + [f"CRS{i}" for i in range(1, 6)] + [f"RNG{i}" for i in range(1, 5)]
an = {}
for t in types:
    an[t] = {x["IBUId"]: x.get("Result") or x.get("TotalTime") for x in c.get("AnalyticResults", RaceId=RID, TypeId=t).get("Results") or []}
rows = []
for x in res["Results"]:
    i = x.get("IBUId")
    rows.append([i, x.get("GivenName"), x.get("FamilyName"), x.get("Nat"), x.get("Rank"), x.get("IRM"), x.get("TotalTime"),
                 x.get("Shootings"), x.get("StartTime"), x.get("WC")] + [an[t].get(i) for t in types])
comp = res.get("Competition") or {}
print("DATA_BEGIN")
print(json.dumps({"comp": {k: comp.get(k) for k in ("RaceId", "km", "catId", "DisciplineId", "StartTime", "PenaltySeconds", "NrShootings", "ShortDescription")},
                  "cols": ["ibu", "first", "last", "nat", "rank", "irm", "total", "shootings", "start", "wc"] + types, "rows": rows}, ensure_ascii=False, separators=(",", ":")))
print("DATA_END")
