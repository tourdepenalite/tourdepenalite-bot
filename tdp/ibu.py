"""Client de l'API (non officielle) de biathlonresults.com, le Datacenter IBU.

Points connus, d'apres les bibliotheques Python existantes :
- base : https://biathlonresults.com/modules/sportapi/api/
- l'API repond 401 sans en-tete "apikey". La cle est publique : le site la
  livre dans son JavaScript (window.ApiKey). On la relit quand l'API la refuse.
L'API peut changer sans preavis : toutes les lectures passent par .get().
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import time
from urllib.parse import urljoin

import requests

SITE = "https://biathlonresults.com/"
API = SITE + "modules/sportapi/api/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Referer": SITE,
}
_SCRIPT_SRC = re.compile(r"""<script[^>]*\ssrc=["']?([^"'\s>]+\.js)""", re.I)
_API_KEY = re.compile(r"""ApiKey\s*=\s*["']([0-9a-fA-F-]{36})["']""")

# Mode test : lit les reponses dans un dossier de fixtures au lieu du reseau.
FIXTURES = os.environ.get("TDP_IBU_FIXTURES")
CACHE_DIR = pathlib.Path(os.environ.get("TDP_CACHE_DIR", ".cache/ibu"))


class IBUError(Exception):
    pass


class Client:
    def __init__(self):
        self.key = os.environ.get("BIATHLONRESULTS_API_KEY")
        self.s = requests.Session()
        self.s.headers.update(HEADERS)

    # ---- bas niveau ----
    def _fetch_key(self) -> str | None:
        page = self.s.get(SITE, timeout=30)
        page.raise_for_status()
        scripts = [urljoin(SITE, s) for s in _SCRIPT_SRC.findall(page.text)]
        scripts.sort(key=lambda u: "app" not in u.rsplit("/", 1)[-1])
        for url in scripts:
            r = self.s.get(url, timeout=30)
            if r.ok and (m := _API_KEY.search(r.text)):
                return m.group(1)
        return None

    def get(self, method: str, cache_s: int = 0, **params):
        if FIXTURES:
            return _fixture(method, params)
        cache = CACHE_DIR / (method + "_" + "_".join(f"{k}-{v}" for k, v in sorted(params.items())) + ".json")
        if cache_s and cache.exists() and time.time() - cache.stat().st_mtime < cache_s:
            return json.loads(cache.read_text())
        for attempt in range(3):
            if not self.key:
                self.key = self._fetch_key()
            r = self.s.get(API + method, params=params, headers={"apikey": self.key or ""}, timeout=30)
            if r.status_code == 401:
                self.key = None
                continue
            if r.status_code >= 500:
                time.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if cache_s:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data))
            return data
        raise IBUError(f"{method} {params}: echec apres 3 essais")

    # ---- endpoints ----
    def current_season(self) -> str:
        seasons = self.get("Seasons", cache_s=86400)
        cur = next((s for s in seasons if s.get("IsCurrent")), None) or max(seasons, key=lambda s: s.get("SortOrder", 0))
        return str(cur["SeasonId"])

    def events(self, season: str, level: int = 1) -> list[dict]:
        return list(self.get("Events", cache_s=3600, SeasonId=season, Level=level))

    def competitions(self, event_id: str) -> list[dict]:
        return list(self.get("Competitions", cache_s=600, EventId=event_id))

    def results(self, race_id: str, cache_s: int = 0) -> dict:
        return dict(self.get("Results", cache_s=cache_s, RaceId=race_id))

    def analytic(self, race_id: str, type_id: str) -> dict:
        """CRST = temps de parcours (ski), RNGT = temps au pas de tir, STTM = temps de tir."""
        try:
            return dict(self.get("AnalyticResults", cache_s=3600, RaceId=race_id, TypeId=type_id))
        except Exception:
            return {}

    def cups(self, season: str) -> list[dict]:
        return list(self.get("Cups", cache_s=86400, SeasonId=season))

    def cup_results(self, cup_id: str) -> dict:
        return dict(self.get("CupResults", cache_s=600, CupId=cup_id))

    def bio(self, ibu_id: str) -> dict:
        try:
            return dict(self.get("CISBios", cache_s=30 * 86400, IBUId=ibu_id))
        except Exception:
            return {}

    def weather(self, race_id: str) -> dict:
        """Meteo officielle du stade (air, neige, vent). Vide si pas encore publiee."""
        try:
            return dict(self.get("weather", cache_s=600, RaceId=race_id) or {})
        except Exception:
            return {}

    def athletes(self, race_id: str) -> list[dict]:
        """Athletes d'une course, avec leur date de naissance (un seul appel)."""
        try:
            return list((self.get("Athletes", cache_s=86400, RaceId=race_id) or {}).get("Athletes") or [])
        except Exception:
            return []

    def reports(self, race_id: str) -> list[dict]:
        """Rapports PDF officiels de la course (liste de departs, resultats, analyse, donnees techniques...)."""
        try:
            return list(self.get("Reports", cache_s=3600, RaceId=race_id) or [])
        except Exception:
            return []

    def total_cup_id(self, season: str, cat: str, level: int = 1) -> str | None:
        for c in self.cups(season):
            if c.get("CatId") == cat and c.get("Level") == level and c.get("DisciplineId") == "TS":
                return str(c.get("CupId"))
        return None


def _fixture(method: str, params: dict):
    base = pathlib.Path(FIXTURES)
    key = {"Seasons": "seasons", "Events": "events", "Cups": "cups"}.get(method)
    if method == "Events" and (base / f"events_{params.get('SeasonId')}.json").exists():
        return json.loads((base / f"events_{params.get('SeasonId')}.json").read_text())
    if key:
        return json.loads((base / f"{key}.json").read_text())
    arg = next(iter(params.values()), "")
    extra = params.get("TypeId")
    name = f"{method}_{arg}" + (f"_{extra}" if extra else "")
    f = base / f"{name}.json"
    if not f.exists():
        raise IBUError(f"fixture manquante : {f.name}")
    return json.loads(f.read_text())
