r"""Deterministischer Test der Hotkey-Logik (_combo_handler) mit FAKE-Events,
die echte (scan_code, name)-Paare tragen — inkl. der auf Edgars deutschem
System gemessenen Werte (Windows-Taste sc=91 'linke windows', Strg sc=29
'strg'), die parse_hotkey NICHT liefert. Braucht keine echte Session.
Ausfuehren: ..\venv\Scripts\python.exe tests\test_hotkey_logic.py
"""
import sys

sys.path.insert(0, r"A:\repos\Whisproq")
import whisproq

calls = {"press": 0, "release": 0}


def fake_press(_e):
    if whisproq._st["on"]:
        return
    whisproq._st["on"] = True
    calls["press"] += 1


def fake_release(_e):
    if not whisproq._st["on"]:
        return
    whisproq._st["on"] = False
    calls["release"] += 1


whisproq._press = fake_press
whisproq._release = fake_release


class Ev:
    def __init__(self, sc, name, t):
        self.scan_code, self.name, self.event_type = sc, name, t


def reset():
    calls["press"] = calls["release"] = 0
    whisproq._st["on"] = False


results = []


def case(name, hk, keys):
    """keys: Liste (scan_code, event_name) der Tasten der Kombi in
    Druck-Reihenfolge. Prueft: alle druecken -> 1x press; letzte los -> 1x
    release; Auto-Repeat startet nicht doppelt; zweiter Zyklus geht."""
    reset()
    h = whisproq._combo_handler(hk)
    ok = True
    for i, (sc, nm) in enumerate(keys, 1):
        h(Ev(sc, nm, "down"))
        want = 1 if i == len(keys) else 0
        if calls["press"] != want:
            ok = False
    h(Ev(*keys[-1], "down"))                 # Auto-Repeat letzte Taste
    if calls["press"] != 1:
        ok = False
    h(Ev(*keys[-1], "up"))                    # eine los -> stop
    if calls["release"] != 1:
        ok = False
    for sc, nm in keys:                       # zweiter Zyklus
        h(Ev(sc, nm, "down"))
    if calls["press"] != 2:
        ok = False
    print(f"[{'OK ' if ok else 'FAIL'}] {name} ({hk})")
    results.append(ok)


# DER reale Bug-Fall: Windows-Taste liefert sc=91 (nicht 57435) + dt. Name
case("Strg+Windows (echte Werte sc=91/'linke windows')", "ctrl+windows",
     [(29, "strg"), (91, "linke windows")])
# rechte Windows-Taste (sc=92)
case("Strg+rechte Windows (sc=92)", "ctrl+windows",
     [(29, "strg"), (92, "rechte windows")])
# Einzeltaste
case("Einzeltaste F10", "f10", [(68, "f10")])
# andere Kombi, deutsche Namen
case("Strg+Umschalt (dt.)", "ctrl+shift",
     [(29, "strg"), (42, "umschalt")])

# reiner NAMENS-Match: scancode weicht voellig ab, nur der Name passt
reset()
h = whisproq._combo_handler("ctrl+windows")
h(Ev(29, "strg", "down"))
h(Ev(99999, "linke windows", "down"))        # unbekannter sc, aber Name passt
name_ok = calls["press"] == 1
print(f"[{'OK ' if name_ok else 'FAIL'}] Match nur ueber Namen (sc unbekannt)")
results.append(name_ok)

# Gegenprobe: Fremdtaste startet nichts
reset()
h = whisproq._combo_handler("ctrl+windows")
h(Ev(30, "a", "down"))
h(Ev(29, "strg", "down"))
none_ok = calls["press"] == 0                # Windows fehlt -> kein Start
print(f"[{'OK ' if none_ok else 'FAIL'}] ohne Windows kein Start")
results.append(none_ok)

print(f"\n{sum(results)}/{len(results)} bestanden")
sys.exit(0 if all(results) else 1)
