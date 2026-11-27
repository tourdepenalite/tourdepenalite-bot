"""Sonde 5 : texte du rapport « Competition Data Summary » (C82), donnees techniques du parcours."""
import io
import sys

import requests
from pypdf import PdfReader

sys.path.insert(0, ".")
from tdp.ibu import Client  # noqa: E402

c = Client()
for rid in ("BT2627SWRLCP01SMIN", "BT2526SWRLCP01SWSP", "BT2526SWRLCP01SWPU"):
    reps = c.get("Reports", RaceId=rid)
    for r in reps:
        if "Data Summary" in (r.get("Description") or "") or "Competition Analysis" in (r.get("Description") or ""):
            pdf = requests.get(r["URL"], timeout=60).content
            text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages[:2])
            print(f"\n===== {rid} {r['Description']}\n" + text[:3500])
