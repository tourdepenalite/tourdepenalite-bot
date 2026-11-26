"""Redaction par Claude : titres, stat du jour, legende. Claude ne recoit que des faits
calcules et doit les reutiliser tels quels. Sans cle API, un texte de secours est produit."""
from __future__ import annotations

import json
import re

from . import config

SYSTEM = """Tu écris pour @tourdepenalite, un compte Instagram français de statistiques de biathlon.
Ton : simple, punchy, chaleureux, pour des fans. Phrases courtes. Tutoiement collectif interdit.
Règles strictes :
- Utilise UNIQUEMENT les faits et chiffres fournis. N'invente aucun chiffre, aucun record, aucune citation, aucune info sur la vie des athlètes.
- Ne modifie aucun nombre. N'ajoute pas de superlatif historique ("historique", "record") sauf s'il est dans les faits.
- Pas de tiret cadratin.
- Réponds uniquement avec un objet JSON valide, sans texte autour."""

HASHTAGS = "#biathlon #biathlonfrance #coupedumondebiathlon #equipedefrance"


def _ask(prompt: str) -> dict | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(model=config.CLAUDE_MODEL, max_tokens=900, system=SYSTEM,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as exc:  # le texte de secours prend le relais
        print("captions: echec Claude", exc)
        return None


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", s or ""))


def _safe(text: str, facts: str, limit: int) -> bool:
    """Garde-fou : tout nombre ecrit par Claude doit exister dans les faits fournis."""
    return bool(text) and len(text) <= limit and _numbers(text) <= _numbers(facts)


def post_race(meta: dict, facts: str, candidates: list[dict], fallback_headline: str) -> dict:
    cand_txt = "\n".join(f"{i}. {c['fact']}" for i, c in enumerate(candidates[:6]))
    prompt = f"""Course : {meta['label']} à {meta['site']}.
Faits calculés :
{facts}
Stats candidates pour la slide "La stat du jour" :
{cand_txt or '(aucune)'}

Rends ce JSON :
{{"headline": "titre du podium, 45 caractères max, sur le vainqueur ou le meilleur Français",
"stat_index": numéro de la stat candidate la plus partageable (priorité aux Français si elle est forte),
"stat_headline": "phrase choc de 60 caractères max reprenant cette stat",
"stat_detail": "phrase d'explication de 140 caractères max",
"caption": "légende Instagram de 3 à 5 lignes : résultat, meilleur Français, une question pour faire réagir. Emojis sobres."}}"""
    out = _ask(prompt) or {}
    all_facts = facts + "\n" + cand_txt
    res = {
        "headline": out.get("headline") if _safe(out.get("headline"), all_facts, 60) else fallback_headline,
        "caption": out.get("caption") if _safe(out.get("caption"), all_facts, 1500) else facts,
    }
    idx = out.get("stat_index", 0) if isinstance(out.get("stat_index"), int) else 0
    if candidates:
        c = candidates[min(max(idx, 0), len(candidates) - 1)]
        res["stat"] = {
            "big": c["big"],
            "headline": out.get("stat_headline") if _safe(out.get("stat_headline"), c["fact"], 80) else c.get("short", c["fact"]),
            "detail": out.get("stat_detail") if _safe(out.get("stat_detail"), c["fact"], 170) else c["fact"],
        }
    res["caption"] = res["caption"].strip() + "\n\n" + HASHTAGS
    return res


def generic(kind: str, facts: str, fallback_headline: str, fallback_caption: str) -> dict:
    prompt = f"""Type de post : {kind}.
Faits calculés :
{facts}

Rends ce JSON :
{{"headline": "titre de 45 caractères max", "caption": "légende Instagram de 3 à 5 lignes, avec une question pour faire réagir"}}"""
    out = _ask(prompt) or {}
    head = out.get("headline") if _safe(out.get("headline"), facts, 60) else fallback_headline
    cap = out.get("caption") if _safe(out.get("caption"), facts, 1500) else fallback_caption
    return {"headline": head, "caption": cap.strip() + "\n\n" + HASHTAGS}
