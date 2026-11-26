"""Genere une fausse saison au format de l'API IBU (noms et resultats inventes) pour tester
tout le pipeline sans reseau. Usage : python tests/make_fixtures.py <dossier> [--after]"""
import datetime as dt
import json
import pathlib
import random
import sys

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures")
AFTER = "--after" in sys.argv  # classement general incluant la 2e etape
OUT.mkdir(parents=True, exist_ok=True)
rnd = random.Random(7)
SEASON = "2627"

FIRST_W = {"NOR": ["Ingrid", "Marte", "Karoline", "Ida", "Juni", "Ragnhild"], "FRA": ["Lou", "Julia", "Océane", "Camille", "Sophie", "Jeanne", "Anaïs", "Chloé"],
           "SWE": ["Hanna", "Elvira", "Linn", "Mona"], "GER": ["Franziska", "Vanessa", "Selina", "Sophia"], "ITA": ["Dorothea", "Lisa", "Michela", "Rebecca"],
           "SUI": ["Aita", "Lena", "Amy", "Elisa"], "AUT": ["Anna", "Lisa", "Julia", "Tamara"], "FIN": ["Suvi", "Mari", "Venla", "Inka"], "CZE": ["Marketa", "Tereza", "Lucie", "Jessica"],
           "USA": ["Deedra", "Chloe", "Joanne"], "UKR": ["Olena", "Yuliia", "Anastasiya"], "SLO": ["Anamarija", "Lena"]}
FIRST = {"NOR": ["Lars", "Jonas", "Sivert", "Vetle", "Endre", "Martin"], "FRA": ["Émile", "Hugo", "Théo", "Paul", "Louis", "Quentin", "Antonin", "Fabien"],
         "SWE": ["Viktor", "Erik", "Jesper", "Oskar"], "GER": ["Tobias", "Philipp", "Johannes", "Roman"], "ITA": ["Matteo", "Tommaso", "Lukas", "Didier"],
         "SUI": ["Simon", "Niklas", "Joscha", "Sebastian"], "AUT": ["Felix", "David", "Simon", "Patrick"], "FIN": ["Olli", "Tero", "Jaakko", "Otto"], "CZE": ["Michal", "Jakub", "Vitezslav", "Adam"],
         "USA": ["Sean", "Campbell", "Paul"], "UKR": ["Dmytro", "Vitalii", "Artem"], "SLO": ["Jakov", "Miha"]}
LAST = {"NOR": ["EIKELAND", "BREKKE", "HAUGEN", "SOLBERG", "LIEN", "DAHL"], "FRA": ["GARNIER", "MARTEL", "ROUVIER", "DELORME", "BERTHET", "VIDAL", "MOREAU", "CHAUVIN", "LACROIX", "PERRIN"],
        "SWE": ["LINDQVIST", "NYBERG", "SANDSTRÖM", "HOLM"], "GER": ["REITER", "KELLNER", "BAUMANN", "VOGT"], "ITA": ["VARESCO", "PELLEGRINI", "ZINGERLE", "COMPER"],
        "SUI": ["AEBI", "STALDER", "GASPARIN", "HÄCKI"], "AUT": ["HAUSER", "EDER", "LEITNER", "STEINER"], "FIN": ["VIRTANEN", "KORHONEN", "MÄKINEN", "LAINE"],
        "CZE": ["NOVAK", "DVORAK", "KRCMAR", "VOBORNIKOVA"], "USA": ["DOHERTY", "BROWN", "IRWIN"], "UKR": ["PIDRUCHNYI", "SEMENKO", "BILOSIUK"], "SLO": ["FAK", "KLEMENCIC"]}


def athletes(cat):
    lst, i = [], 0
    for nat, lasts in LAST.items():
        n = 8 if nat == "FRA" else len(lasts)
        for k in range(n):
            last = lasts[k % len(lasts)] + ("" if k < len(lasts) else "-ROUX")
            src = FIRST if cat == "SM" else FIRST_W
            first = src[nat][k % len(src[nat])]
            ibu = f"BT{nat}{cat}{k:02d}"
            skill = rnd.gauss(0, 1) + (1.2 if (nat, k) in {("NOR", 0), ("FRA", 0), ("SWE", 0), ("FRA", 1)} else 0) + (0.4 if nat in ("NOR", "FRA") else 0)
            lst.append({"IBUId": ibu, "FamilyName": last, "GivenName": first, "Nat": nat, "skill": skill,
                        "acc": min(0.97, max(0.75, rnd.gauss(0.87, 0.05))), "shoot_speed": rnd.gauss(28, 3),
                        "birth": f"{rnd.randint(1994, 2005)}-0{rnd.randint(1, 9)}-1{rnd.randint(0, 9)}"})
            i += 1
    return lst


ATH = {"SM": athletes("SM"), "SW": athletes("SW")}
PTS = [90, 75, 60, 50, 45, 40, 36, 34, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
FMT = {"SP": (2, 1500, 10), "PU": (4, 1900, 12.5), "MS": (4, 2200, 15), "IN": (4, 2900, 20)}


def fmt(s):
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{int(h)}:{int(m):02d}:{sec:04.1f}" if h else f"{int(m)}:{sec:04.1f}"


def race(race_id, disc, cat, start_iso):
    stages, base, km = FMT[disc]
    km = km if cat == "SM" else km - 2.5
    res, ana = [], {"CRST": [], "RNGT": [], "STTM": []}
    field = ATH[cat] if disc != "MS" else sorted(ATH[cat], key=lambda a: -a["skill"])[:30]
    for a in field:
        misses = [sum(rnd.random() > a["acc"] for _ in range(5)) for _ in range(stages)]
        ski = base * (1 - 0.012 * a["skill"]) + rnd.gauss(0, 12)
        shoot = a["shoot_speed"] * stages + rnd.gauss(0, 4)
        rng = shoot + 8 * stages + rnd.gauss(0, 2)
        pen = 25 * sum(misses)
        total = ski + rng + pen
        res.append({"a": a, "misses": misses, "total": total, "ski": ski, "rng": rng, "shoot": shoot})
    res.sort(key=lambda r: r["total"])
    rows = []
    for i, r in enumerate(res):
        a = r["a"]
        dnf = i >= len(res) - 2 and disc != "SP"
        rows.append({"IBUId": a["IBUId"], "FamilyName": a["FamilyName"], "GivenName": a["GivenName"],
                     "Name": f"{a['GivenName']} {a['FamilyName']}", "Nat": a["Nat"], "Bib": str(i + 1), "IsTeam": False,
                     "Rank": "" if dnf else str(i + 1), "ResultOrder": i + 1, "IRM": "DNF" if dnf else "",
                     "TotalTime": "" if dnf else fmt(r["total"]), "Behind": "" if (dnf or i == 0) else "+" + fmt(r["total"] - res[0]["total"]).lstrip("0:"),
                     "Shootings": "+".join(map(str, r["misses"])), "ShootingTotal": str(sum(r["misses"]))})
        for k, v in (("CRST", r["ski"]), ("RNGT", r["rng"]), ("STTM", r["shoot"])):
            ana[k].append({"IBUId": a["IBUId"], "TotalTime": fmt(v), "IsTeam": False})
    comp = {"RaceId": race_id, "DisciplineId": disc, "catId": cat, "ShortDescription": f"{'Men' if cat=='SM' else 'Women'} {km}km {disc}", "km": km, "StartTime": start_iso, "StatusText": "Official"}
    (OUT / f"Results_{race_id}.json").write_text(json.dumps({"Competition": comp, "Results": rows}))
    for k, v in ana.items():
        (OUT / f"AnalyticResults_{race_id}_{k}.json").write_text(json.dumps({"Results": v}))
    return comp, rows


def relay(race_id, cat, start_iso):
    nats = ["NOR", "FRA", "SWE", "GER", "ITA", "SUI", "AUT", "FIN", "CZE", "USA"]
    rnd.shuffle(nats)
    nats.sort(key=lambda n: -(1 if n in ("NOR", "FRA") else 0) + rnd.random())
    t0 = 4400
    rows = [{"IsTeam": True, "Nat": n, "Name": n, "Rank": str(i + 1), "TotalTime": fmt(t0 + i * 17.3), "Behind": "" if i == 0 else "+" + fmt(i * 17.3).lstrip("0:"),
             "ShootingTotal": f"{rnd.randint(0,1)}+{rnd.randint(2,7)}"} for i, n in enumerate(nats)]
    comp = {"RaceId": race_id, "DisciplineId": "RL", "catId": cat, "ShortDescription": f"{'Women' if cat=='SW' else 'Men'} 4x6km Relay", "StartTime": start_iso, "StatusText": "Official"}
    (OUT / f"Results_{race_id}.json").write_text(json.dumps({"Competition": comp, "Results": rows}))
    for k in ("CRST", "RNGT", "STTM"):
        (OUT / f"AnalyticResults_{race_id}_{k}.json").write_text(json.dumps({"Results": []}))
    return comp, []


EVENTS = [
    ("BT2627SWRLCP01", "Kontiolahti", "KONTIOLAHTI", dt.date(2026, 11, 26), [("SP", "SM", 0, "14:10"), ("SP", "SW", 0, "16:40"), ("PU", "SM", 2, "13:00"), ("PU", "SW", 2, "15:30"), ("RL", "SW", 3, "12:00"), ("MS", "SM", 3, "14:45")]),
    ("BT2627SWRLCP02", "Le Grand-Bornand", "LE GRAND-BORNAND", dt.date(2026, 12, 17), [("SP", "SW", 0, "13:15"), ("SP", "SM", 1, "13:15"), ("PU", "SW", 2, "11:45"), ("PU", "SM", 2, "14:00"), ("MS", "SW", 3, "11:30"), ("MS", "SM", 3, "14:00")]),
]
events_json, all_rows = [], {"SM": [], "SW": []}
for n, (eid, org, short, d0, races) in enumerate(EVENTS):
    comps = []
    for k, (disc, cat, off, hhmm) in enumerate(races):
        day = d0 + dt.timedelta(days=off)
        local = dt.datetime.fromisoformat(f"{day}T{hhmm}")
        utc = (local - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rid = f"{eid}{cat}{disc}{k}"
        comp, rows = relay(rid, cat, utc) if disc == "RL" else race(rid, disc, cat, utc)
        comps.append(comp)
        if rows and (AFTER or n == 0):
            all_rows[cat].append(rows)
    (OUT / f"Competitions_{eid}.json").write_text(json.dumps(comps))
    events_json.append({"EventId": eid, "Organizer": org, "ShortDescription": short, "StartDate": f"{d0}T00:00:00Z", "EndDate": f"{d0 + dt.timedelta(days=3)}T00:00:00Z"})
(OUT / "events.json").write_text(json.dumps(events_json))
(OUT / "seasons.json").write_text(json.dumps([{"SeasonId": SEASON, "IsCurrent": True, "SortOrder": 99}]))
(OUT / "cups.json").write_text(json.dumps([{"CupId": f"BT{SEASON}SWRLCP__{c}TS", "CatId": c, "Level": 1, "DisciplineId": "TS"} for c in ("SM", "SW")]))
for cat in ("SM", "SW"):
    score = {}
    for rows in all_rows[cat]:
        for r in rows:
            if r["Rank"] and int(r["Rank"]) <= 40:
                score[r["IBUId"]] = score.get(r["IBUId"], 0) + PTS[int(r["Rank"]) - 1]
    order = sorted(score, key=lambda k: -score[k])
    by = {a["IBUId"]: a for a in ATH[cat]}
    rows = [{"Rank": str(i + 1), "IBUId": k, "FamilyName": by[k]["FamilyName"], "GivenName": by[k]["GivenName"], "Nat": by[k]["Nat"], "Score": str(score[k])} for i, k in enumerate(order)]
    (OUT / f"CupResults_BT{SEASON}SWRLCP__{cat}TS.json").write_text(json.dumps({"Rows": rows}))
for cat in ("SM", "SW"):
    for a in ATH[cat]:
        (OUT / f"CISBios_{a['IBUId']}.json").write_text(json.dumps({"BirthDate": a["birth"]}))
print("fixtures ->", OUT, "(after)" if AFTER else "")
