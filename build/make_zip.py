"""Zippt dist/Whisproq -> build/payload/Whisproq.zip (fuer die Setup-EXE).

Bewusst Python statt PowerShell: Compress-Archive scheitert an den
tk-tzdata-Dateien der PyInstaller-Ausgabe (z.B. _tcl_data/tzdata/America/
St_Vincent). Prueft am Ende, dass ALLE Dateien im Zip gelandet sind.
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dist", "Whisproq")
DST = os.path.join(ROOT, "build", "payload", "Whisproq.zip")

if not os.path.isdir(SRC):
    sys.exit(f"FEHLER: {SRC} fehlt - erst PyInstaller laufen lassen (build.ps1)")

os.makedirs(os.path.dirname(DST), exist_ok=True)
written = 0
with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, files in os.walk(SRC):
        for name in files:
            p = os.path.join(root, name)
            z.write(p, os.path.relpath(p, SRC))
            written += 1

expected = sum(len(f) for _r, _d, f in os.walk(SRC))
with zipfile.ZipFile(DST) as z:
    packed = len(z.namelist())
if packed != expected or packed != written:
    sys.exit(f"FEHLER: unvollstaendig - {packed} im Zip, {expected} auf Platte")
print(f"OK: {packed}/{expected} Dateien -> {DST}")
