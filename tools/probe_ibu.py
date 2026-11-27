"""Sonde 2 : fichier de session (chronometrage) de l'IBU, recherche du detail tir par tir."""
import json, re
from tdp.ibu import Client

RACE = "BT2627SWRLCP01SMIN"
c = Client()
info = c.get("SessionInfo", RaceId=RACE)
url = info["FullUri"] + "?" + info["SASToken"]
txt = c.s.get(url, timeout=60).text
print("taille", len(txt))
print("DEBUT", txt[:1500])
for kw in ("BTHShot", "BTHShooting", "UnitShooting", "Shot", "Target", "Hit", "Miss"):
    idx = [m.start() for m in re.finditer(kw, txt)][:3]
    print(f"\n### {kw}: {len(re.findall(kw, txt))} occurrences")
    for i in idx:
        print("   ...", txt[max(0, i - 300): i + 700].replace("\n", " "))
# fichiers voisins (changesets)
base = info["FullUri"].rsplit("/", 1)[0]
for suffix in (".session.js", ".changeset.session.js", ".shots.session.js"):
    u = f"{base}/{info['SessionId']}{suffix}?{info['SASToken']}"
    r = c.s.get(u, timeout=30)
    print("\nvoisin", suffix, r.status_code, len(r.text))
