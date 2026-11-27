"""Sonde 4 : distance officielle des tours (rapports PDF, champs de competition)."""
import json
import sys

sys.path.insert(0, ".")
from tdp.ibu import Client  # noqa: E402

c = Client()
for rid in ("BT2627SWRLCP01SMIN", "BT2526SWRLCP01SWSP", "BT2526SWRLCP01SWPU"):
    print("\n=====", rid)
    for m, p in (("Reports", {"RaceId": rid}), ("Reports", {"EventId": rid[:14]}), ("Competitions", {"EventId": rid[:14]})):
        try:
            d = c.get(m, **p)
        except Exception as exc:  # noqa: BLE001
            print(m, p, "ERR", str(exc)[:150]); continue
        if m == "Competitions":
            comp = next((x for x in d if x.get("RaceId") == rid), {})
            print("COMP", json.dumps(comp, ensure_ascii=False)[:1500])
        else:
            items = d if isinstance(d, list) else d.get("Reports") or d.get("Items") or d
            print(m, p, json.dumps(items, ensure_ascii=False)[:3000])
    try:
        a = c.get("AnalyticResults", RaceId=rid, TypeId="LAP1")
        print("LAP1 meta", json.dumps({k: v for k, v in a.items() if k != "Results"}, ensure_ascii=False)[:800])
    except Exception as exc:  # noqa: BLE001
        print("LAP1 ERR", exc)
