"""Calculs deterministes. Aucune statistique publiee ne vient d'un LLM : tout sort d'ici."""
from __future__ import annotations

import datetime as dt
import re
from statistics import mean

from . import config
from .ibu import Client

# ----------------------------------------------------------------- utilitaires

def parse_time(v) -> float | None:
    if v in (None, ""):
        return None
    t = str(v).strip().lstrip("+")
    try:
        parts = [float(p) for p in t.split(":")]
    except ValueError:
        return None
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def fmt_time(s: float | None) -> str:
    if s is None:
        return "-"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{int(h)}:{int(m):02d}:{sec:04.1f}"
    return f"{int(m)}:{sec:04.1f}"


def fmt_gap(s: float | None) -> str:
    if s is None:
        return ""
    if s < 60:
        return f"+{s:.1f}"
    return "+" + fmt_time(s)


def ordinal(n: int | None) -> str:
    if not n:
        return "-"
    return "1er" if n == 1 else f"{n}e"


def ordinal_f(n: int | None) -> str:
    """Accord feminin (1re)."""
    if not n:
        return "-"
    return "1re" if n == 1 else f"{n}e"


def person(row: dict) -> tuple[str, str]:
    fam = (row.get("FamilyName") or "").strip()
    giv = (row.get("GivenName") or "").strip()
    if not fam:
        parts = (row.get("Name") or "").split()
        caps = [p for p in parts if p.isupper() and len(p) > 1]
        fam = " ".join(caps) or (parts[-1] if parts else "?")
        giv = " ".join(p for p in parts if p not in caps)
    fam = "-".join(w.capitalize() for w in fam.lower().split("-"))
    fam = " ".join(w[:1].upper() + w[1:] for w in fam.split(" "))
    return giv, fam


def parse_dt(v) -> dt.datetime | None:
    if not v:
        return None
    t = str(v).replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(config.TZ)


def site_key(text: str) -> str | None:
    t = (text or "").lower().replace("é", "e").replace("ä", "a").replace("ö", "o").replace("ě", "e")
    for k in config.SITES:
        if k in t:
            return k
    return None


# ----------------------------------------------------------------- courses

def _int(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def race_meta(comp: dict, event: dict | None = None) -> dict:
    disc = comp.get("DisciplineId") or ""
    cat = comp.get("catId") or comp.get("CatId") or ""
    desc = comp.get("ShortDescription") or comp.get("Description") or ""
    km = comp.get("km")
    if not km and (m := re.search(r"(\d+(?:[.,]\d+)?)\s*km", desc, re.I)):
        km = m.group(1)
    if km:
        km = f"{float(km):g}" if str(km).replace(".", "", 1).isdigit() else str(km)
    km_txt = f"{str(km).replace('.', ',')}\u00a0km" if km else ""  # espace insecable : jamais "7,5 / km"
    d = config.DISCIPLINES.get(disc, {"fr": desc})
    if disc in ("MR", "SR"):
        label = d["fr"]
    else:
        label = f"{d['fr']} {config.CATEGORIES.get(cat, '')}".strip()
    if km_txt and not d.get("relay"):
        label += f" {km_txt}"
    ev = event or {}
    venue_txt = " ".join(str(ev.get(k) or "") for k in ("Organizer", "ShortDescription", "Description"))
    sk = site_key(venue_txt)
    return {
        "race_id": comp.get("RaceId"),
        "disc": disc,
        "cat": cat,
        "relay": bool(d.get("relay")),
        "label": label,
        "label_upper": label.upper(),
        "start": parse_dt(comp.get("StartTime") or comp.get("StartDate")),
        "status": comp.get("StatusText") or "",
        "site_key": sk,
        "site": config.SITES[sk]["name"] if sk else (ev.get("Organizer") or ev.get("ShortDescription") or ""),
        "event_id": ev.get("EventId"),
        "penalty_s": _int(comp.get("PenaltySeconds")),     # fourni par l'IBU (60 en individuel)
        "nr_shootings": _int(comp.get("NrShootings")),
    }


def status_text(payload: dict, comp: dict | None = None) -> str:
    return " | ".join(t for t in (str((payload.get("Competition") or {}).get("StatusText") or ""),
                                  str((comp or {}).get("StatusText") or "")) if t)


def has_results(payload: dict, n: int = 3) -> bool:
    ranked = [r for r in payload.get("Results", []) or [] if str(r.get("Rank") or "").strip().isdigit()]
    return len(ranked) >= n


def is_official(payload: dict, comp: dict | None = None) -> bool:
    """Resultat definitif ? Le libelle exact du statut n'est pas documente. Une course a
    aussi une "liste de depart officielle" : on exige donc des resultats classes ET un
    statut qui parle de resultat officiel/final. Sinon l'orchestrateur attend que le
    classement soit stable sur deux passages, au moins 60 min apres le depart."""
    if not has_results(payload):
        return False
    if payload.get("IsFinal") is True:
        return True
    tl = status_text(payload, comp).lower()
    if any(w in tl for w in ("unofficial", "provisional", "live", "start", "progress", "running")):
        return False
    return ("official" in tl and "result" in tl) or "final" in tl


def _rank_map(client: Client, race_id: str, type_id: str) -> dict[str, tuple[float, int]]:
    data = client.analytic(race_id, type_id)
    vals = []
    for r in data.get("Results", []) or []:
        if r.get("IsTeam"):
            continue
        s = parse_time(r.get("TotalTime") or r.get("Result"))
        if r.get("IBUId") and s is not None:
            vals.append((str(r["IBUId"]), s))
    vals.sort(key=lambda x: x[1])
    return {ibu: (s, i + 1) for i, (ibu, s) in enumerate(vals)}


def individual_results(client: Client, race_id: str, payload: dict | None = None) -> list[dict]:
    payload = payload or client.results(race_id)
    ski = _rank_map(client, race_id, "CRST")
    rng = _rank_map(client, race_id, "RNGT")
    sht = _rank_map(client, race_id, "STTM")
    rows = []
    for r in payload.get("Results", []) or []:
        if r.get("IsTeam"):
            continue
        ibu = str(r.get("IBUId") or "")
        rank = r.get("Rank")
        try:
            rank = int(rank) if rank not in (None, "") else None
        except ValueError:
            rank = None
        misses = [int(x) if x.strip().isdigit() else 0 for x in str(r.get("Shootings") or "").split("+") if x.strip()]
        first, last = person(r)
        t = parse_time(r.get("TotalTime") or r.get("Result"))
        rows.append({
            "ibu": ibu, "rank": rank, "first": first, "last": last, "name": f"{first} {last}".strip(),
            "nat": r.get("Nat") or "", "bib": r.get("Bib"), "time_s": t,
            "behind_s": parse_time(r.get("Behind")) if rank and rank > 1 else 0.0,
            "misses": misses, "misses_total": sum(misses) if misses else None,
            "shots": 5 * len(misses), "irm": r.get("IRM") or "",
            "ski": ski.get(ibu), "range": rng.get(ibu), "shoot": sht.get(ibu),
            "wc": _int(r.get("WC")),  # points Coupe du monde publies par l'IBU
        })
    rows.sort(key=lambda x: (x["rank"] is None, x["rank"] or 999))
    return rows


def start_grid(payload: dict) -> list[dict]:
    """Liste de depart (avant course) : ordre, dossard, heure de depart, retard au depart
    (poursuite = ecart a la 1re heure de depart)."""
    rows = []
    for r in payload.get("Results", []) or []:
        if r.get("IsTeam"):
            continue
        first, last = person(r)
        try:
            order = int(r.get("StartOrder") or r.get("Bib") or 0)
        except ValueError:
            order = 0
        rows.append({"ibu": str(r.get("IBUId") or ""), "first": first, "last": last, "name": f"{first} {last}".strip(),
                     "nat": r.get("Nat") or "", "bib": r.get("Bib"), "order": order,
                     "start": parse_dt(r.get("StartTime"))})
    rows.sort(key=lambda x: (x["order"] or 999, int(x["bib"]) if str(x["bib"] or "").isdigit() else 999))
    t0 = min((x["start"] for x in rows if x["start"]), default=None)
    for x in rows:
        x["gap_s"] = (x["start"] - t0).total_seconds() if (x["start"] and t0) else None
    return rows


def relay_lineups(payload: dict) -> list[dict]:
    """Compositions des relais : [{nat, bib, legs: [(relais, nom), ...]}] tries par dossard."""
    teams, legs = {}, {}
    for r in payload.get("Results", []) or []:
        nat = r.get("Nat") or ""
        if r.get("IsTeam"):
            teams[nat] = {"nat": nat, "bib": _int(str(r.get("Bib") or "").split("-")[0]), "legs": []}
        elif r.get("Leg"):
            first, last = person(r)
            legs.setdefault(nat, []).append((_int(r.get("Leg")) or 0, f"{first} {last}".strip()))
    for nat, lst in legs.items():
        teams.setdefault(nat, {"nat": nat, "bib": None, "legs": []})["legs"] = [n for _, n in sorted(lst)]
    return sorted(teams.values(), key=lambda t: t["bib"] or 999)


def relay_results(payload: dict) -> list[dict]:
    teams = []
    for r in payload.get("Results", []) or []:
        if not r.get("IsTeam"):
            continue
        try:
            rank = int(r.get("Rank"))
        except (TypeError, ValueError):
            rank = None
        pen = spare = 0
        for leg in str(r.get("ShootingTotal") or "").split(","):
            if "+" in leg:
                a, b = leg.split("+", 1)
                pen += int(a) if a.strip().isdigit() else 0
                spare += int(b) if b.strip().isdigit() else 0
        teams.append({"rank": rank, "nat": r.get("Nat") or "", "name": r.get("Name") or r.get("Nat"),
                      "time_s": parse_time(r.get("TotalTime") or r.get("Result")),
                      "behind_s": parse_time(r.get("Behind")) if rank and rank > 1 else 0.0,
                      "penalties": pen, "spares": spare})
    teams.sort(key=lambda x: (x["rank"] is None, x["rank"] or 999))
    return teams


# ----------------------------------------------------------------- classements

def standings(client: Client, season: str, cat: str) -> list[dict]:
    cup = client.total_cup_id(season, cat)
    if not cup:
        return []
    rows = []
    for r in (client.cup_results(cup).get("Rows") or []):
        try:
            rank = int(r.get("Rank"))
        except (TypeError, ValueError):
            continue
        first, last = person(r)
        try:
            score = int(float(r.get("Score") or 0))
        except ValueError:
            score = 0
        rows.append({"rank": rank, "ibu": str(r.get("IBUId") or ""), "first": first, "last": last,
                     "name": f"{first} {last}".strip(), "nat": r.get("Nat") or "", "score": score})
    rows.sort(key=lambda x: x["rank"])
    return rows


def _birth(bio: dict) -> dt.date | None:
    for k in ("BirthDate", "Birthdate", "DateOfBirth"):
        if bio.get(k):
            try:
                return dt.date.fromisoformat(str(bio[k])[:10])
            except ValueError:
                pass
    for item in bio.get("Personal", []) or []:
        if "birth" in str(item.get("Description") or "").lower():
            v = str(item.get("Value") or "").strip()
            for f in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return dt.datetime.strptime(v[:10], f).date()
                except ValueError:
                    continue
    return None


def birth_map(client: Client, race_ids: list[str]) -> dict[str, dt.date]:
    """Dates de naissance via l'endpoint Athletes (un appel par course au lieu d'un par athlete)."""
    out = {}
    for rid in race_ids:
        for a in client.athletes(rid):
            b = _birth({"BirthDate": a.get("Birthdate")})
            if a.get("IBUId") and b:
                out[str(a["IBUId"])] = b
    return out


def u23_standings(client: Client, rows: list[dict], first_race: dt.date, limit: int = 40,
                  births: dict[str, dt.date] | None = None) -> list[dict]:
    """Classement jeunes : moins de 23 ans a la premiere course de la saison
    (regle reprise d'un outil existant, a confirmer aupres de l'IBU)."""
    out = []
    births = births or {}
    for r in rows[:limit]:
        b = births.get(r["ibu"]) or _birth(client.bio(r["ibu"]))
        if not b:
            continue
        age = first_race.year - b.year - ((first_race.month, first_race.day) < (b.month, b.day))
        if age < 23:
            out.append({**r, "age": age})
    return out


def clean_sheets(rows: list[dict]) -> list[dict]:
    """Athletes classes sans aucune faute au tir."""
    return [r for r in rows if r["rank"] and r["shots"] and r["misses_total"] == 0]


WC_POINTS = [90, 75, 60, 50, 45, 40, 36, 34, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21,
             20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]


def in_form(races: list[tuple[dict, list[dict]]], exclude: set[str]) -> dict | None:
    """Athlete le plus en forme sur un ensemble de courses (l'etape precedente) :
    le plus de points Coupe du monde, puis le meilleur resultat."""
    tot = {}
    for _, rows in races:
        for r in rows:
            if not r["rank"]:
                continue
            pts = r.get("wc")
            if pts is None:
                pts = WC_POINTS[r["rank"] - 1] if r["rank"] <= len(WC_POINTS) else 0
            t = tot.setdefault(r["ibu"], {**r, "pts": 0, "podiums": 0, "best": 99, "n": 0})
            t["pts"] += pts
            t["podiums"] += r["rank"] <= 3
            t["best"] = min(t["best"], r["rank"])
            t["n"] += 1
    cands = [t for k, t in tot.items() if k not in exclude and t["pts"] > 0]
    return max(cands, key=lambda t: (t["pts"], -t["best"]), default=None)


def movers(before: dict[str, int], after: list[dict], n: int = 3) -> dict:
    deltas = []
    for r in after[:30]:
        if r["ibu"] in before:
            deltas.append({**r, "before": before[r["ibu"]], "after": r["rank"], "delta": before[r["ibu"]] - r["rank"]})
    up = sorted([d for d in deltas if d["delta"] > 0], key=lambda d: (-d["delta"], d["after"]))[:n]
    down = sorted([d for d in deltas if d["delta"] < 0], key=lambda d: (d["delta"], d["after"]))[:n]
    return {"up": up, "down": down}


# ----------------------------------------------------------------- stat du jour

def stat_candidates(meta: dict, rows: list[dict], start_ranks: dict[str, int] | None = None) -> list[dict]:
    """Faits remarquables calcules, classes par interet. Claude choisit et redige, sans inventer."""
    fin = [r for r in rows if r["rank"]]
    if not fin:
        return []
    c = []
    win = fin[0]
    pen_s = config.DISCIPLINES.get(meta["disc"], {}).get("penalty_s", 25)
    if meta["disc"] in ("IN", "SI") and meta.get("penalty_s"):
        pen_s = meta["penalty_s"]  # valeur officielle IBU
    home = [r for r in fin if r["nat"] == config.HOME_NAT]
    il = "elle" if meta.get("cat") == "SW" else "il"
    le = "la" if meta.get("cat") == "SW" else "le"

    # Meilleur temps de ski sans la victoire
    best_ski = min((r for r in fin if r["ski"]), key=lambda r: r["ski"][1], default=None)
    if best_ski and best_ski["rank"] != 1:
        missed = best_ski["misses_total"] or 0
        fautes = f"{missed} faute{'s' if missed > 1 else ''}"
        txt = f"{best_ski['name']} ({best_ski['nat']}) signe le meilleur temps de ski mais finit {ordinal(best_ski['rank'])} avec {fautes}."
        if missed and best_ski["behind_s"] is not None and missed * pen_s > best_ski["behind_s"]:
            sans = f"sans {'elles' if missed > 1 else 'elle'}"
            if meta["disc"] in ("IN", "SI"):
                # Individuel : penalite en temps, fixe, pas de tour : le calcul est exact.
                pen = "1 minute" if meta["disc"] == "IN" else "45 secondes"
                txt += f" Chaque faute ajoute {pen} : {sans}, {il} gagnait."
            else:
                txt += f" Chaque faute impose un tour de pénalité, environ {pen_s} s : {sans}, {il} était probablement devant."
        c.append({"big": "1re" if meta.get("cat") == "SW" else "1er", "kind": "ski", "short": f"{best_ski['last']}, meilleur temps de ski", "fact": txt, "score": 90 + (10 if best_ski["nat"] == config.HOME_NAT else 0)})

    # Sans-faute
    clean = [r for r in fin[:15] if r["misses_total"] == 0]
    if clean:
        c.append({"big": f"{len(clean)}", "kind": "clean", "short": f"{len(clean)} sans-faute dans le top 15", "fact": f"{len(clean)} sans-faute dans le top 15 : " + ", ".join(r['name'] for r in clean[:5]) + ".", "score": 60})

    # Victoire au sprint final / ecart
    if len(fin) > 1 and fin[1]["behind_s"] is not None:
        gap = fin[1]["behind_s"]
        if gap < 3:
            c.append({"big": f"{gap:.1f} s", "kind": "photo", "short": f"{win['last']} gagne d'un souffle", "fact": f"{win['name']} gagne avec seulement {gap:.1f} s d'avance sur {fin[1]['name']}.", "score": 85})
        elif gap > 30:
            c.append({"big": f"{gap:.0f} s", "kind": "domination", "short": f"{win['last']} écrase la course", "fact": f"{win['name']} gagne avec {gap:.1f} s d'avance, une marge énorme.", "score": 75})

    # Remontee en poursuite
    if start_ranks:
        best = max(((start_ranks.get(r["ibu"], r["rank"]) - r["rank"], r) for r in fin), key=lambda x: x[0], default=(0, None))
        if best[1] and best[0] >= 10:
            r = best[1]
            c.append({"big": f"+{best[0]}", "kind": "remontee", "short": f"La remontée de {r['last']}", "fact": f"{r['name']} part {ordinal(start_ranks[r['ibu']])} et finit {ordinal(r['rank'])} : {best[0]} places gagnées.", "score": 88 + (8 if r['nat'] == config.HOME_NAT else 0)})

    # Tireur le plus rapide
    fastest = min((r for r in fin if r["shoot"]), key=lambda r: r["shoot"][0], default=None)
    if fastest:
        c.append({"big": fmt_time(fastest["shoot"][0]), "kind": "tir_rapide", "short": f"{fastest['last']}, la gâchette la plus rapide", "fact": f"{fastest['name']} est {le} plus rapide sur le tapis : {fmt_time(fastest['shoot'][0])} de tir cumulé.", "score": 50})

    # Bleus
    if home:
        n_top10 = len([r for r in home if r["rank"] <= 10])
        if n_top10 >= 3:
            c.append({"big": str(n_top10), "kind": "bleus", "short": f"{n_top10} Bleus dans le top 10", "fact": f"{n_top10} Français dans le top 10.", "score": 80})
        hits = sum(r["shots"] - (r["misses_total"] or 0) for r in home)
        shots = sum(r["shots"] for r in home)
        if shots:
            pct = round(100 * hits / shots)
            c.append({"big": f"{pct} %", "kind": "tir_bleus", "short": "La précision des Bleus", "fact": f"Les Français tirent à {pct} % ({hits}/{shots}).", "score": 55 + (15 if pct >= 92 else 0)})
    c.sort(key=lambda x: -x["score"])
    return c


# ----------------------------------------------------------------- favoris

def favorites(meta: dict, season_rows: list[tuple[dict, list[dict]]], fallback_standings: list[dict],
              start_list: list[dict] | None = None, n: int = 3) -> list[dict]:
    """Score de forme : points de place (41 - rang, plancher 0) sur les N dernieres courses
    individuelles de la categorie + bonus tir. En poursuite : les mieux places au depart."""
    if meta["disc"] == "PU" and start_list:
        out = []
        for r in start_list[:n]:
            gap = r["behind_s"] or 0
            why = "Part en tête" if r["rank"] == 1 else f"Part {ordinal(r['rank'])}, à {fmt_gap(gap)}"
            out.append({**r, "why": why})
        return out
    races = [(m, rows) for m, rows in season_rows if m["cat"] == meta["cat"] and not m["relay"]][-config.FAVORITES_FORM_RACES:]
    if len(races) < 2:
        return [{**r, "why": (f"{ordinal(r['rank'])} du général la saison passée ({r['why_prefix'].replace('saison ', '')})"
                             if r.get("why_prefix") else f"{ordinal(r['rank'])} du général")}
                for r in fallback_standings[:n]]
    score, info = {}, {}
    for _, rows in races:
        for r in rows:
            if not r["rank"]:
                continue
            pts = max(0, 41 - r["rank"])
            acc = 1 - (r["misses_total"] or 0) / r["shots"] if r["shots"] else 0.85
            score[r["ibu"]] = score.get(r["ibu"], 0) + pts * (0.8 + 0.4 * acc)
            i = info.setdefault(r["ibu"], {**r, "ranks": [], "wins": 0, "hits": 0, "shots": 0})
            i["ranks"].append(r["rank"])
            i["wins"] += r["rank"] == 1
            i["hits"] += r["shots"] - (r["misses_total"] or 0)
            i["shots"] += r["shots"]
    top = sorted(score, key=lambda k: -score[k])[:n]
    out = []
    for k in top:
        i = info[k]
        if i["wins"] >= 2:
            why = f"{i['wins']} victoires sur les {len(races)} dernières courses"
        elif i["shots"] and i["hits"] / i["shots"] >= 0.92:
            why = f"{round(100 * i['hits'] / i['shots'])} % au tir sur les dernières courses"
        else:
            why = f"Moyenne : {ordinal(round(mean(i['ranks'])))} sur les {len(i['ranks'])} dernières courses"
        out.append({**i, "why": why})
    return out


# ----------------------------------------------------------------- bilan Bleus

def athlete_week(ibu: str, event_races: list[tuple[dict, list[dict]]], season_races: list[tuple[dict, list[dict]]]) -> dict:
    def collect(races):
        res = []
        for m, rows in races:
            for r in rows:
                if r["ibu"] == ibu:
                    res.append((m, r))
        return res
    wk, ss = collect(event_races), collect(season_races)

    def agg(lst):
        ranks = [r["rank"] for _, r in lst if r["rank"]]
        hits = sum(r["shots"] - (r["misses_total"] or 0) for _, r in lst)
        shots = sum(r["shots"] for _, r in lst)
        ski = [r["ski"][1] for _, r in lst if r["ski"]]
        return {"best": min(ranks) if ranks else None, "n": len(lst),
                "tir": round(100 * hits / shots) if shots else None,
                "ski": round(mean(ski)) if ski else None}
    return {"week": agg(wk), "season": agg(ss),
            "week_by_disc": [(m["disc"], r["rank"]) for m, r in wk],
            "form": [r["rank"] for _, r in ss][-6:]}
