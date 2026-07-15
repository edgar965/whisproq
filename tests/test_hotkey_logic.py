r"""Deterministischer Test der Hotkey-Logik (_combo_handler) mit
FAKE-Scancode-Events. Braucht KEINEN Tastatur-Treiber / keine echte
Session — die Scancodes kommen aus keyboard.parse_hotkey, also exakt die,
die auch in echten Events stehen. Deckt Einzeltaste und (Modifier-)Kombi
ab. Ausfuehren: ..\venv\Scripts\python.exe tests\test_hotkey_logic.py
"""
import sys

sys.path.insert(0, r"A:\repos\Whisproq")
import keyboard
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
    def __init__(self, sc, t):
        self.scan_code, self.event_type = sc, t


def scancodes(hk):
    """Pro Taste EIN konkreter Scancode (der erste der Gruppe)."""
    return [sorted(g)[0] for g in keyboard.parse_hotkey(hk)[0]]


def reset():
    calls["press"] = calls["release"] = 0
    whisproq._st["on"] = False


def check(name, hk, expect_press_after):
    """Drueckt die Tasten der Reihe nach; expect_press_after = nach wie vielen
    Tastendruecken _press kommen muss. Dann alle loslassen -> _release."""
    reset()
    h = whisproq._combo_handler(hk)
    scs = scancodes(hk)
    ok = True
    for i, sc in enumerate(scs, 1):
        h(Ev(sc, "down"))
        want = 1 if i >= expect_press_after else 0
        if calls["press"] != want:
            ok = False
    # Auto-Repeat der letzten Taste darf nicht doppelt starten
    h(Ev(scs[-1], "down"))
    if calls["press"] != 1:
        ok = False
    # eine Taste loslassen -> stoppt
    h(Ev(scs[-1], "up"))
    if calls["release"] != 1:
        ok = False
    # zweiter Zyklus muss wieder gehen
    for sc in scs:
        h(Ev(sc, "down"))
    if calls["press"] != 2:
        ok = False
    print(f"[{'OK ' if ok else 'FAIL'}] {name} ({hk})")
    return ok


r = []
r.append(check("Einzeltaste", "f10", 1))
r.append(check("Strg+Windows", "ctrl+windows", 2))
r.append(check("Strg+Shift", "ctrl+shift", 2))
r.append(check("Strg+Leertaste", "ctrl+space", 2))

# irrelevante Taste stoert nicht
reset()
h = whisproq._combo_handler("ctrl+windows")
c, w = scancodes("ctrl+windows")
h(Ev(999, "down"))                       # Fremdtaste
h(Ev(c, "down"))
h(Ev(w, "down"))
extra_ok = calls["press"] == 1
print(f"[{'OK ' if extra_ok else 'FAIL'}] Fremdtaste stoert nicht")
r.append(extra_ok)

print(f"\n{sum(r)}/{len(r)} bestanden")
sys.exit(0 if all(r) else 1)
