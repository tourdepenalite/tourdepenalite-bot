"""Stockage public des images (Supabase), publication Instagram, validation Telegram."""
from __future__ import annotations

import json
import pathlib
import time

import requests

from . import config

# ------------------------------------------------------------------ stockage

def upload(path: pathlib.Path, key: str) -> str:
    """Meta va chercher l'image lui-meme : elle doit etre sur une URL publique (bucket public)."""
    if config.DRY_RUN:
        return path.resolve().as_uri()
    url = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{config.SUPABASE_BUCKET}/{key}"
    key_ = (config.SUPABASE_SERVICE_KEY or "").strip().strip('"').strip("'")
    if key_.lower().startswith("bearer "):
        key_ = key_[7:].strip()
    headers = {"apikey": key_, "Content-Type": "image/jpeg", "x-upsert": "true"}
    if not key_.startswith("sb_"):
        # Anciennes cles service_role (JWT) : elles passent aussi dans Authorization.
        # Les nouvelles cles sb_secret ne sont pas des JWT : Storage les refuse dans Authorization.
        headers["Authorization"] = f"Bearer {key_}"
    r = requests.post(url, data=path.read_bytes(), timeout=60, headers=headers)
    if not r.ok:
        kind = ("sb_secret" if key_.startswith("sb_secret_") else "sb_publishable" if key_.startswith("sb_publishable_")
                else "JWT" if key_.startswith("eyJ") else "format inconnu")
        raise RuntimeError(f"Supabase {r.status_code} : {r.text[:300]} | cle de type {kind}, {len(key_)} caracteres")
    return f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{config.SUPABASE_BUCKET}/{key}"


# ------------------------------------------------------------------ Instagram

def _graph() -> str:
    return f"https://{config.IG_GRAPH_HOST}"


def _ig(method: str, path: str, **params) -> dict:
    params["access_token"] = config.IG_ACCESS_TOKEN
    url = f"{_graph()}/{config.IG_API_VERSION}/{path}"
    r = requests.request(method, url, params=params if method == "GET" else None,
                         data=params if method == "POST" else None, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Instagram {path}: {r.status_code} {r.text[:300]}")
    return r.json()


def _wait(container_id: str):
    # La doc conseille de verifier environ une fois par minute, 5 minutes maximum.
    for _ in range(10):
        st = _ig("GET", container_id, fields="status_code").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container_id}: {st}")
        time.sleep(30)
    raise RuntimeError(f"container {container_id}: delai depasse")


def _container(**params) -> str:
    if config.IG_MARK_AI:
        params["is_ai_generated"] = "true"
    return _ig("POST", f"{config.IG_USER_ID}/media", **params)["id"]


def publish_feed(urls: list[str], caption: str) -> str:
    if config.DRY_RUN:
        return "dry-run"
    if len(urls) == 1:
        cid = _container(image_url=urls[0], caption=caption)
    else:
        children = [_container(image_url=u, is_carousel_item="true") for u in urls[: config.MAX_CAROUSEL]]
        cid = _container(media_type="CAROUSEL", children=",".join(children), caption=caption)
    _wait(cid)
    return _ig("POST", f"{config.IG_USER_ID}/media_publish", creation_id=cid)["id"]


def publish_story(url: str) -> str:
    if config.DRY_RUN:
        return "dry-run"
    cid = _container(image_url=url, media_type="STORIES")
    _wait(cid)
    return _ig("POST", f"{config.IG_USER_ID}/media_publish", creation_id=cid)["id"]


def quota() -> dict:
    return _ig("GET", f"{config.IG_USER_ID}/content_publishing_limit", fields="quota_usage,config")


def my_instagram_accounts() -> list[dict]:
    """Unified Login : liste les comptes Instagram partages avec l'app (donne IG_USER_ID)."""
    return _ig("GET", "me/assigned_instagram_accounts").get("data", [])


def refresh_token() -> str:
    """Seulement pour l'ancienne API Instagram Login (graph.instagram.com)."""
    r = requests.get("https://graph.instagram.com/refresh_access_token", params={"grant_type": "ig_refresh_token",
                     "access_token": config.IG_ACCESS_TOKEN}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


# ------------------------------------------------------------------ Telegram

def _tg(method: str, **payload) -> dict:
    if config.DRY_RUN or not config.TELEGRAM_BOT_TOKEN:
        print(f"[telegram:{method}]", json.dumps(payload, ensure_ascii=False)[:400])
        return {"result": []}
    r = requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def send_for_approval(key: str, urls: list[str], caption: str, story_url: str | None = None):
    media = [{"type": "photo", "media": u} for u in (urls + ([story_url] if story_url else []))[:10]]
    if len(media) == 1:
        _tg("sendPhoto", chat_id=config.TELEGRAM_CHAT_ID, photo=media[0]["media"])
    else:
        _tg("sendMediaGroup", chat_id=config.TELEGRAM_CHAT_ID, media=media)
    _tg("sendMessage", chat_id=config.TELEGRAM_CHAT_ID, text=f"{key}\n\n{caption}"[:4000],
        reply_markup={"inline_keyboard": [[{"text": "✅ Publier", "callback_data": f"ok|{key}"},
                                           {"text": "❌ Annuler", "callback_data": f"no|{key}"}]]})


def notify(text: str):
    try:
        _tg("sendMessage", chat_id=config.TELEGRAM_CHAT_ID, text=text[:4000])
    except Exception as exc:  # une alerte ratee ne doit pas arreter le bot
        print("telegram: alerte non envoyee :", exc, "|", text[:200])


def read_decisions(offset: int) -> tuple[list[tuple[str, str]], int]:
    """Lit les clics sur les boutons depuis le dernier passage (pas de serveur a heberger)."""
    try:
        data = _tg("getUpdates", offset=offset, timeout=0, allowed_updates=["callback_query"])
    except Exception as exc:
        # Jeton Telegram invalide ou service indisponible : on continue sans les validations.
        print("telegram: lecture des validations impossible :", exc)
        return [], offset
    out = []
    for u in data.get("result", []):
        offset = max(offset, u["update_id"] + 1)
        cq = u.get("callback_query")
        if not cq or str(cq.get("message", {}).get("chat", {}).get("id")) != str(config.TELEGRAM_CHAT_ID):
            continue
        action, _, key = (cq.get("data") or "").partition("|")
        out.append((action, key))
        _tg("answerCallbackQuery", callback_query_id=cq["id"], text="Publication lancée" if action == "ok" else "Annulé")
    return out, offset
