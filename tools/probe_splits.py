"""Sonde 9 : donnees compactes d'un relais reel (prototype du Reel relais)."""
import json
import sys

sys.path.insert(0, ".")
from tdp.ibu import Client  # noqa: E402

c = Client()
RID = "BT2526SWRLCP01SWRL"
res = c.get("Results", RaceId=RID)
an = {}
for t in [f"LAP{i}" for i in range(1, 13)] + [f"CRS{i}" for i in range(1, 13)]:
    an[t] = {x["IBUId"]: x.get("TotalTime") for x in (c.get("AnalyticResults", RaceId=RID, TypeId=t).get("Results") or [])}
keep = ("IBUId", "IsTeam", "Name", "FamilyName", "GivenName", "Nat", "Bib", "Leg", "Rank", "IRM", "Shootings", "ShootingTotal",
        "TotalTime", "Behind", "LegRank", "TeamRankAfterLeg")
rows = [{k: r.get(k) for k in keep} for r in res["Results"]]
comp = res.get("Competition") or {}
print("DATA_BEGIN")
print(json.dumps({"comp": {k: comp.get(k) for k in ("RaceId", "km", "ShortDescription", "DisciplineId", "catId")}, "rows": rows, "an": an},
                 ensure_ascii=False, separators=(",", ":")))
print("DATA_END")
