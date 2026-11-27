"""Orchestrateur. Lance toutes les 5-10 minutes par GitHub Actions :
1. lit les validations Telegram et publie ce qui a ete accepte ;
2. regarde la grille et produit les posts dus (une seule fois chacun) ;
3. enregistre l'etat dans state.json (commite par le workflow).

Usage : python -m tdp.tick [--now 2026-12-17T10:00]  (--now sert aux tests)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import traceback

import requests

from . import captions, config, publish, stats, templates
from .ibu import Client
from .render import render

STATE = pathlib.Path(os.environ.get("TDP_STATE", "state.json"))
OUT = pathlib.Path(os.environ.get("TDP_OUT", "out"))
NOW: dt.datetime | None = None  # heure courante (simulable avec --now)
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class NotReady(Exception):
    """Donnees pas encore disponibles : on reessaiera au prochain passage, sans compter d'echec."""


# ================================================================ etat

def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"posts": {}, "tg_offset": 0, "snapshots": {}, "watch": {}}


def save_state(st: dict):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str))


# ================================================================ contexte saison

class Season:
    def __init__(self, client: Client, now: dt.datetime):
        self.c, self.now = client, now
        self.id = client.current_season()
        self.events = sorted(client.events(self.id, config.WC_LEVEL), key=lambda e: e.get("StartDate") or "")
        self._races = None
        self._spans = {}

    def previous_id(self) -> str:
        a, b = int(self.id[:2]), int(self.id[2:])
        return f"{a - 1:02d}{b - 1:02d}"

    def ev_dates(self, ev):
        s, e = stats.parse_dt(ev.get("StartDate")), stats.parse_dt(ev.get("EndDate"))
        return (s.date() if s else None), (e.date() if e else None)

    def comps(self, ev) -> list[dict]:
        out = [stats.race_meta(c, ev) | {"_comp": c} for c in self.c.competitions(ev["EventId"])]
        return sorted([m for m in out if m["start"]], key=lambda m: m["start"])

    def race_span(self, ev) -> tuple[dt.datetime | None, dt.datetime | None]:
        """Premiere et derniere course de l'etape. Les dates de l'etape publiees par l'IBU
        incluent les jours d'entrainement : on se fie aux horaires des courses."""
        key = ev.get("EventId")
        if key not in self._spans:
            starts = [m["start"] for m in self.comps(ev)]
            self._spans[key] = (min(starts), max(starts)) if starts else (None, None)
        return self._spans[key]

    def _near(self, ev, days: int) -> bool:
        s, e = self.ev_dates(ev)
        today = self.now.date()
        return bool(s and e and (s - today).days <= days + 7 and (today - e).days <= days + 7)

    def upcoming(self, days=7):
        """Etape dont la premiere course n'a pas encore eu lieu et tombe dans les `days` jours."""
        best = None
        for ev in self.events:
            if not self._near(ev, days):
                continue
            first, _ = self.race_span(ev)
            if first and first > self.now and (first.date() - self.now.date()).days <= days:
                if not best or first < self.race_span(best)[0]:
                    best = ev
        return best

    def running(self):
        for ev in self.events:
            if not self._near(ev, 0):
                continue
            first, last = self.race_span(ev)
            if first and last and first.date() <= self.now.date() <= last.date():
                return ev
        return None

    def just_ended(self, max_days=4):
        best = None
        for ev in self.events:
            if not self._near(ev, max_days):
                continue
            _, last = self.race_span(ev)
            if last and 0 < (self.now.date() - last.date()).days <= max_days:
                best = ev
        return best

    def finished_races(self, until: dt.datetime | None = None) -> list[tuple[dict, list[dict]]]:
        """Toutes les courses individuelles terminees de la saison, avec resultats enrichis."""
        if self._races is not None and until is None:
            return self._races
        until = until or self.now
        out = []
        for ev in self.events:
            s, _ = self.ev_dates(ev)
            if not s or s > until.date():
                continue
            for m in self.comps(ev):
                if m["relay"] or m["start"] > until - dt.timedelta(hours=1):
                    continue
                old = (self.now - m["start"]).days >= 1
                try:
                    rows = stats.individual_results(self.c, m["race_id"], self.c.results(m["race_id"], cache_s=7 * 86400 if old else 0))
                except Exception:
                    continue
                if any(r["rank"] for r in rows):
                    out.append((m, rows))
        if until is self.now:
            self._races = out
        return out


    def finished_relays(self) -> list[tuple[dict, list[dict]]]:
        """Relais termines de la saison (classement par nation, tours de penalite)."""
        out = []
        for ev in self.events:
            s, _ = self.ev_dates(ev)
            if not s or s > self.now.date():
                continue
            for m in self.comps(ev):
                if not m["relay"] or m["start"] > self.now - dt.timedelta(hours=1):
                    continue
                old = (self.now - m["start"]).days >= 1
                try:
                    teams = stats.relay_results(self.c.results(m["race_id"], cache_s=7 * 86400 if old else 0))
                except Exception:
                    continue
                if teams and teams[0]["rank"]:
                    out.append((m, teams))
        return out


# ================================================================ production d'un post

def produce(st: dict, key: str, kind: str, slides: list[str], caption: str, story: str | list[str] | None = None,
            expires: dt.datetime | None = None, alts: list[str] | None = None, auto: bool = False):
    """story : une story ou une liste de stories, publiees apres le post du fil."""
    stories = [x for x in (story if isinstance(story, list) else [story]) if x]
    folder = OUT / key.replace(":", "_")
    paths = render(slides + stories, folder, "s")
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    urls = [publish.upload(p, f"{key.replace(':', '/')}/{stamp}_{p.name}") for p in paths]
    story_urls = urls[len(slides):]
    urls = urls[:len(slides)]
    real_now = dt.datetime.now(config.TZ)
    if NOW < real_now - dt.timedelta(minutes=30):
        # Rattrapage (--now dans le passe) : laisser 20 h pour valider, quelle que soit l'heure de la course.
        expires = real_now + dt.timedelta(hours=20)
    if not alts:
        first = caption.strip().splitlines()[0] if caption.strip() else kind
        alts = [f"Tour de pénalité, statistiques de biathlon : {first} (visuel {i + 1}/{len(urls)})" for i in range(len(urls))]
    post = {"kind": kind, "status": "pending", "urls": urls, "story_urls": story_urls, "caption": caption, "alts": alts,
            "created": NOW.isoformat(),
            "expires": (expires or NOW + dt.timedelta(hours=20)).isoformat(),
            "files": [str(p) for p in paths]}
    st["posts"][key] = post
    if config.REQUIRE_APPROVAL and not auto:
        publish.send_for_approval(key, urls, caption, story_urls)
    else:
        do_publish(st, key)
    print(f"[produit] {key} ({len(paths)} visuel(s))")


def produce_video(st: dict, key: str, kind: str, path: pathlib.Path, caption: str, thumb_ms: int = 0):
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    url = publish.upload(path, f"{key.replace(':', '/')}/{stamp}_{path.name}")
    real_now = dt.datetime.now(config.TZ)
    expires = real_now + dt.timedelta(hours=20) if NOW < real_now - dt.timedelta(minutes=30) else NOW + dt.timedelta(hours=20)
    st["posts"][key] = {"kind": kind, "status": "pending", "urls": [], "story_urls": [], "video_url": url, "thumb_ms": thumb_ms,
                        "caption": caption, "created": NOW.isoformat(), "expires": expires.isoformat(), "files": [str(path)]}
    if config.REQUIRE_APPROVAL:
        publish.send_for_approval(key, [], caption, None, video=url)
    else:
        do_publish(st, key)
    print(f"[produit] {key} (video)")


def do_publish(st: dict, key: str):
    p = st["posts"][key]
    try:
        if p.get("video_url"):
            p["ig_id"] = publish.publish_reel(p["video_url"], p["caption"], p.get("thumb_ms", 0))
        if p["urls"]:
            p["ig_id"] = publish.publish_feed(p["urls"], p["caption"], p.get("alts"))
        stories = p.get("story_urls") or ([p["story_url"]] if p.get("story_url") else [])
        p["ig_story_ids"] = [publish.publish_story(u) for u in stories]
        p["status"] = "published"
        p["published"] = (NOW or dt.datetime.now(config.TZ)).isoformat()
    except Exception as exc:
        p["status"] = "failed"
        p["error"] = str(exc)[:500]
        publish.notify(f"⚠️ Échec de publication {key} : {exc}")


def handle_decisions(st: dict, now: dt.datetime):
    decisions, st["tg_offset"] = publish.read_decisions(st.get("tg_offset", 0))
    for action, key in decisions:
        p = st["posts"].get(key)
        if not p or p["status"] != "pending":
            continue
        if action == "ok":
            do_publish(st, key)
            ok = p["status"] == "published"
            publish.notify(f"✅ {key} publié sur Instagram." if ok else f"⚠️ {key} : échec de publication, voir le journal.")
        else:
            p["status"] = "cancelled"
            publish.notify(f"❌ {key} annulé.")
    for key, p in st["posts"].items():
        if p["status"] == "pending" and p.get("expires") and now > dt.datetime.fromisoformat(p["expires"]):
            p["status"] = "expired"
            publish.notify(f"⌛ {key} non validé à temps, abandonné.")


# ================================================================ meteo (open-meteo, sans cle)

SKY_FR = [("overcast", "couvert"), ("cloud", "nuageux"), ("sun", "ensoleillé"), ("clear", "dégagé"), ("fog", "brouillard"),
          ("snow", "neige"), ("rain", "pluie"), ("drizzle", "bruine")]
SNOW_FR = [("hard", "neige dure"), ("packed", "neige tassée"), ("icy", "neige glacée"), ("wet", "neige mouillée"),
           ("soft", "neige molle"), ("powder", "neige poudreuse"), ("new", "neige fraîche")]


def _fr(text: str, table) -> str | None:
    t = (text or "").lower()
    return next((fr for en, fr in table if en in t), None)


def weather(meta: dict, client: Client | None = None) -> str | None:
    """Meteo officielle IBU du stade si publiee, sinon prevision open-meteo."""
    if client and meta.get("race_id"):
        w = client.weather(meta["race_id"])
        if w.get("AirTemperature_C") is not None:
            parts = [f"{round(w['AirTemperatureDec_C'] if w.get('AirTemperatureDec_C') is not None else w['AirTemperature_C'])} °C"]
            if (sky := _fr(w.get("WeatherCondition"), SKY_FR)):
                parts.append(sky)
            if w.get("WindSpeed_KMH") is not None:
                parts.append(f"vent {w['WindSpeed_KMH']} km/h")
            if (snow := _fr(w.get("SnowCondition"), SNOW_FR)):
                parts.append(snow)
            return " · ".join(parts)
    site = config.SITES.get(meta["site_key"] or "")
    if not site or not meta["start"] or os.environ.get("TDP_IBU_FIXTURES"):
        return None
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
            "latitude": site["lat"], "longitude": site["lon"], "hourly": "temperature_2m,wind_speed_10m",
            "timezone": "Europe/Paris", "forecast_days": 2})
        h = r.json()["hourly"]
        target = meta["start"].strftime("%Y-%m-%dT%H:00")
        i = h["time"].index(target)
        wind = h["wind_speed_10m"][i]
        wtxt = "vent faible" if wind < 10 else ("vent modéré" if wind < 25 else "vent fort")
        return f"{round(h['temperature_2m'][i])} °C · {wtxt} (prévision)"
    except Exception:
        return None


# ================================================================ les 6 types de posts

def p_programme(st, S: Season, ev):
    metas = S.comps(ev)
    if not metas:
        return
    site = metas[0]["site"]
    days = {}
    for m in metas:
        d = m["start"].date()
        days.setdefault(d, []).append((m["start"].strftime("%H:%M"), m["label"][0].upper() + m["label"][1:]))
    day_list = [(JOURS[d.weekday()], v) for d, v in sorted(days.items())]
    enjeux, facts = {}, [f"Étape : {site}, {len(metas)} courses sur {len(days)} jours."]
    prev = S.previous_id()
    for cat in ("SM", "SW"):
        fem = cat == "SW"
        o = stats.ordinal_f if fem else stats.ordinal
        rows = stats.standings(S.c, S.id, cat)
        current = len(rows) >= 2 and rows[0]["score"] > 0
        if not current:  # premiere etape : classement de la saison passee
            rows = stats.standings(S.c, prev, cat)
        if not rows:
            continue
        items = []
        a = rows[0]
        if current:
            b = rows[1]
            d = a["score"] - b["score"]
            items.append(("DOSSARD JAUNE", a["name"], a["nat"],
                          f"{d} pts d'avance sur {b['name']}" if d else f"À égalité avec {b['name']}"))
            facts.append(f"Leader {config.CATEGORIES[cat]} : {a['name']} {a['nat']}, {d} points devant {b['name']}.")
        else:
            items.append(("TENANTE DU GROS GLOBE" if fem else "TENANT DU GROS GLOBE", a["name"], a["nat"],
                          f"{'1re' if fem else '1er'} du général {prev[:2]}-{prev[2:]}, {a['score']} pts"))
            facts.append(f"Vainqueur du général {config.CATEGORIES[cat]} la saison passée : {a['name']} {a['nat']}.")
        home = next((r for r in rows if r["nat"] == config.HOME_NAT and r["ibu"] != a["ibu"]), None)
        if home:
            ctx = "au général" if current else f"du général {prev[:2]}-{prev[2:]}"
            items.append(("LA FRANÇAISE À SUIVRE" if fem else "LE FRANÇAIS À SUIVRE", home["name"], home["nat"],
                          f"{o(home['rank'])} {ctx}, {home['score']} pts"))
            facts.append(f"{'Meilleure Française' if fem else 'Meilleur Français'} {ctx} : {home['name']}, {home['rank']}e.")
        # En forme : le plus de points sur l'etape precedente (hors athletes deja affiches)
        prev_races = [(m, r) for m, r in S.finished_races() if m["cat"] == cat and m["event_id"] != ev["EventId"]]
        if prev_races:
            last_ev = prev_races[-1][0]["event_id"]
            last = [(m, r) for m, r in prev_races if m["event_id"] == last_ev]
            f = stats.in_form(last, {a["ibu"]} | ({home["ibu"]} if home else set()))
            if f:
                where = templates.a_site_txt(last[0][0]["site"])
                pod = f", {f['podiums']} podium{'s' if f['podiums'] > 1 else ''}" if f["podiums"] else ""
                items.append(("EN FORME", f["name"], f["nat"], f"{f['pts']} pts {where}{pod}"))
                facts.append(f"En forme : {f['name']} ({f['nat']}), {f['pts']} points {where}.")
        enjeux[cat] = items
    slides = templates.programme(site, day_list, len(metas), len(days), enjeux)
    fb = [f"📅 Le programme de la Coupe du monde de biathlon {templates.a_site_txt(site)}",
          f"{len(metas)} courses en {len(days)} jours, heures françaises dans le carrousel 👉",
          "Enregistrez le post pour ne rien manquer. Quelle course attendez-vous le plus ?"]
    cap = captions.generic("programme du week-end", "\n".join(facts), "", "\n".join(fb), [site, "programme"])
    produce(st, f"prog:{ev['EventId']}", "programme", slides, cap["caption"], templates.story_programme(site, day_list))


def snapshot(st, S: Season, ev):
    key = str(ev["EventId"])
    if key in st["snapshots"]:
        return
    st["snapshots"][key] = {cat: {r["ibu"]: r["rank"] for r in stats.standings(S.c, S.id, cat)} for cat in ("SM", "SW")}


def p_classement(st, S: Season, ev):
    races = S.finished_races()
    if not races:
        return  # premier week-end de la saison : rien a classer
    site = S.comps(ev)[0]["site"]
    first_race = min(m["start"] for m, _ in races).date()
    slides_data, facts = [], []
    for cat in ("SM", "SW"):
        rows = stats.standings(S.c, S.id, cat)
        if not rows:
            continue
        a, b = rows[0], rows[1]
        d = a['score'] - b['score']
        head = f"Égalité en tête entre {a['last']} et {b['last']}" if d == 0 else f"{d} point{'s' if d > 1 else ''} entre {a['last']} et {b['last']}"
        facts.append(f"{config.CATEGORIES[cat]} : {a['name']} {a['score']} pts, {b['name']} {b['score']} pts.")
        slides_data.append((f"CLASSEMENT GÉNÉRAL · {config.CATEGORIES[cat].upper()}", rows, head, f"Après {len(races)} courses · ⬤ dossard jaune", False, cat))
        births = stats.birth_map(S.c, [m["race_id"] for m, _ in races if m["cat"] == cat][-2:])
        young = stats.u23_standings(S.c, rows, first_race, births=births)
        for i, y in enumerate(young):
            y["young_rank"] = i + 1
        if young:
            slides_data.append((f"CLASSEMENT U23 · {config.CATEGORIES[cat].upper()}", young, f"{young[0]['name']}, {'meilleure' if cat == 'SW' else 'meilleur'} jeune", "Moins de 23 ans · (rang au général)", True, cat))
    total = len(slides_data)
    slides = [templates.standings_slide(k, r, h, f"Avant {templates.apres_site(site)}", i + 1, total, n, y, c)
              for i, (k, r, h, n, y, c) in enumerate(slides_data)]
    fb = [f"📊 Le classement général de la Coupe du monde de biathlon avant {templates.apres_site(site)}"] + facts + ["Qui finira en jaune cette saison ?"]
    cap = captions.generic("classements généraux avant l'étape", "\n".join(facts), "", "\n".join(fb), [site, "classementgeneral"])
    produce(st, f"gen:{ev['EventId']}", "classement", slides, cap["caption"])


KEY_POINT = {
    "SP": "Le point clé : le tir debout. 1 faute = environ 25 s perdues.",
    "PU": "Le point clé : les écarts du sprint fixent l'ordre de départ.",
    "MS": "Le point clé : le dernier tir debout, souvent décisif.",
    "IN": "Le point clé : chaque faute coûte 1 minute.",
    "SI": "Le point clé : chaque faute coûte 45 secondes.",
}


def p_pre_race(st, S: Season, m: dict, ev):
    d = config.DISCIPLINES[m["disc"]]
    stages = d["stages"]
    tirs = f"{len(stages)} tirs ({', '.join(dict.fromkeys(s.lower() for s in stages))})"
    pen = d["penalty"]
    if m["disc"] in ("IN", "SI") and m.get("penalty_s"):
        ps = m["penalty_s"]
        pen = f"{ps // 60} min ajoutée par faute" if ps % 60 == 0 else f"{ps} s ajoutées par faute"
    lines = [("Format", f"{d['laps']} tours · {tirs}"), ("Pénalité", pen)]
    site = config.SITES.get(m["site_key"] or "", {})
    if site.get("altitude"):
        lines.append(("Altitude", f"{site['altitude']} m"))
    if site.get("profile"):
        lines.append(("Parcours", site["profile"]))
    if w := weather(m, S.c):
        lines.append(("Météo", w))
    season_rows = S.finished_races()
    start_list = None
    if m["disc"] == "PU":
        sprint = next(((sm, r) for sm, r in season_rows if sm["event_id"] == m["event_id"] and sm["disc"] == "SP" and sm["cat"] == m["cat"]), None)
        start_list = [r for r in sprint[1] if r["rank"]] if sprint else None
    fallback = stats.standings(S.c, S.id, m["cat"])
    if not fallback or fallback[0]["score"] == 0:
        prev = S.previous_id()
        fallback = [{**r, "why_prefix": f"saison {prev[:2]}-{prev[2:]}"} for r in stats.standings(S.c, prev, m["cat"])]
    favs = stats.favorites(m, season_rows, fallback, start_list)
    feed, story = templates.pre_race(m, m["label"], lines, favs, KEY_POINT.get(m["disc"], ""))
    facts = [f"{m['label']} à {m['site']}, départ {m['start'].strftime('%H:%M')}."] + [f"Favori : {f['name']} ({f['nat']}), {f['why']}." for f in favs]
    if not [r for mm, r in season_rows if mm["cat"] == m["cat"]]:
        facts.append("Première course de la saison pour cette catégorie : pas encore de classement général cette saison.")
    fb = [f"⏱️ {m['label']} {templates.a_site_txt(m['site'])}, départ à {m['start'].strftime('%H:%M')}",
          "Nos favoris : " + ", ".join(f["name"] for f in favs) + ".",
          "Votre pronostic pour la victoire ? 👇"]
    cap = captions.generic("avant la course", "\n".join(facts), m["label"], "\n".join(fb), [m["site"]] + [f["name"] for f in favs[:1]])
    produce(st, f"pre:{m['race_id']}", "avant_course", [feed], cap["caption"], story, expires=m["start"])


def p_grille(st, S: Season, m: dict):
    """Story 1 h avant : grille de depart (ou compositions pour un relais)."""
    payload = S.c.results(m["race_id"])
    if m["relay"]:
        teams = stats.relay_lineups(payload)
        if not teams:
            raise NotReady("compositions des relais pas encore publiees")
        fra = [t for t in teams if t["nat"] == config.HOME_NAT]
        others = [t for t in teams if t["nat"] != config.HOME_NAT][: 3 - len(fra)]
        story = templates.story_relais(m, fra + others)
    else:
        grid = stats.start_grid(payload)
        if len(grid) < 3:
            raise NotReady("liste de depart pas encore publiee")
        fem = m["cat"] == "SW"
        o = stats.ordinal_f if fem else stats.ordinal
        gen = stats.standings(S.c, S.id, m["cat"])
        if not gen or gen[0]["score"] == 0:
            gen = stats.standings(S.c, S.previous_id(), m["cat"])
        rank = {g["ibu"]: g["rank"] for g in gen}
        births = stats.birth_map(S.c, [m["race_id"]])
        first_race = min([mm["start"] for mm, _ in S.finished_races()], default=m["start"]).date()
        young = [x for x in grid if x["ibu"] in births and
                 first_race.year - births[x["ibu"]].year - ((first_race.month, first_race.day) < (births[x["ibu"]].month, births[x["ibu"]].day)) < 23]
        best_young = min(young, key=lambda x: rank.get(x["ibu"], 999), default=None)
        keep = []
        for x in grid:
            tags = []
            if rank.get(x["ibu"], 99) <= 3:
                tags.append(f"{o(rank[x['ibu']])} général")
            if best_young and x["ibu"] == best_young["ibu"]:
                tags.append("U23")
            if tags or x["nat"] == config.HOME_NAT:
                keep.append({**x, "tags": tags})
        mode = {"PU": "retard", "MS": "ordre"}.get(m["disc"], "heure")
        story = templates.story_grille(m, keep, mode)
    produce(st, f"grid:{m['race_id']}", "grille", [], "", story, expires=m["start"])


def p_depart(st, S: Season, m: dict):
    """Story « C'est parti ! » au depart : publiee sans validation (aucun chiffre, et un clic
    tardif la rendrait inutile)."""
    favs = []
    if not m["relay"]:
        season_rows = S.finished_races()
        fallback = stats.standings(S.c, S.id, m["cat"])
        if not fallback or fallback[0]["score"] == 0:
            fallback = stats.standings(S.c, S.previous_id(), m["cat"])
        start_list = None
        if m["disc"] == "PU":
            sprint = next(((sm, r) for sm, r in season_rows if sm["event_id"] == m["event_id"] and sm["disc"] == "SP" and sm["cat"] == m["cat"]), None)
            start_list = [r for r in sprint[1] if r["rank"]] if sprint else None
        favs = stats.favorites(m, season_rows, fallback, start_list)
    produce(st, f"go:{m['race_id']}", "depart", [], "", templates.story_depart(m, favs),
            expires=m["start"] + dt.timedelta(minutes=30), auto=True)


def le(label: str) -> str:
    """« le sprint », « l'individuel »."""
    l = label.lower()
    if l.startswith(("poursuite", "mass start")):
        return "la " + l
    return ("l'" if l[:1] in "aeiouyéèêh" else "le ") + l


def fautes(n) -> str:
    n = n or 0
    return "sans faute" if n == 0 else f"{n} faute{'s' if n > 1 else ''}"


def p_post_race(st, S: Season, m: dict, payload: dict):
    if m["relay"]:
        teams = stats.relay_results(payload)
        if not teams or not teams[0]["rank"]:
            raise NotReady("relais sans classement")
        home = next((t for t in teams if t["nat"] == config.HOME_NAT), None)
        win_fr = templates.NAT_FR.get(teams[0]["nat"], teams[0]["nat"])
        head = (f"La France gagne le relais" if teams[0]["nat"] == config.HOME_NAT else
                f"{win_fr} gagne" + (f", la France {stats.ordinal_f(home['rank'])}" if home else ""))
        facts = [f"Vainqueur : {win_fr}."] + ([f"France : {home['rank']}e, {home['penalties']} tour(s) de pénalité."] if home else [])
        fb = [f"🏆 {head} {templates.a_site_txt(m['site'])}", f"Le classement du {m['label'].lower()} de Coupe du monde de biathlon.",
              {"SW": "Votre relayeuse du jour ?", "SM": "Votre relayeur du jour ?"}.get(m["cat"], "Votre relayeur ou relayeuse du jour ?")]
        cap = captions.generic("résultat de relais", "\n".join(facts), head, "\n".join(fb), [m["site"], "relais"])
        produce(st, f"post:{m['race_id']}", "relais", templates.relay_image(m, teams, cap["headline"] or head), cap["caption"])
        return
    rows = stats.individual_results(S.c, m["race_id"], payload)
    fin = [r for r in rows if r["rank"]]
    if len(fin) < 3:
        raise NotReady("moins de 3 classes")
    start_ranks = None
    if m["disc"] == "PU":
        sprint = next((r for sm, r in S.finished_races() if sm["event_id"] == m["event_id"] and sm["disc"] == "SP" and sm["cat"] == m["cat"]), None)
        if sprint:
            start_ranks = {r["ibu"]: r["rank"] for r in sprint if r["rank"]}
    cands = stats.stat_candidates(m, rows, start_ranks)
    home = [r for r in fin if r["nat"] == config.HOME_NAT]
    w = fin[0]
    facts = [f"1. {w['name']} ({w['nat']}) en {stats.fmt_time(w['time_s'])}, {w['misses_total']} faute(s).",
             f"2. {fin[1]['name']} ({fin[1]['nat']}) {stats.fmt_gap(fin[1]['behind_s'])}.",
             f"3. {fin[2]['name']} ({fin[2]['nat']}) {stats.fmt_gap(fin[2]['behind_s'])}."]
    facts += [f"Français : {r['name']} {r['rank']}e ({r['misses_total']} faute(s))." for r in home[:6]]
    o = stats.ordinal_f if m["cat"] == "SW" else stats.ordinal
    best = home[0] if home else None
    fb = [f"🏆 {w['name']} remporte {le(m['label'])} {templates.a_site_txt(m['site'])}",
          f"Coupe du monde de biathlon, le podium : {w['name']}, {fin[1]['name']} ({stats.fmt_gap(fin[1]['behind_s'])}), {fin[2]['name']} ({stats.fmt_gap(fin[2]['behind_s'])}).",
          (f"🇫🇷 {'Meilleure Française' if m['cat'] == 'SW' else 'Meilleur Français'} : {best['name']}, {o(best['rank'])}." if best else ""),
          f"Ski, tir et fiche de {'chaque Bleue' if m['cat'] == 'SW' else 'chaque Bleu'} dans le carrousel 👉",
          "Qui vous a le plus impressionné aujourd'hui ?"]
    tags = [m["site"], w["name"]] + ([best["name"]] if best else [])
    cap = captions.post_race(m, "\n".join(facts), cands, f"{w['last']} s'impose {templates.a_site_txt(m['site'])}",
                             "\n".join(x for x in fb if x), tags)
    slides = templates.results_carousel(m, rows, cap["headline"], cap.get("stat"))
    podium_alt = (f"Podium {('du ' + le(m['label'])[3:]) if le(m['label']).startswith('le ') else 'de ' + le(m['label'])} de Coupe du monde de biathlon {templates.a_site_txt(m['site'])} : "
                  f"1. {w['name']} ({w['nat']}), 2. {fin[1]['name']} ({fin[1]['nat']}), 3. {fin[2]['name']} ({fin[2]['nat']}).")
    alts = ["Top 10 : " + ", ".join(f"{r['rank']}. {r['name']} ({r['nat']}, {fautes(r['misses_total'])})" for r in fin[:10]) + "."]
    if cap.get("stat"):
        alts.append(f"Stat du jour : {cap['stat']['headline']}. {cap['stat']['detail']}")
    for r in home:
        ski = f", {o(r['ski'][1])} temps de ski" if r["ski"] else ""
        alts.append(f"Fiche de {r['name']} : {o(r['rank'])}{ski}, {r['shots'] - (r['misses_total'] or 0)}/{r['shots']} au tir.")
    alts = alts[: len(slides) - 1]
    if len(slides) - 1 > len(alts):
        shown = len(alts) - (2 if cap.get("stat") else 1)
        alts.append("Les autres Français : " + ", ".join(f"{r['name']} {o(r['rank'])}" for r in home[shown:]) + ".")
    alts.append(podium_alt)
    clean = stats.clean_sheets(rows)
    best_shooters = sorted([r for r in fin if r["shots"]], key=lambda r: (r["misses_total"] or 0, r["rank"]))[:5]
    stories = ([templates.story_bleus(m, home)] if home else []) + [templates.story_sans_faute(m, clean, best_shooters)]
    if start_ranks:
        mv = stats.pursuit_moves(rows, start_ranks, config.HOME_NAT)
        if mv.get("up") or mv.get("down"):
            stories.append(templates.story_poursuite(m, mv))
    produce(st, f"post:{m['race_id']}", "apres_course", slides, cap["caption"], stories, alts=alts)


def p_bilan(st, S: Season, ev):
    metas = S.comps(ev)
    site = metas[0]["site"] if metas else ""
    ev_races = [(m, r) for m, r in S.finished_races() if m["event_id"] == ev["EventId"]]
    podiums = sum(1 for _, rows in ev_races for r in rows if r["nat"] == config.HOME_NAT and r["rank"] and r["rank"] <= 3)
    wins = sum(1 for _, rows in ev_races for r in rows if r["nat"] == config.HOME_NAT and r["rank"] == 1)
    hits = sum(r["shots"] - (r["misses_total"] or 0) for _, rows in ev_races for r in rows if r["nat"] == config.HOME_NAT)
    shots = sum(r["shots"] for _, rows in ev_races for r in rows if r["nat"] == config.HOME_NAT)
    snap = st["snapshots"].get(str(ev["EventId"]), {})
    mv, leader_change = {}, []
    for cat in ("SM", "SW"):
        rows = stats.standings(S.c, S.id, cat)
        before = snap.get(cat) or {}
        if rows and before:
            mv[cat] = stats.movers(before, rows)
            old = next((k for k, v in before.items() if v == 1), None)
            if old and old != rows[0]["ibu"]:
                leader_change.append(rows[0])
    figures = [(str(podiums), "podiums français"), (str(wins), "victoires françaises")]
    if shots:
        figures.append((f"{round(100 * hits / shots)} %", "au tir pour les Bleus"))
    figures.append((str(len(ev_races)), "courses individuelles"))
    head = f"{leader_change[0]['name']} prend le dossard jaune" if leader_change else f"{site} : {podiums} podium(s) français"
    facts = [f"{site} : {podiums} podiums français, {wins} victoires, {len(ev_races)} courses individuelles."]
    if shots:
        facts.append(f"Tir des Français : {round(100 * hits / shots)} %.")
    for lc in leader_change:
        facts.append(f"Nouveau leader : {lc['name']}.")
    fb = [f"🏁 {head}", f"Le bilan de l'étape de Coupe du monde de biathlon {templates.a_site_txt(site)}."] + facts[1:] + ["Votre moment fort du week-end ?"]
    cap = captions.generic("bilan de l'étape", "\n".join(facts), head, "\n".join(fb), [site, "bilan"])
    relays = S.finished_relays()
    pen = {"week": stats.penalty_counts(ev_races, [(m, t) for m, t in relays if m["event_id"] == ev["EventId"]]),
           "season": stats.penalty_counts(S.finished_races(), relays)}
    produce(st, f"bilan:{ev['EventId']}", "bilan", templates.bilan(site, cap["headline"], figures, mv, pen), cap["caption"])


def p_bleus(st, S: Season, ev, cat: str):
    season_races = [(m, r) for m, r in S.finished_races() if m["cat"] == cat]
    ev_races = [(m, r) for m, r in season_races if m["event_id"] == ev["EventId"]]
    if not ev_races:
        return
    site = ev_races[0][0]["site"]
    gen = {r["ibu"]: r for r in stats.standings(S.c, S.id, cat)}
    ids = []
    for _, rows in ev_races:
        for r in rows:
            if r["nat"] == config.HOME_NAT and r["ibu"] not in ids:
                ids.append(r["ibu"])
    athletes = []
    for ibu in ids:
        a = stats.athlete_week(ibu, ev_races, season_races)
        ref = next(r for _, rows in ev_races for r in rows if r["ibu"] == ibu)
        g = gen.get(ibu, {})
        athletes.append({**a, "name": ref["name"], "first": ref["first"], "last": ref["last"],
                         "gen_rank": g.get("rank"), "score": g.get("score", 0)})
    athletes.sort(key=lambda a: a["gen_rank"] or 999)
    facts = [f"{a['name']} : meilleur résultat {a['week']['best']}e, tir {a['week']['tir']} %, {a['gen_rank']}e au général." for a in athletes]
    who = "Françaises" if cat == "SW" else "Français"
    fb = [f"🇫🇷 Le week-end des {who} {templates.a_site_txt(site)}",
          "Résultats, tir et forme de chaque athlète, week-end et saison, dans le carrousel 👉",
          f"{'Quelle Française' if cat == 'SW' else 'Quel Français'} vous a le plus marqué ?"]
    cap = captions.generic(f"bilan des {who}", "\n".join(facts), f"Le week-end des {who}", "\n".join(fb),
                           ["equipedefrance"] + [a["name"] for a in athletes[:1]])
    produce(st, f"bleus:{ev['EventId']}:{cat}", "bleus", templates.bleus(cat, site, athletes), cap["caption"])


def p_duel(st, S: Season, ev):
    """Mardi : leader du general contre le meilleur Francais (ou le 2e si le leader est francais), femmes puis hommes."""
    races = S.finished_races()
    site = next((m["site"] for m, _ in races if m["event_id"] == ev["EventId"]), None)
    if not site:
        return
    slides, facts, names = [], [], []
    duels = []
    for cat in ("SW", "SM"):
        d = stats.duel(stats.standings(S.c, S.id, cat), [(m, r) for m, r in races if m["cat"] == cat], config.HOME_NAT)
        if d:
            duels.append((cat, d))
    for i, (cat, d) in enumerate(duels):
        slides.append(templates.duel(cat, site, d, i + 1, len(duels)))
        a, b = d["a"], d["b"]
        o = stats.ordinal_f if cat == "SW" else stats.ordinal
        facts.append(f"{'Femmes' if cat == 'SW' else 'Hommes'} : {a['name']} ({a['nat']}, {o(1)} du général, {a['score']} pts, "
                     f"{a['wins']} victoire(s)) contre {b['name']} ({b['nat']}, {o(b['rank'])}, {b['score']} pts, {b['wins']} victoire(s)). "
                     f"Écart {d['gap']} pts. Face-à-face cette saison : {d['h2h'][0]}-{d['h2h'][1]}.")
        names += [a["name"], b["name"]]
    if not slides:
        return
    fb = ["⚔️ Le duel de la semaine", "\n".join(facts), "Qui finira devant à la fin de la saison ?"]
    cap = captions.generic("duel de la semaine (comparaison de deux athlètes au général)", "\n".join(facts),
                           "Le duel de la semaine", "\n\n".join(fb), ["duel"] + names[:2])
    produce(st, f"duel:{ev['EventId']}", "duel", slides, cap["caption"])


def _season_minus(sid: str, k: int) -> str:
    return f"{int(sid[:2]) - k:02d}{int(sid[2:]) - k:02d}"


def last_visit(S: Season, ev, max_back: int = 3):
    """Derniere etape au meme site sur les `max_back` saisons precedentes : (saison, k, courses) ou None."""
    key = stats.race_meta({}, ev)["site_key"]
    if not key:
        return None
    for k in range(1, max_back + 1):
        sid = _season_minus(S.id, k)
        try:
            evs = S.c.events(sid, config.WC_LEVEL)
        except Exception:
            continue
        for pev in evs:
            if stats.race_meta({}, pev)["site_key"] != key:
                continue
            races = []
            for c in S.c.competitions(pev["EventId"]):
                m = stats.race_meta(c, pev)
                if m["relay"] or not m["start"]:
                    continue
                try:
                    rows = stats.individual_results(S.c, m["race_id"], S.c.results(m["race_id"], cache_s=30 * 86400))
                except Exception:
                    continue
                if any(r["rank"] for r in rows):
                    races.append((m, rows))
            if races:
                return sid, k, sorted(races, key=lambda x: x[0]["start"])
    return None


def p_an_dernier(st, S: Season, ev):
    found = last_visit(S, ev)
    if not found:
        print(f"[an dernier] pas de donnees sur 3 saisons pour {ev.get('Organizer')}")
        return
    sid, k, races = found
    site = races[0][0]["site"]
    label = f"20{sid[:2]}-{sid[2:]}"
    by_cat = {}
    facts = []
    for m, rows in races:
        fin = [r for r in rows if r["rank"]]
        fr = next((r for r in fin if r["nat"] == config.HOME_NAT), None)
        by_cat.setdefault(m["cat"], []).append((m, fin[:3], fr))
        facts.append(f"{m['label']} : 1. {fin[0]['name']} ({fin[0]['nat']})"
                     + (f", 2. {fin[1]['name']} ({fin[1]['nat']})" if len(fin) > 1 else "")
                     + (f", 3. {fin[2]['name']} ({fin[2]['nat']})" if len(fin) > 2 else "")
                     + (f" ; meilleur Français : {fr['name']}, {fr['rank']}e" if fr else "") + ".")
    hl = stats.past_highlights(races, config.HOME_NAT)
    facts += [f"{h['label']} : {h['big']} ({h['sub']})." for h in hl]
    when = "l'an dernier" if k == 1 else f"la dernière fois (saison {label})"
    facts.insert(0, f"Ces résultats datent de la saison {label}, {when} {templates.a_site_txt(site)}. Ce ne sont PAS des résultats de cette saison.")
    fb = [f"🔙 {'L’an dernier' if k == 1 else 'La dernière fois'} {templates.a_site_txt(site)} (saison {label})",
          "Les podiums femmes et hommes et les chiffres à retenir, dans le carrousel 👉",
          "Qui va faire mieux cette année ?"]
    cap = captions.generic("rappel de la dernière étape au même site (saison passée)", "\n".join(facts),
                           "L'an dernier ici", "\n".join(fb), [site])
    produce(st, f"ici:{ev['EventId']}", "an_dernier", templates.last_time(site, label, k == 1, by_cat, hl), cap["caption"])


def _birthdays(S: Season, start: dt.date, days: int) -> list[dict]:
    races = S.finished_races()
    births = stats.birth_map(S.c, [m["race_id"] for m, _ in races])
    return stats.birthdays(races, births, start, days, config.HOME_NAT)


def p_anniversaire(st, S: Season, a: dict):
    races = [(m, r) for m, r in S.finished_races() if m["cat"] == a["cat"]]
    gen = {g["ibu"]: g for g in stats.standings(S.c, S.id, a["cat"])}
    g = gen.get(a["ibu"], {"ibu": a["ibu"], "rank": None, "score": 0, "nat": a["nat"]})
    card = stats.season_card(g, races)
    story = templates.story_anniversaire(a, card, g.get("rank"), g.get("score", 0))
    produce(st, f"anniv:{a['ibu']}:{a['day'].year}", "anniversaire", [], f"🎂 Joyeux anniversaire {a['name']} ({a['age']} ans)",
            story=story, expires=NOW.replace(hour=22, minute=0))


def birthdays_todo(st, S: Season, now: dt.datetime) -> list:
    """Story a 9h le jour J ; liste des 7 prochains jours envoyee sur Telegram le lundi (verification a l'avance)."""
    if now.hour < config.SCHEDULE["anniversaire_hour"] or not S.finished_races():
        return []
    today = now.date()
    if st.get("anniv_list") != today.isoformat() and now.weekday() == 0:
        st["anniv_list"] = today.isoformat()
        nxt = _birthdays(S, today, 7)
        lines = [f"{a['day'].strftime('%d/%m')} : {a['name']} ({a['age']} ans)" for a in nxt] or ["aucun"]
        print("[anniversaires] 7 prochains jours :", "; ".join(lines))
        publish.notify("🎂 Anniversaires des 7 prochains jours (story à 9h) :\n" + "\n".join(lines))
    return [(f"anniv:{a['ibu']}:{today.year}", lambda a=a: p_anniversaire(st, S, a)) for a in _birthdays(S, today, 1)]


def p_reel(st, S: Season, m: dict):
    """Reel « Revivre la course » : la course rejouee tir par tir (courses individuelles)."""
    from . import reel
    nr = len(config.DISCIPLINES.get(m["disc"], {}).get("stages") or [])
    course = reel.course_info(S.c, m["race_id"])
    data = reel.build({**m, "km": m["_comp"].get("km"), "course": course}, reel.load_rows(S.c, m["race_id"], nr))
    if not data or len(data["focus"]) < 3:
        raise NotReady("temps par tour pas encore publies")
    h = data["hooks"]["vainqueur"]
    w = data["podium"][0]
    facts = [f"Vainqueur : {w['first']} {w['last']} ({w['nat']}), {h['sub']}."]
    for k, stt in enumerate(data["standings"]):
        facts.append(f"Après le tir {k + 1} : 1. {stt[0]['last']}, 2. {stt[1]['last']}, 3. {stt[2]['last']}.")
    if data["best_fr"]:
        facts.append(f"Meilleur Français : {data['best_fr']['name']}, {data['best_fr']['rank']}.")
    fb = [f"⏪ Revivez {le(m['label'])} {templates.a_site_txt(m['site'])}, tir par tir",
          f"{w['last'].title()} s'impose, {h['sub'].lower()}.",
          "À quel tir la course s'est-elle jouée ? 👇"]
    cap = captions.generic("Reel qui rejoue la course tir par tir", "\n".join(facts), "Revivre la course", "\n".join(fb),
                           [m["site"], f"{w['first']} {w['last']}"])
    path = OUT / f"reel:{m['race_id']}".replace(":", "_") / "reel.mp4"
    reel.record(data, path)
    produce_video(st, f"reel:{m['race_id']}", "reel", path, cap["caption"], thumb_ms=1600)


# ================================================================ boucle

def finished(st: dict, key: str) -> bool:
    """Post deja traite : tout sauf une erreur qui a encore droit a un nouvel essai."""
    p = st["posts"].get(key)
    return bool(p) and not (p.get("status") == "error" and p.get("attempts", 1) < 3)


def at(now, rule) -> bool:
    return now.weekday() == rule["weekday"] and now.hour >= rule["hour"]


def run(now: dt.datetime):
    global NOW
    NOW = now
    st = load_state()
    try:
        _run(st, now)
    finally:
        save_state(st)  # meme en cas d'erreur, pour ne pas perdre les decisions deja prises


def _run(st: dict, now: dt.datetime):
    handle_decisions(st, now)
    S = Season(Client(), now)
    todo = []

    up = S.upcoming(days=6)
    if up and at(now, config.SCHEDULE["programme"]):
        todo.append((f"prog:{up['EventId']}", lambda: p_programme(st, S, up)))
    if up:
        first, _ = S.race_span(up)
        if first and (first.date() - now.date()).days <= 2:
            snapshot(st, S, up)  # juste avant l'etape : base du "qui monte, qui descend"
        if at(now, config.SCHEDULE["an_dernier"]):
            todo.append((f"ici:{up['EventId']}", lambda: p_an_dernier(st, S, up)))
        if at(now, config.SCHEDULE["classement"]):
            todo.append((f"gen:{up['EventId']}", lambda: p_classement(st, S, up)))

    for ev in filter(None, {id(x): x for x in (S.running(), up)}.values()):
        for m in S.comps(ev):
            delta = (m["start"] - now).total_seconds() / 60
            if 40 <= delta <= 70:
                todo.append((f"grid:{m['race_id']}", lambda m=m: p_grille(st, S, m)))
            if -15 <= delta <= 2 and now >= m["start"] - dt.timedelta(minutes=2):
                todo.append((f"go:{m['race_id']}", lambda m=m: p_depart(st, S, m)))
            if not m["relay"] and 30 <= delta <= config.SCHEDULE["pre_race_minutes"]:
                todo.append((f"pre:{m['race_id']}", lambda m=m, ev=ev: p_pre_race(st, S, m, ev)))
            if -12 * 60 <= delta < -20 and not finished(st, f"post:{m['race_id']}"):
                payload = S.c.results(m["race_id"])
                ok = stats.is_official(payload, m["_comp"])
                print(f"[statut] {m['race_id']} : '{stats.status_text(payload, m['_comp'])}' officiel={ok}")
                sig = hashlib.md5(json.dumps([(r.get("Rank"), r.get("IBUId"), r.get("TotalTime")) for r in (payload.get("Results") or [])[:30]]).encode()).hexdigest()
                w = st["watch"].setdefault(m["race_id"], {})
                stable = w.get("sig") == sig and delta < -60 and stats.has_results(payload, 10)
                w["sig"] = sig
                w["status"] = stats.status_text(payload, m["_comp"])
                if ok or stable:
                    todo.append((f"post:{m['race_id']}", lambda m=m, p=payload: p_post_race(st, S, m, p)))
            post = st["posts"].get(f"post:{m['race_id']}") or {}
            if (config.REEL and not m["relay"] and -12 * 60 <= delta < -20 and post.get("status") in ("pending", "published")
                    and not finished(st, f"reel:{m['race_id']}")):
                todo.append((f"reel:{m['race_id']}", lambda m=m: p_reel(st, S, m)))

    done = S.just_ended()
    if done and at(now, config.SCHEDULE["bilan"]):
        todo.append((f"bilan:{done['EventId']}", lambda: p_bilan(st, S, done)))
    if done and at(now, config.SCHEDULE["bleus"]):
        for cat in ("SM", "SW"):
            todo.append((f"bleus:{done['EventId']}:{cat}", lambda cat=cat: p_bleus(st, S, done, cat)))
    if done and at(now, config.SCHEDULE["duel"]):
        todo.append((f"duel:{done['EventId']}", lambda: p_duel(st, S, done)))
    todo += birthdays_todo(st, S, now)

    for key, fn in todo:
        prev = st["posts"].get(key)
        if finished(st, key):
            continue
        try:
            fn()
            st["posts"].setdefault(key, {"status": "skipped"})
        except NotReady as nr:
            print(f"[attente] {key} : {nr}")
        except Exception as exc:
            traceback.print_exc()
            attempts = (prev or {}).get("attempts", 0) + 1
            if attempts >= 3:
                publish.notify(f"⚠️ Erreur en préparant {key} (3 essais) : {exc}")
            st["posts"][key] = {"status": "error", "error": str(exc)[:500], "attempts": attempts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="heure simulee, ex. 2026-12-17T10:00 (heure de Paris)")
    a = ap.parse_args()
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=config.TZ) if a.now else dt.datetime.now(config.TZ)
    run(now)


if __name__ == "__main__":
    main()
