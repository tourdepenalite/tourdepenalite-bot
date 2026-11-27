"""Reel « Revivre la course » : la course rejouee tir par tir, en video verticale 1080x1920.

Donnees (API IBU, verifiees sur l'individuel de Kontiolahti 2026-27) :
- AnalyticResults LAPn : temps du tour n, tir et penalites compris. Somme des LAP = temps final
  (+ ecart de depart en poursuite). Le classement apres le tir k = somme LAP1..k.
- AnalyticResults CRSn : temps de ski du tour n, pour l'ordre d'arrivee au pas de tir.
- L'ordre des cibles manquees n'est pas publie : les fautes sont affichees en fin de serie.

Rendu : une page HTML dont l'etat depend d'un temps t (fonction JS draw(t)), capturee image par
image avec Playwright (rendu deterministe), puis encodee en H.264 avec ffmpeg.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

from . import config
from .stats import fmt_time, ordinal, ordinal_f, parse_time
from .templates import HOME, flag, page, set_cat, a_site_txt, e

FPS = 30
HOOK, INTRO, STAGE, FINISH, OUTRO = 3.0, 2.4, 4.8, 4.4, 1.8
TOP_ROWS = 10
TOP_FR = 3


# ---------------------------------------------------------------- donnees

def load_rows(client, race_id: str, nr_shootings: int) -> list[dict]:
    """Resultats + temps par tour / temps de ski, depuis l'API."""
    res = client.results(race_id, cache_s=3600)
    laps = {}
    for t in [f"LAP{i}" for i in range(1, nr_shootings + 2)] + [f"CRS{i}" for i in range(1, nr_shootings + 2)]:
        try:
            laps[t] = {x.get("IBUId"): x.get("Result") or x.get("TotalTime")
                       for x in client.analytic(race_id, t).get("Results") or []}
        except Exception:
            laps[t] = {}
    rows = []
    for x in res.get("Results") or []:
        if x.get("IsTeam"):
            continue
        i = x.get("IBUId")
        rows.append({"ibu": i, "first": x.get("GivenName") or "", "last": x.get("FamilyName") or "", "nat": x.get("Nat") or "",
                     "rank": int(x["Rank"]) if str(x.get("Rank") or "").isdigit() else None, "total": x.get("TotalTime"),
                     "shootings": x.get("Shootings"), "start": x.get("StartTime"),
                     "lap": [laps.get(f"LAP{k}", {}).get(i) for k in range(1, nr_shootings + 2)],
                     "crs": [laps.get(f"CRS{k}", {}).get(i) for k in range(1, nr_shootings + 2)]})
    return rows


def _gap(s: float) -> str:
    if s < 0.05:
        return ""
    m, sec = divmod(round(s, 1), 60)
    return (f"+{int(m)}:{sec:04.1f}" if m else f"+{sec:.1f}").replace(".", ",")


def build(meta: dict, rows: list[dict]) -> dict:
    """Prepare la chronologie : athletes suivis, tirs, classements apres chaque tir, podium."""
    stages = config.DISCIPLINES.get(meta["disc"], {}).get("stages") or []
    n = len(stages)
    fem = meta.get("cat") == "SW"
    o = ordinal_f if fem else ordinal
    t0 = min((dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")) for r in rows if r.get("start")), default=None)
    ath = []
    for r in rows:
        laps = [parse_time(x) for x in r["lap"][:n]]
        if not r.get("shootings") or None in laps:
            continue
        misses = [int(x) if x.strip().isdigit() else 0 for x in r["shootings"].split("+")][:n]
        total = parse_time(r.get("total"))
        offset = 0.0
        if meta["disc"] == "PU" and total is not None and None not in (parse_time(x) for x in r["lap"]):
            offset = max(0.0, total - sum(parse_time(x) for x in r["lap"]))   # ecart de depart de la poursuite
        cum = [offset + sum(laps[:k + 1]) for k in range(n)]
        start = 0.0
        if meta["disc"] in ("SP", "IN") and r.get("start") and t0:
            start = (dt.datetime.fromisoformat(r["start"].replace("Z", "+00:00")) - t0).total_seconds()
        crs = [parse_time(x) or 0 for x in r["crs"][:n]]
        net = [(cum[k - 1] if k else offset) + crs[k] for k in range(n)]   # temps de course a l'arrivee au tir k
        arrive = [start + net[k] for k in range(n)]                          # heure d'arrivee au tir k
        ath.append({**r, "misses": misses, "cum": cum, "arrive": arrive, "net": net})
    if not ath:
        return {}
    # Homonymes (ex. Emilien et Fabien Claude) : initiale du prenom devant le nom
    lasts = [a["last"] for a in ath]
    for a in ath:
        a["show"] = f"{a['first'][:1]}. {a['last']}" if lasts.count(a["last"]) > 1 and a["first"] else a["last"]
    final = sorted([a for a in ath if a["rank"]], key=lambda a: a["rank"])
    standings, prev, positions = [], {}, []
    for k in range(n):
        order = sorted(ath, key=lambda a: a["cum"][k])
        lead = order[0]["cum"][k]
        pos = {a["ibu"]: i + 1 for i, a in enumerate(order)}
        top = [{"rank": i + 1, "last": a["show"], "nat": a["nat"], "gap": _gap(a["cum"][k] - lead),
                "miss": sum(a["misses"][:k + 1]), "delta": (prev.get(a["ibu"], i + 1) - (i + 1)) if k else 0}
               for i, a in enumerate(order[:5])]
        fr = next(((i + 1, a) for i, a in enumerate(order) if a["nat"] == HOME), None)
        if fr and fr[0] > 5:
            top.append({"rank": fr[0], "last": fr[1]["show"], "nat": HOME, "gap": _gap(fr[1]["cum"][k] - lead),
                        "miss": sum(fr[1]["misses"][:k + 1]), "delta": (prev.get(fr[1]["ibu"], fr[0]) - fr[0]) if k else 0})
        standings.append(top)
        positions.append(pos)
        prev = pos
    # Liste affichee a chaque tir = classement au moment du tir (temps de course a l'arrivee au pas de tir) :
    # les 10 premiers, plus le meilleur Francais s'il n'y est pas.
    # Athletes suivis : top 10 final + 3 meilleurs Francais (hors top 10), ordonnes a chaque tir
    # selon le classement au moment du tir (temps de course a l'arrivee au pas de tir, tous partants).
    focus = final[:TOP_ROWS] + [a for a in final[TOP_ROWS:] if a["nat"] == HOME][:TOP_FR]
    vis, at_pos = [], []
    for k in range(n):
        order = sorted(ath, key=lambda a: a["net"][k])
        at_pos.append({a["ibu"]: i + 1 for i, a in enumerate(order)})
        vis.append(sorted(focus, key=lambda a: at_pos[k][a["ibu"]]))
    slots, arr_rank = [], []
    for k in range(n):
        slots.append({a["ibu"]: i for i, a in enumerate(vis[k])})
        arr_rank.append({a["ibu"]: i for i, a in enumerate(sorted(vis[k], key=lambda a: a["arrive"][k]))})
    win = final[0]
    podium = [{"rank": a["rank"], "first": a["first"], "last": a["last"], "nat": a["nat"],
               "time": str(a["total"]).replace(".", ",") if a["rank"] == 1 else _gap(parse_time(a["total"]) - parse_time(win["total"])),
               "shots": f"{5 * n - sum(a['misses'])}/{5 * n}"} for a in final[:3]]
    best_fr = next((a for a in final if a["nat"] == HOME), None)
    hooks = _hooks(meta, ath, final, positions, n, t0)
    return {
        "hooks": hooks, "hook": "vainqueur",  # choix de Quentin (27/11) ; les deux autres restent disponibles
        "label": meta["label"], "site": meta["site"], "stages": [s.upper() for s in stages], "fem": fem,
        "focus": [{"last": a["show"], "nat": a["nat"], "flag": flag(a["nat"]), "fr": a["nat"] == HOME, "misses": a["misses"],
                   "arr": [arr_rank[k].get(a["ibu"]) for k in range(n)], "nvis": [len(v) for v in vis],
                   "pos": [at_pos[k][a["ibu"]] for k in range(n)], "slot": [slots[k].get(a["ibu"]) for k in range(n)]} for a in focus],
        "nrows": max(len(v) for v in vis),
        "standings": [[{**s, "flag": flag(s["nat"]), "fr": s["nat"] == HOME} for s in st] for st in standings],
        "podium": [{**p, "flag": flag(p["nat"]), "fr": p["nat"] == HOME} for p in podium],
        "best_fr": ({"name": f"{best_fr['first']} {best_fr['last']}", "rank": o(best_fr["rank"])}
                    if best_fr and best_fr["rank"] > 3 else None),
        "timing": {"hook": HOOK, "intro": INTRO, "stage": STAGE, "finish": FINISH, "outro": OUTRO},
    }


def _hooks(meta, ath, final, positions, n, t0) -> dict:
    """Trois accroches possibles pour les 3 premieres secondes, calculees sur la course."""
    fem = meta.get("cat") == "SW"
    win, second = final[0], final[1] if len(final) > 1 else None
    shots = 5 * n
    hits = shots - sum(win["misses"])
    starts = sorted((a for a in ath if a.get("start")), key=lambda a: a["start"])
    start_pos = next((i + 1 for i, a in enumerate(starts) if a["ibu"] == win["ibu"]), None)
    h = {}
    miss = shots - hits
    sub = ("Aucune faute" if not miss else f"{miss} faute{'s' if miss > 1 else ''}") + (
        f" · parti{'e' if fem else ''} {start_pos}{'re' if fem and start_pos == 1 else 'er' if start_pos == 1 else 'e'}"
        if start_pos and meta["disc"] in ("SP", "IN") else "")
    h["vainqueur"] = {"last": win["last"], "flag": flag(win["nat"]), "big": f"{hits}/{shots}", "sub": sub,
                      "word": "VAINQUEUSE" if fem else "VAINQUEUR", "rewind": "Revivez la course"}
    # Retournement : la plus grosse chute apres un tir (un Francais en priorite)
    best = None
    for k in range(1, n):
        for a in ath:
            p0, p1 = positions[k - 1].get(a["ibu"]), positions[k].get(a["ibu"])
            if not p0 or not p1 or p0 > 30 or not a["misses"][k]:
                continue
            drop = p1 - p0
            score = drop + (100 if a["nat"] == HOME and drop >= 5 else 0)
            if drop >= 5 and (not best or score > best[0]):
                best = (score, a, k, p0, p1, drop)
    if best:
        _, a, k, p0, p1, drop = best
        m = a["misses"][k]
        h["retournement"] = {"last": a["last"], "flag": flag(a["nat"]), "fr": a["nat"] == HOME, "misses": m, "stage": k + 1,
                             "line1": f"{m} balle{'s' if m > 1 else ''}.", "line2": f"{drop} places perdues.",
                             "from": p0, "to": p1}
    if second:
        gap = parse_time(second["total"]) - parse_time(win["total"])
        if gap >= 20:
            h["chiffre"] = {"value": gap, "label": f"d'avance sur {'la' if fem else 'le'} 2e", "last": win["last"], "flag": flag(win["nat"])}
    return h


def duration(data: dict) -> float:
    return HOOK + INTRO + STAGE * len(data["stages"]) + FINISH + OUTRO


# ---------------------------------------------------------------- page animee

STYLE = """
.k2{font-size:28px;color:var(--flash);font-weight:800;letter-spacing:.12em}
.tl{position:absolute;top:470px;left:72px;right:150px;height:70px}
.tl .bar{position:absolute;top:44px;left:12px;right:12px;height:6px;border-radius:3px;background:var(--bar)}
.tl .fill{position:absolute;top:44px;left:12px;height:6px;border-radius:3px;background:var(--flash)}
.tl .st{position:absolute;top:0;transform:translateX(-50%);font-size:17px;font-weight:800;letter-spacing:.06em;color:var(--muted);white-space:nowrap;text-align:center}
.tl .pt{position:absolute;top:38px;width:18px;height:18px;border-radius:50%;background:var(--bg);border:4px solid var(--bar);transform:translateX(-50%)}
.tl .pt.on{border-color:var(--flash);background:var(--flash)}
.foot{display:none}
.row{position:absolute;left:72px;right:150px;height:44px;border-radius:14px;display:flex;align-items:center;padding:0 18px;font-size:27px;font-weight:800;transition:none}
.row .nm{flex:1;margin-left:14px;white-space:nowrap;overflow:hidden;text-transform:uppercase}
.tg{width:26px;height:26px;border-radius:50%;margin-left:9px;border:3px solid var(--ink);background:transparent}
.tg.hit{background:var(--ink)}
.tg.miss{border-color:var(--flash);background:var(--flash)}
.cnt{width:70px;text-align:right;font-size:24px;color:var(--muted);font-weight:800}
.banner{position:absolute;left:0;right:0;top:820px;text-align:center}
.banner span{display:inline-block;background:var(--flash);color:var(--on-flash);font-size:78px;font-weight:900;padding:14px 46px;border-radius:22px;letter-spacing:.04em}
.sd{position:absolute;left:72px;right:150px;height:41px;display:flex;align-items:center;font-size:26px;font-weight:800;border-top:1px solid var(--line)}
.sd .r{width:56px;color:var(--grey)} .sd .n{flex:1;margin-left:12px;text-transform:uppercase} .sd .g{width:150px;text-align:right}
.sd .d{width:64px;text-align:right;font-size:20px}
#hook{position:absolute;inset:0;z-index:20;background:var(--bg-grad, var(--bg));overflow:hidden}
#hook .big{font-weight:900;line-height:.9;letter-spacing:-.02em}
.pod{position:absolute;left:72px;right:150px;border-radius:26px;background:var(--row);display:flex;align-items:center;padding:0 30px}
"""


def html(data: dict) -> str:
    set_cat("SW" if data["fem"] else "SM")
    body = f"""<style>{STYLE}</style>
<div id='head' style='position:absolute;top:270px;left:72px;right:150px'>
<div class='k2'>REVIVRE LA COURSE</div>
<div style='font-size:66px;font-weight:900;line-height:1.02;margin-top:10px'>{e(data['label'])}</div>
<div style='font-size:36px;color:var(--grey);font-weight:700;margin-top:10px'>{e(data['site'])} <span style='font-size:22px;color:var(--muted)'>· temps officiels IBU</span></div></div>
<div class='tl' id='tl'></div>
<div id='rows'></div><div id='sds'></div>
<div class='banner' id='banner'><span></span></div>
<div id='fin'></div><div id='outro'></div><div id='hook'></div>
<script>
const D = {json.dumps(data, ensure_ascii=False)};
const T = D.timing, N = D.stages.length;
const clamp = (x, a=0, b=1) => Math.max(a, Math.min(b, x));
const ease = x => 1 - Math.pow(1 - clamp(x), 3);
const labels = ['DÉPART'].concat(D.stages.map((s, i) => 'TIR ' + (i + 1))).concat(['ARRIVÉE']);
const tl = document.getElementById('tl');
const W = 1080 - 72 - 150 - 24;
tl.innerHTML = "<div class='bar'></div><div class='fill' id='fill'></div>" + labels.map((l, i) => {{
  const x = 12 + W * i / (labels.length - 1);
  return `<div class='st' style='left:${{x}}px'>${{l}}</div><div class='pt' id='pt${{i}}' style='left:${{x}}px'></div>`; }}).join('');
const rows = document.getElementById('rows');
rows.innerHTML = D.focus.map((a, i) => `<div class='row' id='r${{i}}' style='top:600px;opacity:0'>
  <span class='ps' id='p${{i}}' style='width:58px;font-size:24px;color:var(--grey);font-weight:900'></span><span style='font-size:30px'>${{a.flag}}</span><span class='nm' style='color:${{a.fr ? "var(--fr)" : "var(--ink)"}}'>${{a.last}}</span>
  ${{[0,1,2,3,4].map(j => `<span class='tg' id='t${{i}}_${{j}}'></span>`).join('')}}<span class='cnt' id='c${{i}}'></span></div>`).join('');
const SD_TOP = 590 + D.nrows * 49 + 18;
function stageStart(k) {{ return T.intro + k * T.stage; }}
function drawHook(t) {{
  const el = document.getElementById('hook'), H = D.hooks[D.hook];
  if (t >= T.hook) {{ el.style.display = 'none'; return; }}
  el.style.display = 'block';
  const out = t > T.hook - 0.35 ? (T.hook - t) / 0.35 : 1;
  el.style.opacity = out;
  const a = x => ease(clamp(x));
  const top = `<div style='position:absolute;top:300px;left:72px;font-size:28px;font-weight:800;letter-spacing:.12em;color:var(--grey)'>${{D.site.toUpperCase()}} · ${{D.label.toUpperCase()}}</div>`;
  if (D.hook === 'vainqueur') {{
    const rw = t >= 1.9;
    el.innerHTML = top + `<div style='position:absolute;top:470px;left:72px;right:150px;filter:${{rw ? 'blur(' + (t - 1.9) * 6 + 'px)' : 'none'}}'>
      <div style='font-size:60px;opacity:${{a(t / 0.3)}}'>${{H.flag}}</div>
      <div class='big' style='font-size:150px;margin-top:10px;transform:scale(${{0.8 + 0.2 * a(t / 0.35)}});transform-origin:left;opacity:${{a(t / 0.25)}}'>${{H.last}}</div>
      <div class='big' style='font-size:230px;color:var(--flash);margin-top:30px;opacity:${{a((t - 0.45) / 0.3)}}'>${{H.big}}</div>
      <div style='font-size:64px;font-weight:900;margin-top:30px;letter-spacing:.06em;opacity:${{a((t - 0.9) / 0.3)}}'>${{H.word}}</div>
      <div style='font-size:34px;font-weight:700;color:var(--grey);margin-top:14px;opacity:${{a((t - 1.1) / 0.3)}}'>${{H.sub}}</div></div>` +
      (rw ? `<div style='position:absolute;top:1300px;left:72px;right:150px;font-size:62px;font-weight:900;color:var(--flash);opacity:${{a((t - 1.9) / 0.2)}}'>⏪ ${{H.rewind}}</div>` : '');
  }} else if (D.hook === 'retournement') {{
    const shots = [0,1,2,3,4].map(j => {{
      const on = t >= 0.25 + j * 0.16, miss = j >= 5 - H.misses;
      const pop = miss && on ? 1 + 0.35 * (1 - a((t - 0.25 - j * 0.16) / 0.25)) : 1;
      return `<span style='display:inline-block;width:96px;height:96px;border-radius:50%;margin-right:22px;border:8px solid ${{miss && on ? 'var(--flash)' : 'var(--ink)'}};background:${{on ? (miss ? 'var(--flash)' : 'var(--ink)') : 'transparent'}};transform:scale(${{pop}})'></span>`; }}).join('');
    el.innerHTML = top + `<div style='position:absolute;top:430px;left:72px;right:150px'>
      <div style='font-size:30px;font-weight:800;letter-spacing:.1em;color:var(--grey)'>TIR ${{H.stage}}</div>
      <div style='margin-top:26px'>${{shots}}</div>
      <div class='big' style='font-size:170px;margin-top:70px;opacity:${{a((t - 1.1) / 0.25)}}'>${{H.line1}}</div>
      <div class='big' style='font-size:118px;color:var(--flash);margin-top:20px;opacity:${{a((t - 1.5) / 0.25)}};transform:translateY(${{(1 - a((t - 1.5) / 0.25)) * 30}}px)'>${{H.line2}}</div>
      <div style='display:flex;align-items:center;gap:18px;font-size:52px;font-weight:900;margin-top:50px;opacity:${{a((t - 2.0) / 0.25)}}'>${{H.flag}}<span style='color:${{H.fr ? 'var(--fr)' : 'var(--ink)'}}'>${{H.last}}</span>
      <span style='font-size:40px;color:var(--grey);font-weight:800'>${{H.from}}e → ${{H.to}}e</span></div></div>`;
  }} else {{
    const v = H.value * a((t - 0.2) / 1.4);
    const m = Math.floor(v / 60), sec = (v - m * 60).toFixed(1).replace('.', ',');
    const txt = m ? `${{m}}:${{sec.padStart(4, '0')}}` : sec;
    el.innerHTML = top + `<div style='position:absolute;top:520px;left:72px;right:150px'>
      <div class='big' style='font-size:260px;color:var(--flash)'>+${{txt}}</div>
      <div style='font-size:60px;font-weight:900;margin-top:30px;opacity:${{a((t - 1.4) / 0.3)}}'>${{H.label}}</div>
      <div style='display:flex;align-items:center;gap:18px;font-size:56px;font-weight:900;margin-top:60px;opacity:${{a((t - 1.8) / 0.3)}}'>${{H.flag}} ${{H.last}}</div></div>`;
  }}
}}
function draw(t0) {{
  drawHook(t0);
  const t = t0 - T.hook;
  // frise
  let prog = 0;
  for (let k = 0; k < N; k++) if (t >= stageStart(k) + 0.4) prog = k + 1;
  const fin0 = stageStart(N);
  if (t >= fin0) prog = N + 1;
  const target = prog / (labels.length - 1);
  document.getElementById('fill').style.width = (W * target) + 'px';
  labels.forEach((_, i) => document.getElementById('pt' + i).className = 'pt' + (i <= prog ? ' on' : ''));
  // stage courante
  const k = Math.min(N - 1, Math.max(0, Math.floor((t - T.intro) / T.stage)));
  const s0 = stageStart(k), inStages = t >= T.intro && t < fin0;
  const showRows = t >= T.intro - 0.6 && t < fin0 + 0.3;
  const kk = t < T.intro ? 0 : k;
  const mv = (t < T.intro || kk === 0) ? 1 : ease((t - s0 + 0.1) / 0.6);
  D.focus.forEach((a, i) => {{
    const r = document.getElementById('r' + i);
    const cur = a.slot[kk], prv = kk > 0 ? a.slot[kk - 1] : cur;
    const appear = ease((t - (T.intro - 0.8) - (cur ?? 0) * 0.04) / 0.5);
    const out = t >= fin0 ? 1 - ease((t - fin0) / 0.4) : 1;
    // visibilite : entre / sort de la liste au debut de chaque tir
    let vis = 0;
    if (cur != null && prv != null) vis = 1;
    else if (cur != null) vis = mv;            // entre dans le top 10
    else if (prv != null) vis = 1 - mv;        // sort du top 10
    r.style.opacity = showRows ? Math.min(appear, out, vis) : 0;
    r.style.transform = `translateX(${{(1 - Math.min(appear, vis)) * -40}}px)`;
    const y0 = prv ?? cur ?? 0, y1 = cur ?? prv ?? 0;
    r.style.top = (590 + 49 * (y0 + (y1 - y0) * mv)) + 'px';
    document.getElementById('p' + i).textContent = (mv >= 0.5 || kk === 0 ? a.pos[kk] : a.pos[kk - 1]) + 'e';
    const nf = a.nvis[kk];
    const on = cur != null;
    const ts = on ? s0 + 0.9 + 2.1 * (a.arr[kk] / Math.max(1, nf - 1)) : 1e9;
    const shooting = inStages && on && t >= ts && t < ts + 1.0;
    r.style.background = shooting ? 'var(--lead-bg)' : (a.fr ? 'var(--fr-bg)' : 'var(--row)');
    const miss = a.misses[kk];
    for (let j = 0; j < 5; j++) {{
      const el = document.getElementById(`t${{i}}_${{j}}`);
      const done = inStages && on && t >= ts + 0.18 * j;
      el.className = 'tg' + (done ? (j >= 5 - miss ? ' miss' : ' hit') : '');
    }}
    let tot = 0;
    for (let q = 0; q < kk; q++) tot += a.misses[q];
    if (inStages && on && t >= ts + 0.9) tot += a.misses[kk];
    const c = document.getElementById('c' + i);
    c.textContent = t >= T.intro ? tot + ' F' : '';
    c.style.color = tot ? 'var(--flash)' : 'var(--muted)';
  }});
  // bandeau TIR k
  const b = document.getElementById('banner');
  const bt = (t - s0) / 0.9;
  b.style.opacity = inStages && bt >= 0 && bt < 1 ? (bt < 0.2 ? bt / 0.2 : bt > 0.75 ? (1 - bt) / 0.25 : 1) : 0;
  b.style.transform = `scale(${{0.9 + 0.1 * ease(bt / 0.3)}})`;
  b.firstChild.textContent = `TIR ${{k + 1}} · ${{D.stages[k]}}`;
  // classement apres le tir k
  const sds = document.getElementById('sds');
  const sk = t >= s0 + 3.2 ? k : k - 1;
  if (sk >= 0 && inStages) {{
    const st = D.standings[sk], since = t - (sk === k ? s0 + 3.2 : stageStart(k));
    sds.innerHTML = `<div style='position:absolute;top:${{SD_TOP}}px;left:72px;font-size:24px;font-weight:800;letter-spacing:.1em;color:var(--grey)'>CLASSEMENT APRÈS LE TIR ${{sk + 1}}</div>` +
      st.map((s, i) => {{
        const a = sk === k ? ease((since - i * 0.08) / 0.35) : 1;
        const d = s.delta > 0 ? `<span style='color:var(--up)'>▲${{s.delta}}</span>` : s.delta < 0 ? `<span style='color:var(--flash)'>▼${{-s.delta}}</span>` : '';
        return `<div class='sd' style='top:${{SD_TOP + 36 + i * 41}}px;opacity:${{a}};transform:translateY(${{(1 - a) * 16}}px)'>
          <span class='r'>${{s.rank}}</span><span>${{s.flag}}</span><span class='n' style='color:${{s.fr ? "var(--fr)" : "var(--ink)"}}'>${{s.last}}</span>
          <span class='d'>${{d}}</span><span class='g'>${{s.gap || 'en tête'}}</span></div>`; }}).join('');
  }} else sds.innerHTML = '';
  // arrivee : podium
  const f = document.getElementById('fin');
  if (t >= fin0 + 0.3) {{
    const ft = t - fin0 - 0.3;
    f.innerHTML = `<div style='position:absolute;top:620px;left:72px;font-size:30px;font-weight:800;letter-spacing:.12em;color:var(--flash);opacity:${{ease(ft / 0.4)}}'>ARRIVÉE</div>` +
      D.podium.map((p, i) => {{
        const a = ease((ft - 0.3 - (2 - i) * 0.35) / 0.45);
        const big = i === 0;
        return `<div class='pod' style='top:${{690 + i * 190}}px;height:${{big ? 170 : 160}}px;opacity:${{a}};transform:translateY(${{(1 - a) * 40}}px);${{big ? 'background:var(--lead-bg)' : ''}}'>
          <span style='font-size:${{big ? 96 : 76}}px;font-weight:900;width:110px;color:${{big ? 'var(--flash)' : 'var(--grey)'}}'>${{p.rank}}</span>
          <span style='font-size:44px'>${{p.flag}}</span>
          <div style='flex:1;margin-left:20px'><div style='font-size:28px;color:var(--grey);font-weight:600'>${{p.first}}</div>
          <div style='font-size:${{big ? 52 : 44}}px;font-weight:900;line-height:1;text-transform:uppercase;color:${{p.fr ? "var(--fr)" : "var(--ink)"}}'>${{p.last}}</div></div>
          <div style='text-align:right'><div style='font-size:36px;font-weight:900'>${{p.time}}</div><div style='font-size:24px;color:var(--grey);font-weight:700'>${{p.shots}} au tir</div></div></div>`; }}).join('') +
      (D.best_fr ? `<div style='position:absolute;top:1280px;left:72px;right:150px;font-size:32px;font-weight:800;color:var(--fr);opacity:${{ease((ft - 1.8) / 0.4)}}'>🇫🇷 ${{D.fem ? 'Meilleure Française' : 'Meilleur Français'}} : ${{D.best_fr.name}}, ${{D.best_fr.rank}}</div>` : '');
  }} else f.innerHTML = '';
  // fin
  const ou = document.getElementById('outro');
  const ot = t - (fin0 + T.finish);
  ou.innerHTML = ot >= 0 ? `<div style='position:absolute;top:1400px;left:72px;right:150px;font-size:34px;font-weight:800;opacity:${{ease(ot / 0.4)}}'>Toutes les stats sur <span style='color:var(--flash)'>@tourdepenalite</span> 🎯</div>` : '';
}}
window.draw = draw;
draw(0);
</script>"""
    return page(body, data["site"], "Revivre la course", height=1920)


def record(data: dict, out: pathlib.Path, audio: str | None = None, until: float | None = None) -> pathlib.Path:
    """Capture image par image puis encode en MP4 (H.264, 30 i/s)."""
    from playwright.sync_api import sync_playwright
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="reel_"))
    n = int((until or duration(data)) * FPS)
    with sync_playwright() as p:
        exe = os.environ.get("TDP_CHROME")
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        pg.set_content(html(data))
        pg.wait_for_timeout(200)
        for f in range(n):
            pg.evaluate(f"draw({f / FPS})")
            pg.screenshot(path=str(tmp / f"{f:05d}.jpg"), type="jpeg", quality=88)
        b.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(tmp / "%05d.jpg")]
    if audio:
        cmd += ["-i", audio, "-shortest", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out
