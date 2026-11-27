"""Sonde 7 : etat de Telegram (lecture seule, ne confirme aucune mise a jour)."""
import json
import os

import requests

T = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = os.environ.get("TELEGRAM_CHAT_ID")
api = lambda m, **p: requests.post(f"https://api.telegram.org/bot{T}/{m}", json=p, timeout=30).json()
me = api("getMe")
print("getMe ok:", me.get("ok"), "bot:", (me.get("result") or {}).get("username"))
wh = api("getWebhookInfo")
print("webhook:", json.dumps({k: v for k, v in (wh.get("result") or {}).items() if k != "url"}), "url set:", bool((wh.get("result") or {}).get("url")))
st = json.load(open("state.json"))
off = st.get("tg_offset", 0)
up = api("getUpdates", offset=off, timeout=0)
print("getUpdates ok:", up.get("ok"), up.get("description"), "pending:", len(up.get("result") or []))
for u in (up.get("result") or [])[:20]:
    cq = u.get("callback_query")
    if cq:
        print(" callback", u["update_id"], cq.get("data"), "chat match:", str(cq.get("message", {}).get("chat", {}).get("id")) == str(CHAT))
    else:
        print(" other", u["update_id"], list(u.keys()))
chat = api("getChat", chat_id=CHAT)
print("getChat ok:", chat.get("ok"), chat.get("description"), (chat.get("result") or {}).get("type"))
