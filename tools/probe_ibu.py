"""Sonde : cherche ou l'API IBU expose le detail tir par tir. Lecture seule."""
import json, re
from urllib.parse import urljoin
from tdp.ibu import Client, SITE

RACE = "BT2627SWRLCP01SMIN"  # individuel hommes Kontiolahti, termine
c = Client()

def show(title, obj, n=1500):
    print(f"\n===== {title}\n" + json.dumps(obj, ensure_ascii=False)[:n])

p = c.results(RACE)
show("Results: cles racine", list(p.keys()))
rows = [r for r in p.get("Results", []) if r.get("Rank")]
show("Results: 1re ligne complete", rows[0] if rows else None, 3000)
show("Competition", p.get("Competition"))

# 1) Endpoints et codes cites dans le JavaScript du site
html = c.s.get(SITE, timeout=30).text
srcs = [urljoin(SITE, s) for s in re.findall(r"""src=["']?([^"'\s>]+\.js)""", html)]
eps, codes, ctx = set(), set(), []
for u in srcs:
    try:
        js = c.s.get(u, timeout=30).text
    except Exception:
        continue
    eps |= set(re.findall(r"""["'/]api/([A-Za-z]+)""", js))
    codes |= set(re.findall(r"""TypeId[=:\s"'+]*["']([A-Z0-9]{3,6})["']""", js))
    for m in re.finditer(r"(?i)shoot|shot|target", js):
        ctx.append(js[max(0, m.start() - 80): m.end() + 80].replace("\n", " "))
show("Scripts", srcs)
show("Endpoints vus dans le JS", sorted(eps))
show("Codes TypeId vus dans le JS", sorted(codes))
show("Contextes 'shoot/shot/target' (40 premiers)", ctx[:40], 8000)

# 2) Essais directs
for ep in sorted(eps):
    if ep in ("Seasons", "Events", "Competitions", "Results", "Cups", "CupResults", "CISBios"):
        continue
    for params in ({"RaceId": RACE}, {"RaceId": RACE, "IBUId": rows[0]["IBUId"]} if rows else {}):
        try:
            d = c.get(ep, **params)
            show(f"{ep} {list(params)}", d, 1500)
            break
        except Exception as e:
            print(f"{ep} {list(params)} -> {str(e)[:120]}")
for t in sorted(codes | {"STTM", "SHT", "SHOT", "SHTS", "STAT", "TGT", "TRGT", "RNGD", "SHTD", "STDT"}):
    try:
        d = c.analytic(RACE, t)
        res = d.get("Results") or []
        print(f"AnalyticResults {t}: {len(res)} lignes", json.dumps(res[:1], ensure_ascii=False)[:400])
    except Exception as e:
        print(f"AnalyticResults {t} -> {str(e)[:120]}")
