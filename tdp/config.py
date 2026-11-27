"""Reglages du bot Tour de penalite. Tout ce qui est modifiable a la main est ici."""
import os
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
HOME_NAT = "FRA"            # pays mis en avant
WC_LEVEL = 1                # 1 = Coupe du monde IBU

# Validation avant publication. False = publication directe (prevu a partir de janvier).
REQUIRE_APPROVAL = os.environ.get("TDP_REQUIRE_APPROVAL", "1") == "1"
# Simulation : aucun appel a Instagram, Telegram ou au stockage, images gardees en local.
DRY_RUN = os.environ.get("TDP_DRY_RUN", "0") == "1"
# Filigrane "MAQUETTE" sur les visuels (utile pour les tests).
WATERMARK = os.environ.get("TDP_WATERMARK", "0") == "1"

# Grille editoriale (heure de Paris)
SCHEDULE = {
    "programme": {"weekday": 2, "hour": 9},    # mercredi 9h
    "an_dernier": {"weekday": 2, "hour": 12},  # mercredi 12h
    "classement": {"weekday": 2, "hour": 15},  # mercredi 15h
    "pre_race_minutes": 120,                    # 2 h avant le depart
    "bilan": {"weekday": 0, "hour": 9},        # lundi 9h
    "bleus": {"weekday": 1, "hour": 9},        # mardi 9h
    "duel": {"weekday": 1, "hour": 13},        # mardi 13h
    "anniversaire_hour": 9,                     # chaque jour, 9h
}
REEL = os.environ.get("TDP_REEL", "1") == "1"   # Reel « Revivre la course » apres chaque course individuelle
MAX_CAROUSEL = 10            # limite Meta (doc officielle)
MAX_FR_SLIDES = 6            # au-dela, les Francais restants vont dans une slide tableau
FAVORITES_FORM_RACES = 5     # nb de courses prises en compte pour la forme

# Regles de format (connaissance generale du biathlon, a relire)
DISCIPLINES = {
    "SP": {"fr": "Sprint", "laps": 3, "stages": ["Couché", "Debout"], "penalty": "1 tour de 150 m par faute", "penalty_s": 25},
    "PU": {"fr": "Poursuite", "laps": 5, "stages": ["Couché", "Couché", "Debout", "Debout"], "penalty": "1 tour de 150 m par faute", "penalty_s": 25},
    "MS": {"fr": "Mass start", "laps": 5, "stages": ["Couché", "Couché", "Debout", "Debout"], "penalty": "1 tour de 150 m par faute", "penalty_s": 25},
    "IN": {"fr": "Individuel", "laps": 5, "stages": ["Couché", "Debout", "Couché", "Debout"], "penalty": "1 min ajoutée par faute", "penalty_s": 60},
    "SI": {"fr": "Individuel court", "laps": 5, "stages": ["Couché", "Debout", "Couché", "Debout"], "penalty": "45 s ajoutées par faute", "penalty_s": 45},
    "RL": {"fr": "Relais", "relay": True},
    "MR": {"fr": "Relais mixte", "relay": True},
    "SR": {"fr": "Relais mixte simple", "relay": True},
}
CATEGORIES = {"SM": "hommes", "SW": "femmes", "MX": "mixte"}

# Fiches sites : a completer une fois par saison. lat/lon servent a la meteo (open-meteo).
# Laisser profile a None tant que l'info n'est pas verifiee : la ligne n'apparait pas.
SITES = {
    "kontiolahti": {"name": "Kontiolahti", "lat": 62.77, "lon": 29.85, "altitude": None, "profile": None},
    "hochfilzen": {"name": "Hochfilzen", "lat": 47.47, "lon": 12.62, "altitude": None, "profile": None},
    "grand-bornand": {"name": "Le Grand-Bornand", "lat": 45.94, "lon": 6.43, "altitude": None, "profile": None},
    "pokljuka": {"name": "Pokljuka", "lat": 46.33, "lon": 13.93, "altitude": None, "profile": None},
    "ruhpolding": {"name": "Ruhpolding", "lat": 47.76, "lon": 12.64, "altitude": None, "profile": None},
    "antholz": {"name": "Antholz-Anterselva", "lat": 46.88, "lon": 12.17, "altitude": None, "profile": None},
    "nove mesto": {"name": "Nové Město", "lat": 49.56, "lon": 16.08, "altitude": None, "profile": None},
    "otep": {"name": "Otepää", "lat": 58.05, "lon": 26.47, "altitude": None, "profile": None},
    "oberhof": {"name": "Oberhof", "lat": 50.70, "lon": 10.73, "altitude": None, "profile": None},
    "oslo": {"name": "Oslo-Holmenkollen", "lat": 59.96, "lon": 10.67, "altitude": None, "profile": None},
    "ostersund": {"name": "Östersund", "lat": 63.17, "lon": 14.64, "altitude": None, "profile": None},
}

# Cles et services (secrets GitHub)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("TDP_CLAUDE_MODEL", "claude-sonnet-5-5")
IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
IG_API_VERSION = os.environ.get("IG_API_VERSION", "v27.0")
# Les apps Meta creees recemment passent par "Instagram API with Unified Login" (graph.facebook.com).
# Une ancienne app configuree avec Instagram Login utiliserait graph.instagram.com.
IG_GRAPH_HOST = os.environ.get("IG_GRAPH_HOST", "graph.facebook.com")
IG_MARK_AI = os.environ.get("TDP_IG_MARK_AI", "0") == "1"  # parametre is_ai_generated
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "tdp-posts")


# ----------------------------------------------------------------- themes visuels
THEME = os.environ.get("TDP_THEME", "neige")
FLASH = os.environ.get("TDP_FLASH")  # surcharge de la couleur flash (ex. #ff1f7a)
THEMES = {
    "nuit": {"mountains": False, "vars": {
        "bg": "#0d1117", "ink": "#f2f4f7", "grey": "#9aa4b2", "muted": "#6b7686", "row": "#151b24", "chip": "#1f2733",
        "line": "#222b37", "soft": "#c5ccd6", "fr": "#7da2ff", "fr-bg": "#16243f", "fr-strong": "#1d3fa8",
        "flash": "#ff5a1f", "on-flash": "#0d1117", "lead-bg": "#2a1a12", "bar": "#2b3442", "up": "#3ecf8e",
        "wm": "rgba(255,255,255,.05)"}},
    "neige": {"mountains": True, "vars": {
        "bg": "#f4f9fd", "bg-grad": "linear-gradient(180deg,#ffffff 0%,#eef6fc 55%,#e2eff9 100%)",
        "ink": "#0b2545", "grey": "#557089", "muted": "#7f97ad", "row": "#e8f2fa", "chip": "#dbe9f5",
        "line": "#d6e5f2", "soft": "#2f4a66", "fr": "#1f4fd6", "fr-bg": "#dbe6ff", "fr-strong": "#1f4fd6",
        "flash": "#ff2e7e", "on-flash": "#ffffff", "lead-bg": "color-mix(in srgb, var(--flash) 14%, #ffffff)", "bar": "#cfe1f1", "up": "#0e9f6e",
        "wm": "rgba(11,37,69,.05)", "mount1": "#c3dbef", "mount2": "#dbeaf6", "mount3": "#eaf3fa"}},
}
# Couleur flash selon la categorie : femmes, hommes, et posts generiques
# (programme, classements croises, bilan, relais mixtes).
FLASH_BY_CAT = {"SW": "#ff2e7e", "SM": "#7b2cff", None: "#ff5a00"}
if FLASH:  # pour tester une couleur unique partout
    FLASH_BY_CAT = {k: FLASH for k in FLASH_BY_CAT}
