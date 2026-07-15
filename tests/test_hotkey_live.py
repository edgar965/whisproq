"""LIVE-Test der Hotkey-Registrierung mit ECHTEN (simulierten) Tasten.

Installiert den echten keyboard-Hook via whisproq._apply_hotkey, mockt
_press/_release (kein Audio/Groq/Tippen) und feuert die Tastenkombis
ueber keyboard.press/release durch den kompletten Pfad
(OS-Event -> keyboard-Hook -> _combo_handler -> is_pressed). Genau der
Pfad, den der Fake-Event-Test NICHT abdeckte.

WICHTIG: Vorher jede laufende Whisproq-Instanz beenden (Mutex + doppelte
Hooks). Wird nicht ins normale CI aufgenommen — braucht eine echte
Windows-Session mit Tastatur-Treiber.
"""
import sys
import time

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


def context_sees_keyboard():
    """Sentinel: empfaengt dieser Prozess ueberhaupt (simulierte) Tasten-
    Events? In einer nicht-interaktiven/detachten Session (z.B. einem
    Automatisierungs-Agenten) liefert der keyboard-Hook NICHTS — dann ist
    dieser Test nicht aussagekraeftig und wird uebersprungen."""
    got = []
    hk = keyboard.hook(lambda e: got.append(1))
    time.sleep(0.2)
    keyboard.press("a")
    time.sleep(0.15)
    keyboard.release("a")
    time.sleep(0.15)
    keyboard.unhook(hk)
    return bool(got)


def reset():
    calls["press"] = calls["release"] = 0
    whisproq._st["on"] = False


def run(name, hotkey, seq):
    """seq: Liste von ('press'|'release', keyname). Prueft, dass genau
    ein press+release herauskommt."""
    reset()
    whisproq._apply_hotkey(hotkey)
    time.sleep(0.2)
    for action, key in seq:
        getattr(keyboard, action)(key)
        time.sleep(0.12)
    whisproq._remove_hotkeys()
    ok = calls["press"] == 1 and calls["release"] == 1
    print(f"[{'OK ' if ok else 'FAIL'}] {name} ({hotkey}): "
          f"press={calls['press']} release={calls['release']}")
    return ok


if not context_sees_keyboard():
    print("SKIP: dieser Prozess empfaengt keine Tastatur-Events "
          "(nicht-interaktive Session) — Live-Test nur in echter "
          "Desktop-Session aussagekraeftig. Logik: tests\\test_hotkey_logic.py")
    sys.exit(0)

results = []
# 1) Einzeltaste
results.append(run("Einzeltaste F10", "f10",
                   [("press", "f10"), ("release", "f10")]))
# 2) modifier-only Kombi, sicher (kein OS-Shortcut)
results.append(run("Modifier-Kombi Strg+Shift", "ctrl+shift",
                   [("press", "ctrl"), ("press", "shift"),
                    ("release", "shift"), ("release", "ctrl")]))
# 3) der reale Fall: Strg+Windows
results.append(run("Strg+Windows", "ctrl+windows",
                   [("press", "ctrl"), ("press", "windows"),
                    ("release", "windows"), ("release", "ctrl")]))
keyboard.send("esc")                     # evtl. Startmenue wieder zu

print(f"\n{sum(results)}/{len(results)} Hotkey-Typen loesen aus")
sys.exit(0 if all(results) else 1)
