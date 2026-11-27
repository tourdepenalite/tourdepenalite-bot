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
    ctype = {".mp4": "video/mp4", ".png": "image/png"}.get(path.suffix.lower(), "image/jpeg")
    headers = {"apikey": key_, "Content-Type": ctype, "x-upsert": "true"}
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


def _container(top: bool = True, **params) -> str:
    # Etiquette IA : uniquement sur le conteneur publie (le carrousel), jamais sur ses images.
    if config.IG_MARK_AI and top:
        params["is_ai_generated"] = "true"
    return _ig("POST", f"{config.IG_USER_ID}/media", **params)["id"]


def publish_feed(urls: list[str], caption: str, alts: list[str] | None = None) -> str:
    """alt_text : texte alternatif par image (images du fil uniquement, pas les stories)."""
    if config.DRY_RUN:
        return "dry-run"
    alts = (alts or []) + [""] * len(urls)

    def alt(i):
        return {"alt_text": alts[i][:1000]} if alts[i] else {}
    if len(urls) == 1:
        cid = _container(image_url=urls[0], caption=caption, **alt(0))
    else:
        children = [_container(top=False, image_url=u, is_carousel_item="true", **alt(i))
                    for i, u in enumerate(urls[: config.MAX_CAROUSEL])]
        cid = _container(media_type="CAROUSEL", children=",".join(children), caption=caption)
    _wait(cid)
    return _ig("POST", f"{config.IG_USER_ID}/media_publish", creation_id=cid)["id"]


def publish_reel(url: str, caption: str, thumb_ms: int = 0) -> str:
    """Reel (video MP4 sur URL publique). share_to_feed : visible dans le fil et l'onglet Reels."""
    if config.DRY_RUN:
        return "dry-run"
    cid = _container(media_type="REELS", video_url=url, caption=caption, share_to_feed="true", thumb_offset=str(thumb_ms))
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


def send_for_approval(key: str, urls: list[str], caption: str, stories: list[str] | str | None = None,
                      video: str | None = None):
    caption = caption or "(story seule)"
    if video:
        _tg("sendVideo", chat_id=config.TELEGRAM_CHAT_ID, video=video, supports_streaming=True)
    stories = [stories] if isinstance(stories, str) else (stories or [])
    imgs = list(urls) + list(stories)
    # Albums Telegram : 10 images maximum chacun.
    for i in range(0, len(imgs), 10):
        g = imgs[i:i + 10]
        if len(g) == 1:
            _tg("sendPhoto", chat_id=config.TELEGRAM_CHAT_ID, photo=g[0])
        else:
            _tg("sendMediaGroup", chat_id=config.TELEGRAM_CHAT_ID, media=[{"type": "photo", "media": u} for u in g])
    if stories:
        caption = f"{caption}\n\n({len(urls)} visuel(s) dans le fil, {len(stories)} story(s))"
    note = "\n\n⏱ Après ton clic, le bot le traite à son prochain passage (5 min max) et met ce message à jour."
    _tg("sendMessage", chat_id=config.TELEGRAM_CHAT_ID, text=(f"{key}\n\n{caption}"[:3850] + note),
        reply_markup={"inline_keyboard": [[{"text": "✅ Publier", "callback_data": f"ok|{key}"},
                                           {"text": "❌ Annuler", "callback_data": f"no|{key}"}]]})


def notify(text: str):
    try:
        _tg("sendMessage", chat_id=config.TELEGRAM_CHAT_ID, text=text[:4000])
    except Exception as exc:  # une alerte ratee ne doit pas arreter le bot
        print("telegram: alerte non envoyee :", exc, "|", text[:200])


def mark_message(ref: dict | None, status: str):
    """Met a jour le message de validation : boutons retires, statut ajoute en tete."""
    if not ref:
        return
    try:
        _tg("editMessageText", chat_id=ref["chat_id"], message_id=ref["message_id"],
            text=f"{status}\n\n{ref.get('text', '')}"[:4096])
    except Exception as exc:  # message trop ancien ou deja modifie : sans importance
        print("telegram: message non mis a jour :", exc)


def read_decisions(offset: int) -> tuple[list[tuple[str, str, dict]], int]:
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
        msg = cq.get("message") or {}
        out.append((action, key, {"chat_id": msg.get("chat", {}).get("id"), "message_id": msg.get("message_id"),
                                  "text": msg.get("text", "")}))
        try:  # Telegram refuse de confirmer un clic trop ancien : sans importance, la decision est gardee
            _tg("answerCallbackQuery", callback_query_id=cq["id"], text="Publication lancée" if action == "ok" else "Annulé")
        except Exception as exc:
            print("telegram: clic confirme trop tard :", exc)
    return out, offset
