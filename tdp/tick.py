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

    def previous_id(self) -> str:
        a, b = int(self.id[:2]), int(self.id[2:])
        return f"{a - 1:02d}{b - 1:02d}"

    def ev_dates(self, ev):
        s, e = stats.parse_dt(ev.get("StartDate")), stats.parse_dt(ev.get("EndDate"))
        return (s.date() if s else None), (e.date() if e else None)

    def comps(self, ev) -> list[dict]:
        out = [stats.race_meta(c, ev) | {"_comp": c} for c in self.c.competitions(ev["EventId"])]
        return sorted([m for m in out if m["start"]], key=lambda m: m["start"])

    def upcoming(self, days=7):
        for ev in self.events:
            s, e = self.ev_dates(ev)
            if s and 0 <= (s - self.now.date()).days <= days:
                return ev
        return None

    def running(self):
        for ev in self.events:
            s, e = self.ev_dates(ev)
            if s and e and s <= self.now.date() <= e:
                return ev
        return None

    def just_ended(self, max_days=4):
        best = None
        for ev in self.events:
            s, e = self.ev_dates(ev)
            if e and 0 < (self.now.date() - e).days <= max_days:
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


# ================================================================ production d'un post

def produce(st: dict, key: str, kind: str, slides: list[str], caption: str, story: str | None = None,
            expires: dt.datetime | None = None, alts: list[str] | None = None):
    folder = OUT / key.replace(":", "_")
    paths = render(slides + ([story] if story else []), folder, "s")
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    urls = [publish.upload(p, f"{key.replace(':', '/')}/{stamp}_{p.name}") for p in paths]
    story_url = urls.pop() if story else None
    if not alts:
        first = caption.strip().splitlines()[0] if caption.strip() else kind
        alts = [f"Tour de pénalité, statistiques de biathlon : {first} (visuel {i + 1}/{len(urls)})" for i in range(len(urls))]
    post = {"kind": kind, "status": "pending", "urls": urls, "story_url": story_url, "caption": caption, "alts": alts,
            "created": NOW.isoformat(),
            "expires": (expires or NOW + dt.timedelta(hours=20)).isoformat(),
            "files": [str(p) for p in paths]}
    st["posts"][key] = post
    if config.REQUIRE_APPROVAL:
        publish.send_for_approval(key, urls, caption, story_url)
    else:
        do_publish(st, key)
    print(f"[produit] {key} ({len(paths)} visuel(s))")


def do_publish(st: dict, key: str):
    p = st["posts"][key]
    try:
        if p["urls"]:
            p["ig_id"] = publish.publish_feed(p["urls"], p["caption"], p.get("alts"))
        if p.get("story_url"):
            p["ig_story_id"] = publish.publish_story(p["story_url"])
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
    enjeux, facts = [], [f"Étape : {site}, {len(metas)} courses sur {len(days)} jours."]
    for cat in ("SM", "SW"):
        rows = stats.standings(S.c, S.id, cat)
        if len(rows) >= 2 and rows[0]["score"] > 0:
            a, b = rows[0], rows[1]
            d = a["score"] - b["score"]
            enjeux.append((f"DOSSARD JAUNE · {config.CATEGORIES[cat].upper()}", f"{a['name']} ({a['nat']})", f"{d} pts d'avance sur {b['name']}" if d else f"À égalité avec {b['name']}"))
            facts.append(f"Leader {config.CATEGORIES[cat]} : {a['name']} {a['nat']}, {a['score'] - b['score']} points devant {b['name']}.")
            home = next((r for r in rows if r["nat"] == config.HOME_NAT), None)
            if home:
                facts.append(f"Meilleur(e) Français(e) {config.CATEGORIES[cat]} : {home['name']}, {home['rank']}e.")
    slides = templates.programme(site, day_list, len(metas), len(days), enjeux[:3])
    fb = [f"📅 Le programme de la Coupe du monde de biathlon {templates.a_site_txt(site)}",
          f"{len(metas)} courses en {len(days)} jours, heures françaises dans le carrousel 👉",
          "Enregistrez le post pour ne rien manquer. Quelle course attendez-vous le plus ?"]
    cap = captions.generic("programme du week-end", "\n".join(facts), "", "\n".join(fb), [site, "programme"])
    produce(st, f"prog:{ev['EventId']}", "programme", slides, cap["caption"])


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
    fb = [f"⏱️ {m['label']} {templates.a_site_txt(m['site'])}, départ à {m['start'].strftime('%H:%M')}",
          "Nos favoris : " + ", ".join(f["name"] for f in favs) + ".",
          "Votre pronostic pour la victoire ? 👇"]
    cap = captions.generic("avant la course", "\n".join(facts), m["label"], "\n".join(fb), [m["site"]] + [f["name"] for f in favs[:1]])
    produce(st, f"pre:{m['race_id']}", "avant_course", [feed], cap["caption"], story, expires=m["start"])


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
    fb = [f"🏆 {w['name']} remporte le {m['label'].lower()} {templates.a_site_txt(m['site'])}",
          f"Coupe du monde de biathlon, le podium : {w['name']}, {fin[1]['name']} ({stats.fmt_gap(fin[1]['behind_s'])}), {fin[2]['name']} ({stats.fmt_gap(fin[2]['behind_s'])}).",
          (f"🇫🇷 {'Meilleure Française' if m['cat'] == 'SW' else 'Meilleur Français'} : {best['name']}, {o(best['rank'])}." if best else ""),
          f"Ski, tir et fiche de {'chaque Bleue' if m['cat'] == 'SW' else 'chaque Bleu'} dans le carrousel 👉",
          "Qui vous a le plus impressionné aujourd'hui ?"]
    tags = [m["site"], w["name"]] + ([best["name"]] if best else [])
    cap = captions.post_race(m, "\n".join(facts), cands, f"{w['last']} s'impose {templates.a_site_txt(m['site'])}",
                             "\n".join(x for x in fb if x), tags)
    slides = templates.results_carousel(m, rows, cap["headline"], cap.get("stat"))
    alts = [f"Podium du {m['label'].lower()} de Coupe du monde de biathlon {templates.a_site_txt(m['site'])} : "
            f"1. {w['name']} ({w['nat']}), 2. {fin[1]['name']} ({fin[1]['nat']}), 3. {fin[2]['name']} ({fin[2]['nat']}).",
            "Top 10 : " + ", ".join(f"{r['rank']}. {r['name']} ({r['nat']}, {fautes(r['misses_total'])})" for r in fin[:10]) + "."]
    if cap.get("stat"):
        alts.append(f"Stat du jour : {cap['stat']['headline']}. {cap['stat']['detail']}")
    for r in home:
        ski = f", {o(r['ski'][1])} temps de ski" if r["ski"] else ""
        alts.append(f"Fiche de {r['name']} : {o(r['rank'])}{ski}, {r['shots'] - (r['misses_total'] or 0)}/{r['shots']} au tir.")
    alts = alts[: len(slides)]
    if len(slides) > len(alts):
        alts.append("Les autres Français : " + ", ".join(f"{r['name']} {o(r['rank'])}" for r in home[len(alts) - 3:]) + ".")
    produce(st, f"post:{m['race_id']}", "apres_course", slides, cap["caption"], alts=alts)


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
    produce(st, f"bilan:{ev['EventId']}", "bilan", templates.bilan(site, cap["headline"], figures, mv), cap["caption"])


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
        s0, _ = S.ev_dates(up)
        if (s0 - now.date()).days <= 2:
            snapshot(st, S, up)  # juste avant l'etape : base du "qui monte, qui descend"
        if at(now, config.SCHEDULE["classement"]):
            todo.append((f"gen:{up['EventId']}", lambda: p_classement(st, S, up)))

    for ev in filter(None, {id(x): x for x in (S.running(), up)}.values()):
        for m in S.comps(ev):
            delta = (m["start"] - now).total_seconds() / 60
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

    done = S.just_ended()
    if done and at(now, config.SCHEDULE["bilan"]):
        todo.append((f"bilan:{done['EventId']}", lambda: p_bilan(st, S, done)))
    if done and at(now, config.SCHEDULE["bleus"]):
        for cat in ("SM", "SW"):
            todo.append((f"bleus:{done['EventId']}:{cat}", lambda cat=cat: p_bleus(st, S, done, cat)))

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
