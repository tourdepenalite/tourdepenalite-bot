"""Sonde 6 : le bot peut-il lire la musique dans le bucket prive ?"""
import os
import sys

sys.path.insert(0, ".")
from tdp import reel  # noqa: E402

m = reel.pick_music("BT2627SWRLCP01SWIN", 29.4)
if m:
    print("MUSIQUE OK", m["start"], os.path.getsize(m["file"]), "octets")
else:
    print("MUSIQUE INTROUVABLE")
