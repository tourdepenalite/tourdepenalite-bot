"""Sonde : temps intermediaires disponibles dans l'API IBU (pour le Reel « revivre la course »)."""
import json
import re
import sys
from urllib.parse import urljoin

sys.path.insert(0, ".")
from tdp.ibu import Client, SITE, _SCRIPT_SRC  # noqa: E402

c = Client()
out = {}


def try_get(method, **p):
    try:
        d = c.get(method, **p)
        return d
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)[:200]}


# 1. JS du site : noms de methodes et TypeId connus
page = c.s.get(SITE, timeout=30).text
methods, types, snippets = set(), set(), []
for src in _SCRIPT_SRC.findall(page):
    js = c.s.get(urljoin(SITE, src), timeout=30).text
    methods |= set(re.findall(r"sportapi/api/([A-Za-z]+)", js))
    methods |= set(re.findall(r"""["']/?api/([A-Z][A-Za-z]+)["'?]""", js))
    types |= set(re.findall(r"""TypeId[=:,\s"'+]+["']?([A-Z0-9]{2,6})""", js))
    for m in re.finditer(r"(?i)(intermed|split|AnalyticResults|TypeId)", js):
        snippets.append(js[max(0, m.start() - 120): m.end() + 160])
out["js_methods"] = sorted(methods)
out["js_types"] = sorted(types)
out["js_snippets"] = snippets[:60]

# 2. Courses de Kontiolahti (saison en cours), sinon saison passee
season = c.current_season()
races = []
for s in (season, f"{int(season[:2]) - 1:02d}{int(season[2:]) - 1:02d}"):
    for ev in c.events(s):
        for comp in c.competitions(ev["EventId"]):
            if "Final" in (comp.get("StatusText") or "") or "Official" in (comp.get("StatusText") or ""):
                races.append((s, ev.get("Organizer"), comp))
    if races:
        break
pick = {}
for s, org, comp in races:
    pick.setdefault(comp.get("DisciplineId"), (s, org, comp))
out["races"] = {k: [v[0], v[1], v[2].get("RaceId"), v[2].get("ShortDescription")] for k, v in pick.items()}

# 3. Results : toutes les cles d'une ligne
cand = ["CRST", "RNGT", "STTM", "FINN", "SKIT", "TOTL"]
cand += [f"{p}{i}" for p in ("CRS", "RNG", "STT", "INT", "I", "A", "SP", "LAP", "L", "S", "R", "PRN", "STD") for i in range(1, 6)]
cand += sorted(types)
for disc, (s, org, comp) in pick.items():
    rid = comp["RaceId"]
    res = try_get("Results", RaceId=rid)
    rows = (res.get("Results") or []) if isinstance(res, dict) else []
    info = {"result_keys": sorted(rows[0].keys()) if rows else None, "result_row": rows[0] if rows else res,
            "competition_keys": sorted((res.get("Competition") or {}).keys()) if isinstance(res, dict) else None}
    found = {}
    for t in dict.fromkeys(cand):
        d = try_get("AnalyticResults", RaceId=rid, TypeId=t)
        rr = d.get("Results") if isinstance(d, dict) else None
        if rr:
            found[t] = {"n": len(rr), "keys": sorted(rr[0].keys()), "first": rr[0],
                        "meta": {k: v for k, v in d.items() if k != "Results"}}
    info["analytic"] = found
    for m in ("Splits", "Intermediates", "RaceSplits", "CompetitionSplits", "AnalyticResultsAll", "Analytics", "AnalyticTypes", "Intermediate"):
        d = try_get(m, RaceId=rid)
        info[f"ep_{m}"] = str(d)[:400]
    out[disc] = info
    if len(out) > 8:
        break

print(json.dumps(out, ensure_ascii=False, indent=1)[:60000])
open("probe_splits.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1))
