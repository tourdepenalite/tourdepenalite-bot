"""Gabarits HTML (1080x1350 pour le fil, 1080x1920 pour les stories)."""
from __future__ import annotations

from html import escape

from . import config
from .stats import fmt_gap, fmt_time, ordinal, ordinal_f

O, GREY, MUTED, FR_BG, ROW = "var(--flash)", "var(--grey)", "var(--muted)", "var(--fr-bg)", "var(--row)"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1080px;background:var(--bg-grad, var(--bg));color:var(--ink);font-family:'Inter Display','Inter',sans-serif;position:relative;overflow:hidden}
.top{position:absolute;top:56px;left:72px;right:72px;display:flex;justify-content:space-between;align-items:center}
.brand{font-weight:800;letter-spacing:.14em;font-size:26px;display:flex;align-items:center;gap:14px}
.dot{width:26px;height:26px;border-radius:50%;border:5px solid var(--flash);position:relative}
.dot:after{content:'';position:absolute;inset:4px;border-radius:50%;background:var(--flash)}
.hd{text-align:right;font-size:22px;color:var(--grey);font-weight:600;letter-spacing:.08em;line-height:1.4;text-transform:uppercase}
.hd b{color:var(--ink)}
.foot{position:absolute;z-index:2;bottom:52px;left:72px;right:72px;display:flex;justify-content:space-between;font-size:22px;color:var(--muted);font-weight:600}
.mock{position:absolute;top:640px;left:-80px;transform:rotate(-30deg);font-size:64px;font-weight:900;color:var(--wm);white-space:nowrap;letter-spacing:.1em}
.nat{display:inline-block;font-size:20px;font-weight:800;padding:4px 10px;border-radius:6px;background:var(--chip);color:var(--soft);letter-spacing:.06em}
.nat.FRA{background:var(--fr-strong);color:#fff}
.fr{color:var(--fr)}
.t{display:inline-block;border-radius:50%;margin-right:6px;border:3px solid var(--ink);background:var(--ink)}
.t.miss{background:transparent;border-color:var(--flash)}
.k{font-size:30px;color:var(--flash);font-weight:800;letter-spacing:.1em}
.h{font-weight:900;line-height:1.04;margin-top:10px}
.num{font-variant-numeric:tabular-nums}
"""
HOME = config.HOME_NAT
NAT_FR = {"NOR": "Norvège", "FRA": "France", "SWE": "Suède", "GER": "Allemagne", "ITA": "Italie", "SUI": "Suisse",
          "AUT": "Autriche", "FIN": "Finlande", "CZE": "Tchéquie", "USA": "États-Unis", "UKR": "Ukraine", "SLO": "Slovénie",
          "EST": "Estonie", "LAT": "Lettonie", "LTU": "Lituanie", "POL": "Pologne", "SVK": "Slovaquie", "BEL": "Belgique",
          "CAN": "Canada", "BUL": "Bulgarie", "KAZ": "Kazakhstan", "JPN": "Japon", "CHN": "Chine", "KOR": "Corée du Sud"}


def e(x) -> str:
    return escape(str(x if x is not None else ""))


_CAT: str | None = None  # categorie du visuel en cours (SW, SM, ou None = generique)


def set_cat(cat: str | None):
    global _CAT
    _CAT = cat if cat in ("SW", "SM") else None


def _theme_css() -> str:
    t = config.THEMES[config.THEME]
    v = dict(t["vars"])
    if config.THEME != "nuit":
        v["flash"] = config.FLASH_BY_CAT.get(_CAT, config.FLASH_BY_CAT[None])
    return ":root{" + ";".join(f"--{k}:{val}" for k, val in v.items()) + "}"


def _decor(height: int) -> str:
    """Silhouette de montagnes en bas de page (theme neige)."""
    t = config.THEMES[config.THEME]
    if not t.get("mountains"):
        return ""
    y = height - 330
    return f"""<svg style='position:absolute;left:0;top:{y}px;width:1080px;height:330px;z-index:0' viewBox='0 0 1080 330'>
<polygon points='0,150 90,95 170,130 260,60 350,115 450,45 560,120 650,80 760,135 860,55 960,110 1080,70 1080,330 0,330' fill='var(--mount3)'/>
<polygon points='0,200 110,120 200,170 320,70 420,160 530,110 640,185 770,90 880,170 990,125 1080,170 1080,330 0,330' fill='var(--mount2)'/>
<path d='M320,70 L345,94 L360,86 L378,104 L392,98 L420,160 L320,70 Z' fill='#ffffff' opacity='.9'/>
<path d='M770,90 L794,112 L808,104 L826,124 L840,118 L880,170 L770,90 Z' fill='#ffffff' opacity='.9'/>
<polygon points='0,260 140,200 250,240 380,175 510,245 640,205 760,255 900,195 1080,250 1080,330 0,330' fill='var(--mount1)'/></svg>"""


def page(body: str, h1: str, h2: str, idx: int = 0, total: int = 0, height: int = 1350) -> str:
    count = f" · {idx}/{total}" if total else ""
    story = height > 1350
    top = f"<div class='top'><div class='brand'><span class='dot'></span>TOUR DE PÉNALITÉ</div><div class='hd'><b>{e(h1)}</b><br>{e(h2)}</div></div>"
    # Stories : Instagram couvre le haut (nom du compte) et le bas (barre de reponse) :
    # pas de bandeau en haut, source remontee au-dessus de la barre.
    foot = (f"<div class='foot' style='bottom:{360 if story else 52}px'>"
            f"<span>{'' if story else '@tourdepenalite'}</span><span>Données : IBU{count}</span></div>")
    mock = "<div class='mock'>MAQUETTE · DONNÉES FICTIVES</div>" if config.WATERMARK else ""
    return f"""<html><head><meta charset='utf-8'><style>{_theme_css()}{CSS}body{{height:{height}px}}</style></head><body>{_decor(height)}
{"" if story else top}
{body}{mock}
{foot}</body></html>"""


def kicker(t, color=O):
    return f"<div class='k' style='color:{color}'>{e(t)}</div>"


def title(t, size=72):
    return f"<div class='h' style='font-size:{size}px'>{e(t)}</div>"


# Codes CIO utilises par l'IBU -> codes ISO (pour les drapeaux emoji)
IOC_ISO = {"NOR": "NO", "FRA": "FR", "SWE": "SE", "GER": "DE", "ITA": "IT", "SUI": "CH", "AUT": "AT", "FIN": "FI",
           "CZE": "CZ", "USA": "US", "UKR": "UA", "SLO": "SI", "EST": "EE", "LAT": "LV", "LTU": "LT", "POL": "PL",
           "SVK": "SK", "BEL": "BE", "CAN": "CA", "BUL": "BG", "KAZ": "KZ", "JPN": "JP", "CHN": "CN", "KOR": "KR",
           "CRO": "HR", "ROU": "RO", "MDA": "MD", "NED": "NL", "GBR": "GB", "AUS": "AU", "ESP": "ES", "DEN": "DK",
           "HUN": "HU", "SRB": "RS", "MGL": "MN", "GRE": "GR", "IRL": "IE", "ISL": "IS", "BRA": "BR", "ARG": "AR",
           "CHI": "CL", "MEX": "MX", "BIH": "BA", "MKD": "MK", "MNE": "ME", "AND": "AD", "LIE": "LI", "BLR": "BY",
           "RUS": "RU", "GEO": "GE", "ARM": "AM", "TUR": "TR", "ISR": "IL", "IND": "IN", "NZL": "NZ", "RSA": "ZA"}


def flag(n: str) -> str:
    iso = IOC_ISO.get((n or "").upper())
    if not iso:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso)


def nat(n, size=40):
    f = flag(n)
    if not f:  # pays inconnu : on garde le code
        return f"<span class='nat {e(n)}'>{e(n)}</span>"
    return f"<span class='flag' style='font-size:{size}px;line-height:1;font-family:\"Noto Color Emoji\",sans-serif' title='{e(n)}'>{f}</span>"


def shots(misses: list[int], size=20, gap=18, margin=6) -> str:
    """Nombre de fautes par tir, comme l'application IBU : une pastille par passage.
    L'API ne donne pas la cible manquee, seulement le nombre de fautes du passage."""
    d = max(24, int(size * 1.7))
    sp = max(6, min(gap, 12))
    out = []
    for m in misses:
        bg, fg = ("var(--flash)", "var(--on-flash)") if m else ("var(--ink)", "var(--bg)")
        out.append(f"<span style='display:inline-flex;align-items:center;justify-content:center;width:{d}px;height:{d}px;"
                   f"border-radius:50%;background:{bg};color:{fg};font-weight:900;font-size:{int(d * .58)}px;"
                   f"line-height:1;margin-right:{sp}px'>{m}</span>")
    return f"<span style='display:inline-flex;white-space:nowrap;align-items:center'>{''.join(out)}</span>"


def legend():
    return (f"<div style='font-size:22px;color:{MUTED};margin-top:14px;display:flex;gap:14px;align-items:center'>"
            f"{shots([0, 1], 13)}<span>nombre de fautes à chaque passage au tir</span></div>")


def _ord(meta, n):
    return ordinal_f(n) if meta.get("cat") == "SW" else ordinal(n)


def a_site(site: str) -> str:
    """'à Kontiolahti', 'au Grand-Bornand' (sans coupure dans le nom)."""
    for art, rep in (("Le ", "au "), ("La ", "à la "), ("Les ", "aux ")):
        if site.startswith(art):
            return rep + f"<span style='white-space:nowrap'>{e(site[len(art):])}</span>"
    return "à " + f"<span style='white-space:nowrap'>{e(site)}</span>"


def apres_site(site: str) -> str:
    for art in ("Le ", "La ", "Les "):
        if site.startswith(art):
            return art.lower() + site[len(art):]
    return site


def a_site_txt(site: str) -> str:
    for art, rep in (("Le ", "au "), ("La ", "à la "), ("Les ", "aux ")):
        if site.startswith(art):
            return rep + site[len(art):]
    return "à " + site


def _split_name(name: str):
    parts = name.split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", name)


# ================================================================ APRES COURSE

def results_carousel(meta: dict, rows: list[dict], headline: str, stat: dict | None) -> list[str]:
    set_cat(meta.get("cat"))
    fin = [r for r in rows if r["rank"]]
    home = [r for r in fin if r["nat"] == HOME]
    solo = home[: config.MAX_FR_SLIDES]
    rest = home[config.MAX_FR_SLIDES:]
    total = 2 + (1 if stat else 0) + len(solo) + (1 if rest else 0)
    total = min(total, config.MAX_CAROUSEL)
    h1, h2 = meta["site"], meta["label"]
    # Ordre : top 10 (avec l'accroche), stat du jour, Francais, podium en dernier.
    slides = [_top10(meta, fin, headline, h1, h2, total)]
    if stat:
        slides.append(_stat(stat, h1, h2, len(slides) + 1, total))
    room = config.MAX_CAROUSEL - 1 - (1 if rest else 0)   # place gardee pour le podium (et le tableau)
    for i, r in enumerate(solo):
        if len(slides) >= room:
            break
        slides.append(_athlete(meta, r, i + 1, len(home), h1, h2, len(slides) + 1, total))
    if rest and len(slides) < config.MAX_CAROUSEL - 1:
        slides.append(_home_table(meta, rest, h1, h2, len(slides) + 1, total))
    slides.append(_podium(meta, fin, h1, h2, len(slides) + 1, total))
    return slides


def _podium(meta, fin, h1, h2, idx, total):
    p = fin[:3]
    order = [x for x in (p[1:2] + p[0:1] + p[2:3])]
    heights = {1: 380, 2: 290, 3: 220}
    cols = ""
    for r in order:
        cls = "fr" if r["nat"] == HOME else ""
        val = fmt_time(r["time_s"]) if r["rank"] == 1 else fmt_gap(r["behind_s"])
        bg = O if r["rank"] == 1 else "var(--chip)"
        fg = "var(--on-flash)" if r["rank"] == 1 else "var(--ink)"
        cols += f"""<div style='flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end'>
<div style='font-size:28px;color:{GREY};font-weight:600'>{e(r['first'])}</div>
<div class='{cls}' style='font-size:{44 if len(r['last'])<12 else 34}px;font-weight:900;text-transform:uppercase;margin:2px 0 12px;text-align:center;line-height:1'>{e(r['last'])}</div>
{nat(r['nat'], 48)}<div class='num' style='font-size:26px;margin:14px 0 6px;font-weight:700'>{e(val)}</div>
<div style='margin-bottom:22px'>{shots(r['misses'], 20, 10)}</div>
<div style='width:100%;height:{heights.get(r['rank'],200)}px;background:{bg};border-radius:18px 18px 0 0;display:flex;justify-content:center;padding-top:24px;font-size:120px;font-weight:900;color:{fg}'>{r['rank']}</div></div>"""
    best = next((r for r in fin if r["nat"] == HOME), None)
    band = ""
    if best:
        band = f"""<div style='position:absolute;top:1135px;left:72px;right:72px;background:{FR_BG};border-radius:16px;padding:22px 28px;display:flex;justify-content:space-between;align-items:center;font-size:30px;font-weight:700'>
<span>🇫🇷&nbsp; {'Meilleure Française' if meta['cat']=='SW' else 'Meilleur Français'} : <span class='fr'>{e(best['name'])}</span></span><span class='num'>{_ord(meta, best['rank'])}{(' · ' + fmt_gap(best['behind_s'])) if best['rank']>1 else ''}</span></div>"""
    body = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LE PODIUM')}{title('Le podium', 76)}</div>
<div style='position:absolute;top:470px;left:72px;right:72px;height:640px;display:flex;gap:22px;align-items:flex-end'>{cols}</div>{band}"""
    return page(body, h1, h2, idx, total)


def _top10(meta, fin, headline, h1, h2, total):
    rows = ""
    for r in fin[:10]:
        fr = r["nat"] == HOME
        val = fmt_time(r["time_s"]) if r["rank"] == 1 else fmt_gap(r["behind_s"])
        rows += f"""<div style='display:flex;align-items:center;padding:0 24px;height:74px;border-radius:12px;margin-bottom:8px;background:{FR_BG if fr else ROW}'>
<div style='width:70px;font-size:34px;font-weight:900;color:{O if r['rank']<=3 else GREY}'>{r['rank']}</div>
<div class='{'fr' if fr else ''}' style='flex:1;font-size:32px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{e(r['name'])}</div>
<span style='margin-right:24px'>{nat(r['nat'])}</span><div style='width:{250 if len(r['misses'])<=2 else 290}px'>{shots(r['misses'], 18, 10)}</div>
<div class='num' style='width:150px;text-align:right;font-size:30px;font-weight:700'>{e(val)}</div></div>"""
    n_home = len([r for r in fin[:10] if r["nat"] == HOME])
    t = {0: "Aucun Bleu dans le top 10", 1: "1 Bleu dans le top 10"}.get(n_home, f"{n_home} Bleus dans le top 10")
    if meta["cat"] == "SW":
        t = {0: "Aucune Bleue dans le top 10", 1: "1 Bleue dans le top 10"}.get(n_home, f"{n_home} Bleues dans le top 10")
    body = f"""<div style='position:absolute;top:180px;left:72px;right:72px'>{kicker('LE TOP 10 · ' + t.replace(' dans le top 10', '').upper())}{title(headline, 58 if len(headline) < 34 else 46)}</div>
<div style='position:absolute;top:360px;left:72px;right:72px'>{rows}{legend()}</div>"""
    return page(body, h1, h2, 1, total)


def _stat(stat, h1, h2, idx, total):
    big = stat["big"]
    size = 300 if len(big) <= 3 else (200 if len(big) <= 5 else 150)
    body = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LA STAT DU JOUR')}</div>
<div style='position:absolute;top:330px;left:72px;right:72px'>
<div style='font-size:{size}px;font-weight:900;line-height:.9;color:{O};letter-spacing:-.03em'>{e(big)}</div>
<div style='font-size:68px;font-weight:900;line-height:1.05;margin-top:30px'>{e(stat['headline'])}</div>
<div style='font-size:36px;color:{GREY};margin-top:30px;line-height:1.35;font-weight:500'>{e(stat['detail'])}</div></div>"""
    return page(body, h1, h2, idx, total)


def _athlete(meta, r, i, n, h1, h2, idx, total):
    stages = config.DISCIPLINES.get(meta["disc"], {}).get("stages", [])
    bouts = ""
    for k, m in enumerate(r["misses"]):
        label = stages[k] if k < len(stages) else f"Tir {k+1}"
        bouts += f"""<div style='display:flex;justify-content:space-between;align-items:center;padding:{18 if len(r['misses'])>2 else 22}px 0;border-top:1px solid var(--line)'>
<span style='font-size:30px;font-weight:700;width:200px'>{e(label)}</span><span>{shots([m], 34 if len(r['misses']) <= 2 else 26)}</span>
<span style='font-size:30px;font-weight:800;width:90px;text-align:right;color:{O if m else 'var(--ink)'}'>{5-m}/5</span></div>"""

    def card(t, v, rk):
        col = O if rk and rk <= 3 else "var(--soft)"
        return f"""<div style='flex:1;background:{ROW};border-radius:18px;padding:28px'>
<div style='font-size:24px;color:{GREY};font-weight:700;letter-spacing:.08em'>{t}</div>
<div class='num' style='font-size:56px;font-weight:900;margin-top:8px'>{e(v)}</div>
<div style='font-size:28px;margin-top:6px;font-weight:700;color:{col}'>{ordinal(rk) if rk else '-'} temps</div></div>"""
    ski = r["ski"] or (None, None)
    rng = r["range"] or (None, None)
    sht = r["shoot"] or (None, None)
    hits = r["shots"] - (r["misses_total"] or 0)
    label = "LES BLEUES" if meta["cat"] == "SW" else "LES BLEUS"
    rank_txt = _ord(meta, r["rank"])
    num, suf = (rank_txt[:-2], rank_txt[-2:]) if rank_txt.endswith(("er", "re")) else (rank_txt[:-1], rank_txt[-1:])
    body = f"""<div style='position:absolute;top:190px;left:72px;right:72px;display:flex;justify-content:space-between;align-items:flex-end'>
<div>{kicker(f'🇫🇷 {label} · {i}/{n}', 'var(--fr)')}<div style='font-size:34px;color:{GREY};font-weight:600;margin-top:16px'>{e(r['first'])}</div>
<div style='font-size:{92 if len(r['last'])<11 else 70}px;font-weight:900;text-transform:uppercase;line-height:1'>{e(r['last'])}</div></div>
<div style='text-align:right'><div style='font-size:170px;font-weight:900;line-height:.85;color:{O}'>{num}<span style='font-size:80px'>{suf}</span></div>
<div class='num' style='font-size:32px;font-weight:700;color:{GREY};margin-top:10px'>{e(fmt_gap(r['behind_s']) if r['rank']>1 else fmt_time(r['time_s']))}</div></div></div>
<div style='position:absolute;top:520px;left:72px;right:72px;display:flex;gap:20px'>{card('SKI', fmt_time(ski[0]), ski[1])}{card('PAS DE TIR', fmt_time(rng[0]), rng[1])}</div>
<div style='position:absolute;top:790px;left:72px;right:72px'>
<div style='display:flex;justify-content:space-between;font-size:24px;color:{GREY};font-weight:700;letter-spacing:.08em;margin-bottom:10px'>
<span>TIR</span><span>Temps de tir : {e(fmt_time(sht[0]))} ({e(ordinal(sht[1]) if sht[1] else '-')})</span></div>{bouts}
<div style='display:flex;justify-content:space-between;align-items:center;padding:20px 0;border-top:1px solid var(--line)'>
<span style='font-size:30px;font-weight:700'>Total</span><span style='font-size:40px;font-weight:900'>{hits}/{r['shots']}</span></div></div>"""
    return page(body, h1, h2, idx, total)


def _home_table(meta, rest, h1, h2, idx, total):
    rows = "".join(f"""<div style='display:flex;align-items:center;padding:22px 0;border-top:1px solid var(--line);font-size:32px'>
<span style='width:110px;font-weight:900;color:{GREY}'>{_ord(meta, r['rank'])}</span><span class='fr' style='flex:1;font-weight:800'>{e(r['name'])}</span>
<span style='width:300px'>{shots(r['misses'], 16, 8)}</span><span class='num' style='width:160px;text-align:right'>{e(fmt_gap(r['behind_s']))}</span></div>""" for r in rest)
    body = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LES AUTRES BLEUS' if meta['cat']!='SW' else 'LES AUTRES BLEUES', 'var(--fr)')}{title('Le reste de l’équipe', 64)}</div>
<div style='position:absolute;top:380px;left:72px;right:72px'>{rows}</div>"""
    return page(body, h1, h2, idx, total)


def relay_image(meta: dict, teams: list[dict], headline: str) -> list[str]:
    set_cat(meta.get("cat"))  # relais mixtes (MX) : couleur generique
    fin = [t for t in teams if t["rank"]]
    rows = ""
    for t in fin[:8]:
        fr = t["nat"] == HOME
        val = fmt_time(t["time_s"]) if t["rank"] == 1 else fmt_gap(t["behind_s"])
        rows += f"""<div style='display:flex;align-items:center;padding:0 26px;height:78px;border-radius:14px;margin-bottom:9px;background:{FR_BG if fr else ('var(--lead-bg)' if t['rank']==1 else ROW)}'>
<div style='width:80px;font-size:38px;font-weight:900;color:{O if t['rank']<=3 else GREY}'>{t['rank']}</div>
<div class='{'fr' if fr else ''}' style='flex:1;font-size:34px;font-weight:800;display:flex;align-items:center;gap:18px'>{nat(t['nat'], 38)}{e(NAT_FR.get(t['nat'], t['nat']))}</div>
<div style='width:260px;font-size:24px;color:{GREY}'>{t['penalties']} tour(s) · {t['spares']} pioche(s)</div>
<div class='num' style='width:170px;text-align:right;font-size:32px;font-weight:700'>{e(val)}</div></div>"""
    home = next((t for t in fin if t["nat"] == HOME), None)
    band = f"<div style='font-size:34px;font-weight:800;margin-top:24px' class='fr'>🇫🇷 France : {ordinal_f(home['rank'])}</div>" if home else ""
    body = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('RÉSULTAT')}{title(headline, 68 if len(headline) < 34 else 56)}</div>
<div style='position:absolute;top:400px;left:72px;right:72px'>{rows}{band}</div>"""
    return [page(body, meta["site"], meta["label"])]


# ================================================================ AVANT COURSE

def pre_race(meta: dict, headline: str, lines: list[tuple[str, str]], favs: list[dict], key_point: str) -> tuple[str, str]:
    set_cat(meta.get("cat"))
    def line(k, v):
        return f"<div style='display:flex;justify-content:space-between;padding:22px 0;border-top:1px solid var(--line);font-size:32px'><span style='color:{GREY};font-weight:600'>{e(k)}</span><span style='font-weight:800'>{e(v)}</span></div>"
    fav = ""
    for i, r in enumerate(favs):
        fav += f"<div style='display:flex;align-items:center;gap:22px;padding:14px 0'><span style='font-size:44px;font-weight:900;color:{O};width:40px'>{i+1}</span><div style='flex:1'><div class='{'fr' if r['nat']==HOME else ''}' style='font-size:34px;font-weight:800'>{e(r['name'])}</div><div style='font-size:24px;color:{GREY}'>{e(r['why'])}</div></div>{nat(r['nat'])}</div>"
    hhmm = meta["start"].strftime("%H:%M") if meta["start"] else ""
    feed = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker(f"AUJOURD'HUI · {hhmm}")}{title(meta['label'], 72 if len(meta['label'])<26 else 58)}</div>
<div style='position:absolute;top:400px;left:72px;right:72px'>{''.join(line(k, v) for k, v in lines)}
<div style='margin-top:36px'>{kicker('NOS FAVORIS' if meta['cat']!='SW' else 'NOS FAVORITES')}{fav}</div>
<div style='font-size:22px;color:{MUTED};margin-top:6px'>Calcul : résultats et tir sur les dernières courses</div></div>"""
    # Story : pas de faux sondage (l'API ne permet pas les stickers interactifs) ;
    # favoris et infos cles, puis invitation a repondre a la story (message prive).
    fav_rows = "".join(
        f"<div style='display:flex;align-items:center;gap:22px;padding:20px 0;border-top:1px solid var(--line)'>"
        f"<span style='font-size:52px;font-weight:900;color:{O};width:46px'>{i+1}</span>{nat(r['nat'], 46)}"
        f"<div style='flex:1'><div class='{'fr' if r['nat']==HOME else ''}' style='font-size:42px;font-weight:900'>{e(r['name'])}</div>"
        f"<div style='font-size:26px;color:{GREY};margin-top:4px'>{e(r['why'])}</div></div></div>" for i, r in enumerate(favs[:3]))
    meteo = next((v for k, v in lines if k == "Météo"), None)
    meteo_html = f"<div style='font-size:34px;font-weight:700;color:var(--soft);margin-top:22px'>{e(meteo)}</div>" if meteo else ""
    story = f"""<div style='position:absolute;top:250px;left:72px;right:72px'>{kicker('DANS 2 HEURES')}
<div style='font-size:96px;font-weight:900;line-height:1;margin-top:20px'>{e(meta['label'])}</div>
<div style='font-size:44px;color:{GREY};font-weight:700;margin-top:20px'>{hhmm} · {e(meta['site'])}</div>{meteo_html}</div>
<div style='position:absolute;top:760px;left:72px;right:72px;background:var(--row);border-radius:28px;padding:36px 40px 20px'>
<div style='font-size:30px;color:{O};font-weight:800;letter-spacing:.08em;margin-bottom:6px'>{'NOS FAVORITES' if meta['cat']=='SW' else 'NOS FAVORIS'}</div>{fav_rows}</div>
<div style='position:absolute;top:1320px;left:72px;right:72px;font-size:34px;font-weight:700;color:var(--soft);line-height:1.4'>{e(key_point)}</div>
<div style='position:absolute;top:1460px;left:72px;right:72px;text-align:center;font-size:40px;font-weight:900;color:var(--ink)'>
Ton pronostic ? Réponds à cette story 💬</div>"""
    return page(feed, meta["site"], meta["label"]), page(story, meta["site"], "Story avant course", height=1920)


# ================================================================ MERCREDI

def programme(site: str, days: list[tuple[str, list[tuple[str, str]]]], n_races: int, n_days: int, enjeux: dict) -> list[str]:
    set_cat(None)
    rows = ""
    for day, races in days:
        items = "".join(f"<div style='display:flex;gap:26px;font-size:{32 if len(days)<=4 else 28}px;font-weight:600;padding:5px 0'><span class='num' style='width:110px;color:{O};font-weight:800'>{e(h)}</span><span>{e(r)}</span></div>" for h, r in races)
        rows += f"<div style='padding:{20 if len(days)<=4 else 12}px 0;border-top:1px solid var(--line)'><div style='font-size:24px;color:{GREY};font-weight:800;letter-spacing:.1em;margin-bottom:6px'>{e(day.upper())}</div>{items}</div>"
    site_nb = a_site(site)
    total = 2 if enjeux else 1
    s1 = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LE PROGRAMME')}<div class='h' style='font-size:70px'>{n_races} courses, {n_days} jours {site_nb}</div></div>
<div style='position:absolute;top:500px;left:72px;right:72px'>{rows}<div style='font-size:24px;color:{MUTED};margin-top:16px'>Heures françaises</div></div>"""
    slides = [page(s1, site, "Étape de Coupe du monde", 1, total)]
    if enjeux:
        # enjeux : {"SM": [(cle, nom, nat, detail), ...], "SW": [...]} -> deux colonnes Hommes / Femmes
        cols = ""
        for cat in ("SM", "SW"):
            items = enjeux.get(cat) or []
            if not items:
                continue
            col = config.FLASH_BY_CAT.get(cat, "var(--flash)") if config.THEME != "nuit" else "var(--flash)"
            cards = "".join(
                f"<div style='background:{FR_BG if n == HOME else ROW};border-radius:18px;padding:22px 24px;margin-bottom:14px;min-height:190px'>"
                f"<div style='font-size:21px;color:{col};font-weight:800;letter-spacing:.08em'>{e(k)}</div>"
                f"<div style='display:flex;align-items:center;gap:12px;margin-top:12px'>{nat(n, 34)}"
                f"<div class='{'fr' if n == HOME else ''}' style='font-size:36px;font-weight:900;line-height:1.05'>{e(v)}</div></div>"
                f"<div style='font-size:24px;color:var(--soft);margin-top:12px;line-height:1.3'>{e(sub)}</div></div>"
                for k, v, n, sub in items[:3])
            cols += (f"<div style='flex:1;min-width:0'><div style='font-size:30px;font-weight:900;color:{col};margin-bottom:14px'>"
                     f"{'Femmes' if cat == 'SW' else 'Hommes'}</div>{cards}</div>")
        s2 = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LES ENJEUX')}<div class='h' style='font-size:58px;white-space:nowrap'>Ce qu'il faut suivre ce week-end</div></div>
<div style='position:absolute;top:350px;left:72px;right:72px;display:flex;gap:22px'>{cols}</div>"""
        slides.append(page(s2, site, "Étape de Coupe du monde", 2, total))
    return slides


def standings_slide(label: str, rows: list[dict], headline: str, h2: str, idx: int, total: int, note: str = "", young: bool = False, cat: str | None = None) -> str:
    set_cat(cat)
    out = ""
    lead = rows[0]["score"] if rows else 0
    for r in rows[:10]:
        fr = r["nat"] == HOME
        gap = "" if r is rows[0] else ("=" if lead == r["score"] else f"-{lead - r['score']}")
        rank = r.get("young_rank", r["rank"])
        extra = f"<span style='font-size:22px;color:{MUTED};margin-left:10px'>({r['rank']}e)</span>" if young else ""
        out += f"""<div style='display:flex;align-items:center;padding:0 24px;height:66px;border-radius:12px;margin-bottom:7px;background:{FR_BG if fr else ('var(--lead-bg)' if rank==1 else ROW)}'>
<div style='width:66px;font-size:32px;font-weight:900;color:{O if rank<=3 else GREY}'>{rank}</div>
<div class='{'fr' if fr else ''}' style='flex:1;font-size:31px;font-weight:700;white-space:nowrap'>{e(r['name'])}{extra}</div>
{nat(r['nat'])}<div class='num' style='width:110px;text-align:right;font-size:30px;font-weight:800'>{r['score']}</div>
<div class='num' style='width:110px;text-align:right;font-size:24px;color:{MUTED}'>{gap}</div></div>"""
    body = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker(label)}{title(headline, 60)}</div>
<div style='position:absolute;top:400px;left:72px;right:72px'>
<div style='display:flex;justify-content:flex-end;padding:0 24px 10px;font-size:20px;color:{MUTED};font-weight:700;letter-spacing:.08em'><span style='width:110px;text-align:right'>PTS</span><span style='width:110px;text-align:right'>ÉCART</span></div>{out}
<div style='font-size:24px;color:{MUTED};margin-top:12px'>{e(note)}</div></div>"""
    return page(body, "Classement général", h2, idx, total)


# ================================================================ LUNDI

def bilan(site: str, headline: str, figures: list[tuple[str, str]], mv: dict[str, dict], pen: dict | None = None) -> list[str]:
    set_cat(None)
    total = 1 + len(mv) + (2 if pen and pen["week"]["nations"] else 0)
    grid = "".join(f"<div style='background:{ROW};border-radius:18px;padding:30px'><div style='font-size:84px;font-weight:900;color:{O}'>{e(v)}</div><div style='font-size:28px;color:var(--soft);font-weight:600'>{e(k)}</div></div>" for v, k in figures[:4])
    s1 = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LE BILAN')}{title(headline, 80 if len(headline)<34 else 64)}</div>
<div style='position:absolute;top:540px;left:72px;right:72px;display:grid;grid-template-columns:1fr 1fr;gap:20px'>{grid}</div>"""
    slides = [page(s1, site, "Bilan de l'étape", 1, total)]
    for i, (cat, m) in enumerate(mv.items()):
        set_cat(cat)
        def row(d, up):
            fr = d["nat"] == HOME
            arrow = f"<span style='color:{'var(--up)' if up else O};font-weight:900'>{'▲' if up else '▼'} {abs(d['delta'])}</span>"
            o = ordinal_f if cat == "SW" else ordinal
            return f"""<div style='display:flex;align-items:center;padding:0 26px;height:94px;border-radius:14px;margin-bottom:10px;background:{FR_BG if fr else ROW}'>
<div style='width:120px;font-size:36px'>{arrow}</div><div class='{'fr' if fr else ''}' style='flex:1;font-size:33px;font-weight:700'>{e(d['name'])}</div>{nat(d['nat'])}
<div style='width:210px;text-align:right;font-size:28px;color:{GREY};font-weight:700'>{o(d['before'])} → <span style='color:var(--ink)'>{o(d['after'])}</span></div></div>"""
        ups = "".join(row(d, True) for d in m["up"])
        downs = "".join(row(d, False) for d in m["down"])
        s = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('QUI MONTE, QUI DESCEND')}<div class='h' style='font-size:58px'>Le général {config.CATEGORIES[cat]} après <span style='white-space:nowrap'>{e(apres_site(site))}</span></div></div>
<div style='position:absolute;top:410px;left:72px;right:72px'>
<div style='font-size:24px;color:var(--up);font-weight:800;letter-spacing:.08em;margin-bottom:12px'>EN HAUSSE</div>{ups or "<div style='color:var(--muted);font-size:28px'>Aucune progression dans le top 30</div>"}
<div style='font-size:24px;color:{O};font-weight:800;letter-spacing:.08em;margin:26px 0 12px'>EN BAISSE</div>{downs or "<div style='color:var(--muted);font-size:28px'>Aucune baisse dans le top 30</div>"}</div>"""
        slides.append(page(s, "Classement général", config.CATEGORIES[cat], i + 2, total))
    if pen and pen["week"]["nations"]:
        slides += _penalty_slides(site, pen, len(slides), total)
    return slides


# ================================================================ MARDI

DISC_SHORT = {"SP": "SP", "PU": "PO", "MS": "MS", "IN": "IN", "SI": "IC"}


def bleus(cat: str, site: str, athletes: list[dict]) -> list[str]:
    set_cat(cat)
    fem = cat == "SW"
    o = ordinal_f if fem else ordinal
    label = "🇫🇷 LES BLEUES · FEMMES" if fem else "🇫🇷 LES BLEUS · HOMMES"
    n = min(len(athletes), config.MAX_CAROUSEL - 1)
    total = 1 + n
    rows = ""
    for a in athletes:
        wk = " · ".join(f"{DISC_SHORT.get(d, d)} {o(r) if r else 'Ab.'}" for d, r in a["week_by_disc"]) or "-"
        gen = f"{o(a['gen_rank'])} ({a['score']} pts)" if a.get("gen_rank") else "-"
        tir = f"{a['week']['tir']} %" if a["week"]["tir"] is not None else "-"
        rows += f"<div style='display:flex;align-items:center;padding:20px 0;border-top:1px solid var(--line);font-size:28px'><span class='fr' style='flex:1;font-weight:800'>{e(a['name'])}</span><span style='width:330px;color:var(--soft);font-weight:600;font-size:24px'>{e(wk)}</span><span class='num' style='width:200px;text-align:right;font-weight:700'>{e(gen)}</span><span class='num' style='width:100px;text-align:right;font-weight:800;color:{O}'>{e(tir)}</span></div>"
    s1 = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker(label, 'var(--fr)')}{title('Le week-end des Françaises' if fem else 'Le week-end des Français', 70)}</div>
<div style='position:absolute;top:400px;left:72px;right:72px'>
<div style='display:flex;font-size:20px;color:{MUTED};font-weight:800;letter-spacing:.08em;padding-bottom:12px'><span style='flex:1'>ATHLÈTE</span><span style='width:330px'>COURSES</span><span style='width:200px;text-align:right'>GÉNÉRAL</span><span style='width:100px;text-align:right'>TIR</span></div>{rows}
<div style='font-size:22px;color:{MUTED};margin-top:14px'>SP sprint · PO poursuite · MS mass start · IN individuel · Tir : réussite du week-end</div></div>"""
    slides = [page(s1, "Les Bleus" if not fem else "Les Bleues", f"Après {apres_site(site)}", 1, total)]
    for i, a in enumerate(athletes[:n]):
        def stat(k, wk, ss):
            return f"<div style='display:flex;align-items:center;padding:22px 0;border-top:1px solid var(--line)'><span style='flex:1;font-size:30px;color:{GREY};font-weight:700'>{e(k)}</span><span class='num' style='width:220px;text-align:right;font-size:38px;font-weight:900'>{e(wk)}</span><span class='num' style='width:220px;text-align:right;font-size:32px;font-weight:700;color:var(--soft)'>{e(ss)}</span></div>"
        w, s = a["week"], a["season"]
        pct = lambda v: f"{v} %" if v is not None else "-"
        form = ""
        for p in a["form"]:
            h = 40 + max(0, 160 - 4 * (p or 40)) if p else 30
            form += f"<div style='flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:10px'><div style='width:64px;height:{h}px;background:{O if p and p<=3 else 'var(--bar)'};border-radius:10px 10px 0 0'></div><span style='font-size:24px;font-weight:800'>{o(p) if p else 'Ab.'}</span></div>"
        gr = o(a["gen_rank"]) if a.get("gen_rank") else "-"
        num, suf = (gr[:-2], gr[-2:]) if gr.endswith(("er", "re")) else (gr[:-1], gr[-1:])
        body = f"""<div style='position:absolute;top:190px;left:72px;right:72px;display:flex;justify-content:space-between;align-items:flex-end'>
<div>{kicker(f"{label.split(' ·')[0]} · {i+1}/{n}", 'var(--fr)')}<div style='font-size:34px;color:{GREY};font-weight:600;margin-top:16px'>{e(a['first'])}</div><div style='font-size:{92 if len(a['last'])<11 else 70}px;font-weight:900;line-height:1;text-transform:uppercase'>{e(a['last'])}</div></div>
<div style='text-align:right'><div style='font-size:24px;color:{GREY};font-weight:800;letter-spacing:.08em'>GÉNÉRAL</div><div style='font-size:120px;font-weight:900;color:{O};line-height:.9'>{num}<span style='font-size:60px'>{suf}</span></div></div></div>
<div style='position:absolute;top:470px;left:72px;right:72px'>
<div style='display:flex;font-size:20px;color:{MUTED};font-weight:800;letter-spacing:.08em;padding-bottom:10px'><span style='flex:1'></span><span style='width:220px;text-align:right'>WEEK-END</span><span style='width:220px;text-align:right'>SAISON</span></div>
{stat('Meilleur résultat', o(w['best']), o(s['best']))}{stat('Tir', pct(w['tir']), pct(s['tir']))}{stat('Rang ski moyen', o(w['ski']), o(s['ski']))}{stat('Courses', str(w['n']), str(s['n']))}</div>
<div style='position:absolute;top:960px;left:72px;right:72px'><div style='font-size:24px;color:{GREY};font-weight:800;letter-spacing:.08em;margin-bottom:16px'>FORME · {len(a['form'])} DERNIÈRES COURSES</div>
<div style='display:flex;height:240px;gap:10px'>{form}</div></div>"""
        slides.append(page(body, "Les Bleus" if not fem else "Les Bleues", f"Après {apres_site(site)}", i + 2, total))
    return slides


# ================================================================ STORIES (1080x1920)
# Zone sure : Instagram couvre environ 250 px en haut et 320 px en bas.

def story_depart(meta: dict, favs: list[dict]) -> str:
    set_cat(meta.get("cat"))
    hhmm = meta["start"].strftime("%H:%M") if meta["start"] else ""
    fav = ""
    if favs:
        names = "".join(f"<div style='display:flex;align-items:center;gap:16px;font-size:38px;font-weight:800;margin-top:14px'>"
                        f"{nat(r['nat'], 40)}<span class='{'fr' if r['nat'] == HOME else ''}'>{e(r['name'])}</span></div>" for r in favs[:3])
        fav = (f"<div style='position:absolute;top:1080px;left:72px;right:72px;background:var(--row);border-radius:28px;padding:34px 40px'>"
               f"<div style='font-size:28px;color:{O};font-weight:800;letter-spacing:.08em'>À SURVEILLER</div>{names}</div>")
    body = f"""<div style='position:absolute;top:330px;left:72px;right:72px'>{kicker(f'{hhmm} · EN DIRECT')}
<div style='font-size:150px;font-weight:900;line-height:.95;margin-top:26px;color:{O}'>C'est<br>parti !</div>
<div style='font-size:62px;font-weight:900;line-height:1.05;margin-top:40px'>{e(meta['label'])}</div>
<div style='font-size:40px;color:{GREY};font-weight:700;margin-top:16px'>{e(meta['site'])}</div></div>{fav}
<div style='position:absolute;top:1480px;left:72px;right:72px;text-align:center;font-size:36px;font-weight:800;color:var(--soft)'>
Résultats et stats juste après l'arrivée 🎯</div>"""
    return page(body, meta["site"], "Départ", height=1920)


def story_programme(site: str, days: list[tuple[str, list[tuple[str, str]]]]) -> str:
    set_cat(None)
    rows = ""
    for day, races in days:
        items = "".join(f"<div style='display:flex;gap:24px;font-size:34px;font-weight:600;padding:6px 0'>"
                        f"<span class='num' style='width:110px;color:{O};font-weight:800'>{e(h)}</span><span>{e(r)}</span></div>" for h, r in races)
        rows += (f"<div style='padding:18px 0;border-top:1px solid var(--line)'><div style='font-size:26px;color:{GREY};"
                 f"font-weight:800;letter-spacing:.1em;margin-bottom:6px'>{e(day.upper())}</div>{items}</div>")
    body = f"""<div style='position:absolute;top:290px;left:72px;right:72px'>{kicker('LE PROGRAMME')}
<div class='h' style='font-size:84px'>Ce week-end<br>{a_site(site)}</div></div>
<div style='position:absolute;top:640px;left:72px;right:72px'>{rows}
<div style='font-size:26px;color:{MUTED};margin-top:16px'>Heures françaises</div></div>"""
    return page(body, site, "Programme", height=1920)


def story_bleus(meta: dict, home: list[dict]) -> str:
    set_cat(meta.get("cat"))
    fem = meta.get("cat") == "SW"
    o = ordinal_f if fem else ordinal
    b = home[0]
    ski = b["ski"] or (None, None)
    hits = b["shots"] - (b["misses_total"] or 0)
    rank_txt = o(b["rank"])
    num, suf = (rank_txt[:-2], rank_txt[-2:]) if rank_txt.endswith(("er", "re")) else (rank_txt[:-1], rank_txt[-1:])

    def stat(k, v):
        return (f"<div style='flex:1;background:var(--chip);border-radius:18px;padding:20px 22px'>"
                f"<div style='font-size:22px;color:{GREY};font-weight:800;letter-spacing:.08em'>{k}</div>"
                f"<div class='num' style='font-size:40px;font-weight:900;margin-top:6px'>{e(v)}</div></div>")
    others = "".join(
        f"<div style='display:flex;align-items:center;padding:16px 0;border-top:1px solid var(--line);font-size:32px'>"
        f"<span style='width:100px;font-weight:900;color:{GREY}'>{o(r['rank'])}</span>"
        f"<span class='fr' style='flex:1;font-weight:800'>{e(r['name'])}</span>"
        f"<span style='margin-right:18px'>{shots(r['misses'], 15, 6)}</span>"
        f"<span class='num' style='width:150px;text-align:right;font-size:28px;color:var(--soft)'>{e(fmt_gap(r['behind_s']))}</span></div>"
        for r in home[1:8])
    body = f"""<div style='position:absolute;top:270px;left:72px;right:72px'>{kicker('🇫🇷 LES BLEUES' if fem else '🇫🇷 LES BLEUS', 'var(--fr)')}
<div style='font-size:40px;font-weight:800;margin-top:10px;color:var(--soft)'>{e(meta['label'])} · {e(meta['site'])}</div></div>
<div style='position:absolute;top:420px;left:72px;right:72px;background:var(--fr-bg);border-radius:28px;padding:34px 38px'>
<div style='display:flex;justify-content:space-between;align-items:flex-end'>
<div><div style='font-size:26px;color:var(--fr);font-weight:800;letter-spacing:.08em'>{'MEILLEURE FRANÇAISE' if fem else 'MEILLEUR FRANÇAIS'}</div>
<div style='font-size:34px;color:{GREY};font-weight:600;margin-top:12px'>{e(b['first'])}</div>
<div style='font-size:{78 if len(b['last']) < 11 else 60}px;font-weight:900;line-height:1;text-transform:uppercase'>{e(b['last'])}</div></div>
<div style='text-align:right'><div style='font-size:150px;font-weight:900;line-height:.85;color:{O}'>{num}<span style='font-size:70px'>{suf}</span></div>
<div class='num' style='font-size:30px;font-weight:700;color:{GREY};margin-top:8px'>{e(fmt_gap(b['behind_s']) if b['rank'] > 1 else fmt_time(b['time_s']))}</div></div></div>
<div style='display:flex;gap:14px;margin-top:28px'>{stat('SKI', (ordinal(ski[1]) + ' temps') if ski[1] else '-')}{stat('TIR', f'{hits}/{b["shots"]}')}</div>
<div style='margin-top:22px'>{shots(b['misses'], 26, 10)}</div></div>
<div style='position:absolute;top:1010px;left:72px;right:72px'>
{"<div style='font-size:26px;color:" + GREY + ";font-weight:800;letter-spacing:.08em;margin-bottom:8px'>" + ('LES AUTRES BLEUES' if fem else 'LES AUTRES BLEUS') + "</div>" if len(home) > 1 else ""}{others}</div>"""
    return page(body, meta["site"], "Les Bleues" if fem else "Les Bleus", height=1920)


def story_grille(meta: dict, rows: list[dict], mode: str) -> str:
    """Grille de depart 1 h avant. mode : 'heure' (sprint, individuel), 'retard' (poursuite),
    'ordre' (mass start). rows : athletes retenus, avec leurs etiquettes ('tags')."""
    set_cat(meta.get("cat"))
    fem = meta.get("cat") == "SW"
    hhmm = meta["start"].strftime("%H:%M") if meta["start"] else ""
    head = {"heure": "DÉPART", "retard": "RETARD", "ordre": "DOSSARD"}[mode]
    lines = ""
    for r in rows[:14]:
        if mode == "heure":
            val = r["start"].strftime("%H:%M:%S") if r["start"] else "-"
        elif mode == "retard":
            val = "En tête" if not r["gap_s"] else fmt_gap(r["gap_s"])
        else:
            val = str(r["bib"] or "-")
        tags = "".join(f"<span style='font-size:20px;font-weight:800;padding:4px 10px;border-radius:8px;margin-left:10px;"
                       f"background:{O};color:var(--on-flash)'>{e(t)}</span>" for t in r.get("tags", []))
        fr = r["nat"] == HOME
        lines += (f"<div style='display:flex;align-items:center;padding:14px 18px;border-radius:14px;margin-bottom:8px;"
                  f"background:{FR_BG if fr else ROW}'>"
                  f"<span class='num' style='width:92px;font-size:30px;font-weight:900;color:{GREY}'>{r['order'] or '-'}</span>"
                  f"{nat(r['nat'], 34)}<span class='{'fr' if fr else ''}' style='flex:1;margin-left:14px;font-size:31px;font-weight:800;"
                  f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{e(r['name'])}{tags}</span>"
                  f"<span class='num' style='width:170px;text-align:right;font-size:30px;font-weight:800'>{e(val)}</span></div>")
    body = f"""<div style='position:absolute;top:250px;left:72px;right:72px'>{kicker('DANS 1 HEURE · LA GRILLE')}
<div class='h' style='font-size:70px'>{e(meta['label'])}</div>
<div style='font-size:36px;color:{GREY};font-weight:700;margin-top:12px'>{hhmm} · {e(meta['site'])}</div></div>
<div style='position:absolute;top:560px;left:72px;right:72px'>
<div style='display:flex;padding:0 18px 10px;font-size:20px;color:{MUTED};font-weight:800;letter-spacing:.08em'>
<span style='width:92px'>ORDRE</span><span style='flex:1'>{'ATHLÈTE' if not fem else 'ATHLÈTE'}</span><span style='width:170px;text-align:right'>{head}</span></div>{lines}
<div style='font-size:22px;color:{MUTED};margin-top:10px'>Top 3 du général, {'meilleure jeune' if fem else 'meilleur jeune'} et {'toutes les Françaises' if fem else 'tous les Français'}</div></div>"""
    return page(body, meta["site"], "Grille de départ", height=1920)


def story_relais(meta: dict, teams: list[dict]) -> str:
    set_cat(meta.get("cat"))
    hhmm = meta["start"].strftime("%H:%M") if meta["start"] else ""
    blocks = ""
    for t in teams[:3]:
        fr = t["nat"] == HOME
        legs = "".join(f"<div style='display:flex;gap:18px;font-size:30px;font-weight:700;padding:6px 0'>"
                       f"<span style='width:40px;color:{GREY};font-weight:900'>{i + 1}</span><span>{e(n)}</span></div>"
                       for i, n in enumerate(t["legs"]))
        blocks += (f"<div style='background:{FR_BG if fr else ROW};border-radius:24px;padding:26px 32px;margin-bottom:18px'>"
                   f"<div style='display:flex;align-items:center;gap:16px;margin-bottom:8px'>{nat(t['nat'], 44)}"
                   f"<span class='{'fr' if fr else ''}' style='font-size:40px;font-weight:900'>{e(NAT_FR.get(t['nat'], t['nat']))}</span>"
                   f"<span style='margin-left:auto;font-size:24px;color:{GREY};font-weight:800'>DOSSARD {t['bib'] or '-'}</span></div>"
                   f"{legs or '<div style=\'font-size:26px;color:var(--muted)\'>Composition pas encore publiée</div>'}</div>")
    body = f"""<div style='position:absolute;top:250px;left:72px;right:72px'>{kicker('DANS 1 HEURE · LES ÉQUIPES')}
<div class='h' style='font-size:70px'>{e(meta['label'])}</div>
<div style='font-size:36px;color:{GREY};font-weight:700;margin-top:12px'>{hhmm} · {e(meta['site'])}</div></div>
<div style='position:absolute;top:540px;left:72px;right:72px'>{blocks}</div>"""
    return page(body, meta["site"], "Composition des relais", height=1920)


def story_sans_faute(meta: dict, clean: list[dict], best_shooters: list[dict]) -> str:
    """Le club des sans-faute : tous les athletes a 0 faute (12 affiches au plus)."""
    set_cat(meta.get("cat"))
    fem = meta.get("cat") == "SW"
    o = ordinal_f if fem else ordinal
    n = len(clean)
    show = clean[:11]
    rows = "".join(
        f"<div style='display:flex;align-items:center;padding:14px 18px;border-radius:14px;margin-bottom:8px;"
        f"background:{FR_BG if r['nat'] == HOME else ROW}'>{nat(r['nat'], 34)}"
        f"<span class='{'fr' if r['nat'] == HOME else ''}' style='flex:1;margin-left:16px;font-size:32px;font-weight:800'>{e(r['name'])}</span>"
        f"<span class='num' style='font-size:30px;font-weight:800;color:var(--soft)'>{o(r['rank'])}</span></div>" for r in show)
    more = (f"<div style='font-size:28px;color:{GREY};margin-top:10px;font-weight:700'>et {n - 11} autre{'s' if n - 11 > 1 else ''}</div>"
            if n > 11 else "")
    if n:
        big, title_txt = str(n), "sans-faute"
        sub = f"{show[0]['shots']}/{show[0]['shots']} au tir"
    else:
        big, title_txt, sub = "0", "sans-faute aujourd'hui", "Les meilleurs tireurs du jour"
        rows = "".join(
            f"<div style='display:flex;align-items:center;padding:14px 18px;border-radius:14px;margin-bottom:8px;background:{ROW}'>"
            f"{nat(r['nat'], 34)}<span style='flex:1;margin-left:16px;font-size:32px;font-weight:800'>{e(r['name'])}</span>"
            f"<span class='num' style='font-size:30px;font-weight:800'>{r['shots'] - (r['misses_total'] or 0)}/{r['shots']}</span></div>"
            for r in best_shooters[:5])
    body = f"""<div style='position:absolute;top:250px;left:72px;right:72px'>{kicker('LE CLUB DES SANS-FAUTE')}
<div style='display:flex;align-items:baseline;gap:22px;margin-top:10px'><span style='font-size:190px;font-weight:900;line-height:.9;color:{O}'>{big}</span>
<span style='font-size:58px;font-weight:900;line-height:1'>{e(title_txt)}</span></div>
<div style='font-size:34px;color:{GREY};font-weight:700;margin-top:14px'>{e(meta['label'])} · {e(sub)}</div></div>
<div style='position:absolute;top:640px;left:72px;right:72px'>{rows}{more}</div>"""
    return page(body, meta["site"], "Sans-faute", height=1920)


def _fmt_pen(tours: int, minutes: float) -> str:
    parts = []
    if tours:
        parts.append(f"{tours} tour{'s' if tours > 1 else ''}")
    if minutes:
        m = round(minutes, 2)
        parts.append(f"{m:g} min".replace(".", ","))
    return " + ".join(parts) or "0"


def _penalty_slides(site: str, pen: dict, done: int, total: int) -> list[str]:
    """Compteur de tours de penalite : par nation, puis par athlete (semaine + saison)."""
    set_cat(None)
    week, season = pen["week"], pen["season"]
    s_nat = {n["nat"]: n for n in season["nations"]}
    s_ath = {a["ibu"]: a for a in season["athletes"]}
    nations = week["nations"][:8]
    if not any(n["nat"] == HOME for n in nations):
        nations += [n for n in week["nations"] if n["nat"] == HOME]
    has_min = any(n["minutes"] for n in week["nations"])

    def moy(v):
        return f"{v:.1f}".replace(".", ",") if v is not None else "-"

    def row(flag_code, label, wk, ss, av, fr):
        return (f"<div style='display:flex;align-items:center;padding:0 22px;height:76px;border-radius:12px;margin-bottom:8px;"
                f"background:{FR_BG if fr else ROW}'>{nat(flag_code, 34)}"
                f"<span class='{'fr' if fr else ''}' style='flex:1;margin-left:16px;font-size:30px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{e(label)}</span>"
                f"<span class='num' style='width:200px;text-align:right;font-size:27px;font-weight:900;color:{O}'>{e(wk)}</span>"
                f"<span class='num' style='width:170px;text-align:right;font-size:24px;font-weight:700;color:var(--soft)'>{e(ss)}</span>"
                f"<span class='num' style='width:130px;text-align:right;font-size:27px;font-weight:900'>{e(av)}</span></div>")

    def head(avg_label):
        return (f"<div style='display:flex;justify-content:flex-end;align-items:flex-end;padding:0 22px 10px;font-size:19px;color:{MUTED};font-weight:800;letter-spacing:.06em;line-height:1.15'>"
                f"<span style='width:200px;text-align:right'>CE WEEK-END</span><span style='width:170px;text-align:right'>SAISON</span>"
                f"<span style='width:130px;text-align:right'>{avg_label}</span></div>")
    note = ("<div style='font-size:21px;color:" + MUTED + ";margin-top:8px;line-height:1.3'>Moyenne de la saison en fautes, courses individuelles"
            + (". En individuel, pas de tour : chaque faute ajoute du temps." if has_min else ".") + "</div>")
    rows = "".join(row(n["nat"], NAT_FR.get(n["nat"], n["nat"]), _fmt_pen(n["tours"], n["minutes"]),
                       _fmt_pen(s_nat.get(n["nat"], n)["tours"], s_nat.get(n["nat"], n)["minutes"]),
                       moy(s_nat.get(n["nat"], n)["moy"]), n["nat"] == HOME) for n in nations)
    s1 = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LE COMPTEUR DE TOURS DE PÉNALITÉ')}{title('Par nation', 66)}</div>
<div style='position:absolute;top:360px;left:72px;right:72px'>{head('MOY. / ATHLÈTE')}{rows}{note}</div>"""
    ath = week["athletes"][:7]
    home = [a for a in week["athletes"] if a["nat"] == HOME and a not in ath][:2]
    rows2 = "".join(row(a["nat"], a["name"], _fmt_pen(a["tours"], a["minutes"]),
                        _fmt_pen(s_ath.get(a["ibu"], a)["tours"], s_ath.get(a["ibu"], a)["minutes"]),
                        moy(s_ath.get(a["ibu"], a)["moy"]), a["nat"] == HOME) for a in ath + home)
    s2 = f"""<div style='position:absolute;top:190px;left:72px;right:72px'>{kicker('LE COMPTEUR DE TOURS DE PÉNALITÉ')}{title('Les plus pénalisés', 66)}</div>
<div style='position:absolute;top:360px;left:72px;right:72px'>{head('MOY. / COURSE')}{rows2}{note}</div>"""
    return [page(s1, site, "Bilan de l'étape", done + 1, total), page(s2, site, "Bilan de l'étape", done + 2, total)]


def duel(cat: str, site: str, d: dict, idx: int, total: int) -> str:
    """Duel du mardi : une slide par categorie, valeur la meilleure en couleur flash."""
    set_cat(cat)
    fem = cat == "SW"
    o = ordinal_f if fem else ordinal
    a, b = d["a"], d["b"]

    def head(x, align):
        size = 64 if len(x["last"]) < 10 else 50
        return (f"<div style='flex:1;text-align:{align}'>{nat(x['nat'], 54)}"
                f"<div style='font-size:30px;color:{GREY};font-weight:600;margin-top:14px'>{e(x['first'])}</div>"
                f"<div class='{'fr' if x['nat'] == HOME else ''}' style='font-size:{size}px;font-weight:900;line-height:1;text-transform:uppercase'>{e(x['last'])}</div></div>")

    def row(label, va, vb, fa, fb, better):
        ca = cb = "var(--ink)"
        if va is not None and vb is not None and va != vb:
            win_a = (va > vb) if better == "high" else (va < vb)
            ca, cb = (O, "var(--soft)") if win_a else ("var(--soft)", O)
        sa = fa(va) if va is not None else "-"
        sb = fb(vb) if vb is not None else "-"
        return (f"<div style='display:flex;align-items:center;padding:13px 0;border-top:1px solid var(--line)'>"
                f"<span class='num' style='width:260px;font-size:42px;font-weight:900;color:{ca}'>{e(sa)}</span>"
                f"<span style='flex:1;text-align:center;font-size:24px;color:{GREY};font-weight:800;letter-spacing:.08em'>{e(label.upper())}</span>"
                f"<span class='num' style='width:260px;text-align:right;font-size:42px;font-weight:900;color:{cb}'>{e(sb)}</span></div>")

    pts = lambda v: f"{v} pts"
    pct = lambda v: f"{v} %"
    rows = (row("Points", a["score"], b["score"], pts, pts, "high")
            + row("Victoires", a["wins"], b["wins"], str, str, "high")
            + row("Podiums", a["podiums"], b["podiums"], str, str, "high")
            + row("Top 10", a["top10"], b["top10"], str, str, "high")
            + row("Tir", a["tir"], b["tir"], pct, pct, "high")
            + row("Rang ski moyen", a["ski"], b["ski"], o, o, "low"))
    who = "La leader" if fem else "Le leader"
    sub = f"{who} contre {'la meilleure Française' if fem else 'le meilleur Français'}" if d["rule"] == "fr" else "1er contre 2e du général" if not fem else "1re contre 2e du général"
    h0, h1 = d["h2h"]
    body = f"""<div style='position:absolute;top:180px;left:72px;right:72px'>{kicker(('LE DUEL · FEMMES' if fem else 'LE DUEL · HOMMES'))}
<div style='font-size:30px;color:var(--soft);font-weight:700;margin-top:10px'>{e(sub)}</div></div>
<div style='position:absolute;top:320px;left:72px;right:72px;display:flex;align-items:flex-end;gap:20px'>{head(a, 'left')}
<div style='font-size:52px;font-weight:900;color:{O};padding-bottom:6px'>VS</div>{head(b, 'right')}</div>
<div style='position:absolute;top:560px;left:72px;right:72px'>{rows}</div>
<div style='position:absolute;top:1100px;left:72px;right:72px;display:flex;gap:20px'>
<div style='flex:1;background:var(--row);border-radius:24px;padding:22px 28px'><div style='font-size:22px;color:{GREY};font-weight:800;letter-spacing:.08em'>ÉCART AU GÉNÉRAL</div><div class='num' style='font-size:44px;font-weight:900;color:{O}'>{d['gap']} pts</div></div>
<div style='flex:1;background:var(--row);border-radius:24px;padding:22px 28px'><div style='font-size:22px;color:{GREY};font-weight:800;letter-spacing:.08em'>FACE-À-FACE</div><div class='num' style='font-size:44px;font-weight:900'>{h0} – {h1}</div></div></div>"""
    return page(body, "Le duel", f"Après {apres_site(site)}", idx, total)


def last_time(site: str, season_label: str, previous: bool, by_cat: dict, highlights: list[dict]) -> list[str]:
    """Carrousel « L'an dernier ici » : podiums femmes, podiums hommes, stats marquantes."""
    kick = f"L'AN DERNIER · {season_label}" if previous else f"LA DERNIÈRE FOIS · {season_label}"
    head = ("L'an dernier " if previous else "La dernière fois ") + a_site_txt(site)
    cats = [c for c in ("SW", "SM") if by_cat.get(c)]
    total = len(cats) + (1 if highlights else 0)
    slides = []
    for i, cat in enumerate(cats):
        set_cat(cat)
        fem = cat == "SW"
        blocks = ""
        for m, podium, fr in by_cat[cat]:
            names = "".join(
                f"<div style='display:flex;align-items:center;gap:16px;font-size:34px;font-weight:{900 if k == 0 else 700};padding:6px 0'>"
                f"<span style='width:40px;color:{O if k == 0 else GREY};font-weight:900'>{k + 1}</span>{nat(r['nat'], 36)}"
                f"<span class='{'fr' if r['nat'] == HOME else ''}' style='flex:1'>{e(r['name'])}</span></div>" for k, r in enumerate(podium))
            o = ordinal_f if fem else ordinal
            fr_line = (f"<div style='font-size:26px;color:var(--soft);font-weight:700;margin-top:6px'>{flag(HOME)} {'Meilleure Française' if fem else 'Meilleur Français'} : "
                       f"{e(fr['name'])}, {o(fr['rank'])}</div>") if fr and fr["rank"] > 3 else ""
            blocks += (f"<div style='padding:20px 0;border-top:1px solid var(--line)'><div style='font-size:25px;color:{O};font-weight:800;"
                       f"letter-spacing:.08em;margin-bottom:4px'>{e(m['label'].upper())}</div>{names}{fr_line}</div>")
        body = f"""<div style='position:absolute;top:180px;left:72px;right:72px'>{kicker(kick)}{title(head, 58)}
<div style='font-size:28px;color:var(--soft);font-weight:700;margin-top:8px'>Les podiums {'femmes' if fem else 'hommes'}</div></div>
<div style='position:absolute;top:410px;left:72px;right:72px'>{blocks}</div>"""
        slides.append(page(body, site, "L'an dernier" if previous else "La dernière fois", i + 1, total))
    if highlights:
        set_cat(None)
        cards = "".join(
            f"<div style='background:var(--row);border-radius:26px;padding:30px 36px;margin-bottom:20px'>"
            f"<div style='font-size:24px;color:{GREY};font-weight:800;letter-spacing:.08em'>{e(h['label'].upper())}</div>"
            f"<div class='num' style='font-size:84px;font-weight:900;color:{O};line-height:1.05;margin-top:6px'>{e(h['big'])}</div>"
            f"<div style='display:flex;align-items:center;gap:14px;font-size:30px;font-weight:800;margin-top:6px'>{nat(h['nat'], 32)}"
            f"<span class='{'fr' if h['nat'] == HOME else ''}'>{e(h['sub'])}</span></div></div>" for h in highlights)
        body = f"""<div style='position:absolute;top:180px;left:72px;right:72px'>{kicker(kick)}{title('Les chiffres à retenir', 64)}</div>
<div style='position:absolute;top:380px;left:72px;right:72px'>{cards}</div>"""
        slides.append(page(body, site, "L'an dernier" if previous else "La dernière fois", total, total))
    return slides


def story_anniversaire(a: dict, card: dict, gen_rank: int | None, gen_score: int) -> str:
    """Story du jour de l'anniversaire : prenom, age, 3 stats de saison."""
    set_cat(a["cat"])
    fem = a["cat"] == "SW"
    o = ordinal_f if fem else ordinal

    def stat(k, v):
        return (f"<div style='background:var(--row);border-radius:24px;padding:26px 34px;margin-bottom:16px;display:flex;align-items:center'>"
                f"<span style='flex:1;font-size:28px;color:{GREY};font-weight:800;letter-spacing:.06em'>{e(k)}</span>"
                f"<span class='num' style='font-size:52px;font-weight:900;color:{O}'>{e(v)}</span></div>")
    stats_html = (stat("MEILLEUR RÉSULTAT", o(card["best"]) if card["best"] else "-")
                  + stat("TIR CETTE SAISON", f"{card['tir']} %" if card["tir"] is not None else "-")
                  + stat("AU GÉNÉRAL", f"{o(gen_rank)} · {gen_score} pts" if gen_rank else "-"))
    size = 120 if len(a["last"]) < 10 else 92
    body = f"""<div style='position:absolute;top:300px;left:72px;right:72px'>{kicker('🎂 JOYEUX ANNIVERSAIRE')}
<div style='font-size:150px;line-height:1;margin-top:40px'>🎉</div>
<div style='font-size:46px;color:{GREY};font-weight:700;margin-top:30px'>{e(a['first'])}</div>
<div class='fr' style='font-size:{size}px;font-weight:900;line-height:.95;text-transform:uppercase'>{e(a['last'])}</div>
<div style='font-size:64px;font-weight:900;margin-top:26px'><span style='color:{O}'>{a['age']}</span> ans aujourd'hui {flag(HOME)}</div></div>
<div style='position:absolute;top:1030px;left:72px;right:72px'>
<div style='font-size:26px;color:{GREY};font-weight:800;letter-spacing:.08em;margin-bottom:16px'>SA SAISON EN CHIFFRES</div>{stats_html}</div>"""
    return page(body, "Anniversaire", e(a["first"]), height=1920)


def story_poursuite(meta: dict, mv: dict) -> str:
    """Story apres poursuite : remontee du jour (fleche verte), chute du jour (fleche rouge)."""
    set_cat(meta.get("cat"))
    fem = meta.get("cat") == "SW"
    o = ordinal_f if fem else ordinal
    RED = "#e5484d"

    def card(label, r, color, arrow, top, note=""):
        if not r:
            return ""
        size = 58 if len(r["last"]) < 11 else 46
        fails = r["misses_total"] or 0
        return f"""<div style='position:absolute;top:{top}px;left:72px;right:72px;background:var(--row);border-radius:30px;padding:28px 40px'>
<div style='font-size:26px;color:{color};font-weight:800;letter-spacing:.08em'>{e(label)}</div>
<div style='display:flex;align-items:center;gap:18px;margin-top:16px'>{nat(r['nat'], 44)}
<div style='flex:1'><div style='font-size:28px;color:{GREY};font-weight:600'>{e(r['first'])}</div>
<div class='{'fr' if r['nat'] == HOME else ''}' style='font-size:{size}px;font-weight:900;line-height:1;text-transform:uppercase'>{e(r['last'])}</div></div>
<div style='text-align:right;color:{color};font-weight:900'><div style='font-size:60px;line-height:1'>{arrow}</div><div class='num' style='font-size:54px'>{'+' if r['gain'] > 0 else '−'}{abs(r['gain'])}</div></div></div>
<div class='num' style='font-size:34px;font-weight:800;margin-top:16px'>Parti{'e' if fem else ''} {o(r['start'])} → arrivé{'e' if fem else ''} {o(r['rank'])}</div>
<div style='font-size:28px;color:var(--soft);font-weight:700;margin-top:8px'>{fails} faute{'s' if fails > 1 else ''} au tir{e(note)}</div></div>"""
    down_note = " : la cause probable" if (mv.get("down") or {}).get("misses_total", 0) >= 4 else ""
    fr = mv.get("fr")
    body = f"""<div style='position:absolute;top:270px;left:72px;right:72px'>{kicker('LA POURSUITE EN UNE IMAGE')}
<div style='font-size:40px;font-weight:800;margin-top:10px;color:var(--soft)'>{e(meta['label'])} · {e(meta['site'])}</div></div>
{card('🚀 LA REMONTÉE DU JOUR', mv.get('up'), 'var(--up)', '▲', 400)}
{card('📉 LA CHUTE DU JOUR', mv.get('down'), RED, '▼', 770, down_note)}
{card('🇫🇷 ' + ('LA REMONTÉE FRANÇAISE'), fr, 'var(--fr)', '▲', 1140) if fr else ''}"""
    return page(body, meta["site"], "Poursuite", height=1920)

