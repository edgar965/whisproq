#!/usr/bin/env python3
"""
Whisproq — Push-to-talk-Diktat via Groq-Cloud (Whisper + Groq).

Hotkey (Default F10) GEDRUECKT HALTEN = aufnehmen, LOSLASSEN = transkribieren
(Groq whisper-large-v3-turbo, ~0,5 s) und ins AKTIVE Feld einfuegen —
systemweit, auch Terminals/CLIs. Diktierte deutsche Satzzeichen ("Komma",
"Punkt", "Fragezeichen", ...) werden deterministisch umgewandelt
(punctuation.py); Whispers eigene Satzzeichen bleiben erhalten und werden
nie verdoppelt.

Kein Fenster ausser dem Overlay, keine lokalen Modelle. Abhaengigkeiten
bewusst minimal (nur keyboard + sounddevice; Audio/HTTP ueber die
Python-Stdlib), damit die PyInstaller-EXE klein bleibt. Einzelinstanz via
Windows-Mutex.

Key: GROQ_API_KEY aus Prozess-Env, sonst aus HKCU\\Environment (setx-Registry) —
wird bei jedem Druck neu gelesen, ein spaeteres setx wirkt also ohne Neustart.

Wege auf einen neuen Rechner:
  a) Whisproq_Setup.exe doppelklicken (kein Python noetig), oder
  b) Repo klonen/kopieren + install.bat (venv-Variante).
Log: whisproq.log neben Programm (Fallback: %LOCALAPPDATA%\\Whisproq).
"""
import ctypes
import io
import json
import logging
import os
import sys
import threading
import time
import urllib.request
import uuid
import wave
from array import array
from logging.handlers import RotatingFileHandler

__version__ = "0.21"

# Gefroren (PyInstaller-EXE) oder als Skript? Bestimmt Basisverzeichnis.
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(os.path.abspath(sys.executable))
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import punctuation                                    # noqa: E402
import guards                                         # noqa: E402

import sounddevice as sd                              # noqa: E402
import keyboard                                       # noqa: E402

# --- Konfiguration ---
# live_preview: true  -> waehrend der Hotkey gehalten wird, zeigt das Overlay
#                        den Zwischenstand (alle `interval` s via Groq).
#                        Kostet ~3x Kontingent (Puffer wird mehrfach gesendet).
# live_preview: false -> schlank, Text erst beim Loslassen (nur 1 Request).
# language:            Whisper-Sprachcode ("de", "en", ...). Die
#                      Satzzeichen-Wort-Umwandlung laeuft nur bei "de".
# Gespeichert wird IMMER in die User-Config %LOCALAPPDATA%\Whisproq\
# config.json — nie in die config.json neben dem Programm: die ist nur das
# Default-Template und liegt bei der venv-Variante im git-Repo (Zahnrad-
# Speichern soll das Repo nicht dirty machen). Gelesen wird die User-Config,
# falls vorhanden, sonst das Template.
_CFG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "Whisproq")
_CFG_PATH = os.path.join(_CFG_DIR, "config.json")
# Whisper-Prompt = Erkennungs-Kontext. Default LEER: Feldversuch 2026-07-15
# zeigte, dass ein Satzzeichen-Woerter-Prompt bei Edgars Fernfeld-Mikro ab
# ~RMS 400 KONSISTENT Islaendisch provozierte ("Ég testi það..." fuer
# "Ich teste das..."); ohne Prompt gab es nie Fremdsprachen. Wer
# experimentieren will, setzt "prompt" in config.json.
_cfg = {"live_preview": False, "interval": 3.0, "hotkey": "f10",
        "language": "de", "prompt": ""}
for _p in (_CFG_PATH, os.path.join(HERE, "config.json")):
    try:
        # utf-8-sig: PowerShell (Setup-Update) schreibt UTF-8 MIT BOM
        with open(_p, encoding="utf-8-sig") as _f:
            _raw = json.load(_f)
        _cfg["live_preview"] = bool(_raw.get("live_preview", False))
        _cfg["interval"] = float(_raw.get("live_preview_interval_s", 3.0))
        _cfg["hotkey"] = (str(_raw.get("hotkey", "f10")).strip().lower()
                          or "f10")
        _cfg["language"] = (str(_raw.get("language", "de")).strip().lower()
                            or "de")
        _cfg["prompt"] = str(_raw.get("prompt", ""))
        break
    except (OSError, ValueError):
        continue


def _save_config():
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        with open(_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump({"live_preview": _cfg["live_preview"],
                       "live_preview_interval_s": _cfg["interval"],
                       "hotkey": _cfg["hotkey"],
                       "language": _cfg["language"],
                       "prompt": _cfg["prompt"]},
                      f, indent=2)
        log.info("Konfig gespeichert (%s): %s", _CFG_PATH, _cfg)
    except OSError as e:
        log.warning("Konfig nicht speicherbar: %s", e)

_k32 = ctypes.windll.kernel32


def _log_dir():
    """Log neben dem Programm; wenn dort nicht schreibbar (z.B. Programme-
    Ordner), nach %LOCALAPPDATA%\\Whisproq. Nie System-Temp."""
    try:
        probe = os.path.join(HERE, ".write_probe")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return HERE
    except OSError:
        d = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "Whisproq")
        os.makedirs(d, exist_ok=True)
        return d


_handler = RotatingFileHandler(os.path.join(_log_dir(), "whisproq.log"),
                               maxBytes=1_000_000, backupCount=2,
                               encoding="utf-8")
logging.basicConfig(level=logging.INFO, handlers=[_handler],
                    format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("whisproq")

# --- Einzelinstanz (zwei Instanzen wuerden doppelt tippen) ---
# Nach der Log-Initialisierung, damit die zweite Instanz NICHT stumm stirbt,
# sondern nachvollziehbar ins Log schreibt, warum sie sich beendet.
_k32.CreateMutexW(None, False, "Whisproq_SingleInstance")
if _k32.GetLastError() == 183:                        # ERROR_ALREADY_EXISTS
    log.warning("Whisproq laeuft bereits (Mutex belegt) - "
                "diese zweite Instanz beendet sich.")
    sys.exit(0)

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
SR = 16000


def _read_key():
    k = os.environ.get("GROQ_API_KEY", "")
    if k:
        return k
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
            return winreg.QueryValueEx(reg, "GROQ_API_KEY")[0]
    except OSError:
        return ""


def _store_key(key):
    """Speichert den Key dorthin, wo _read_key() ihn findet: Prozess-Env +
    HKCU\\Environment (wie setx), inkl. WM_SETTINGCHANGE-Broadcast, damit
    auch neue Prozesse ihn ohne Neuanmeldung sehen. Key NIE ins Log!"""
    os.environ["GROQ_API_KEY"] = key
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_SET_VALUE) as reg:
            winreg.SetValueEx(reg, "GROQ_API_KEY", 0, winreg.REG_SZ, key)
        HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x2
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 5000, ctypes.byref(ctypes.c_ulong()))
        log.info("GROQ_API_KEY ueber das Zahnrad aktualisiert.")
    except OSError as e:
        log.warning("Key nicht speicherbar: %s", e)


def _groq_transcribe(wav_bytes, key):
    """Multipart-Upload an Groq ueber die Stdlib (kein requests noetig)."""
    boundary = "----whisproq" + uuid.uuid4().hex
    nl = b"\r\n"

    def part(name, value):
        return (b"--" + boundary.encode() + nl
                + f'Content-Disposition: form-data; name="{name}"'.encode()
                + nl + nl + value.encode() + nl)

    body = (part("model", "whisper-large-v3-turbo")
            + part("language", _cfg["language"])
            + part("temperature", "0")
            # verbose_json liefert avg_logprob je Segment (Halluzinations-
            # Filter). no_speech_prob ist bei Groq-turbo nutzlos: gemessen
            # 0.0 sogar bei purer Stille.
            + part("response_format", "verbose_json")
            # Vokabular-Vorspannung (s. _PROMPT_DEFAULT)
            + (part("prompt", _cfg["prompt"]) if _cfg["prompt"] else b"")
            + b"--" + boundary.encode() + nl
            + b'Content-Disposition: form-data; name="file"; '
              b'filename="audio.wav"' + nl
            + b"Content-Type: audio/wav" + nl + nl
            + wav_bytes + nl
            + b"--" + boundary.encode() + b"--" + nl)
    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "multipart/form-data; boundary=" + boundary,
                 # Cloudflare blockt den Default-UA "Python-urllib" mit 403
                 "User-Agent": "whisproq/" + __version__})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    text = (d.get("text") or "").strip()
    segs = d.get("segments") or []
    worst = min((s.get("avg_logprob", 0.0) for s in segs), default=0.0)
    ok, reason = guards.check(text, worst, _cfg["language"], _cfg["prompt"])
    if not ok:
        log.info("Verworfen (%s): %r", reason, text)
        return ""
    return text


def _postprocess(text):
    """Diktierte Satzzeichen-Woerter umwandeln — nur fuer Deutsch."""
    if _cfg["language"].startswith("de"):
        return punctuation.convert(text)
    return text


def _wav_bytes(pcm):
    """Rohe int16-PCM-Bytes -> WAV-Datei-Bytes (16 kHz mono)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return buf.getvalue()


# --- Overlay: erscheint beim Halten des Hotkeys, mit Zahnrad-Einstellungen ---
class _Overlay:
    """Kleines randloses Topmost-Fenster oben rechts. Zeigt beim Halten des
    Hotkeys Status/Zwischenstand, nach dem Loslassen kurz den finalen Text.
    Das Zahnrad oeffnet die Einstellungen (Live-Vorschau an/aus, Intervall).
    Tk laeuft im Main-Thread; andere Threads reden ueber eine Queue."""

    def __init__(self):
        import queue
        import tkinter as tk
        self._tk = tk
        self._q = queue.Queue()
        self._empty = queue.Empty
        self._hide_job = None
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)              # randlos
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        frame = tk.Frame(self.root, bg="#0d2137")
        frame.pack(fill="both", expand=True)
        self.label = tk.Label(frame, text="", font=("Segoe UI", 12),
                              bg="#0d2137", fg="#e0e8f0", justify="left",
                              wraplength=440, padx=14, pady=10)
        self.label.pack(side="left")
        gear = tk.Button(frame, text="⚙", command=self._settings,
                         font=("Segoe UI", 13), bd=0, cursor="hand2",
                         bg="#0d2137", fg="#8fa8c8",
                         activebackground="#16375c", activeforeground="#ffffff")
        gear.pack(side="right", anchor="n", padx=(0, 8), pady=6)
        self.root.after(80, self._poll)

    # -- Einstellungs-Dialog (laeuft im Tk-Thread, via Zahnrad-Klick) --
    def _settings(self):
        tk = self._tk
        win = tk.Toplevel(self.root)
        win.title("Whisproq %s — Einstellungen" % __version__)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(bg="#0d2137", padx=16, pady=12)
        var_prev = tk.BooleanVar(value=_cfg["live_preview"])
        var_int = tk.DoubleVar(value=_cfg["interval"])
        style = {"bg": "#0d2137", "fg": "#e0e8f0", "font": ("Segoe UI", 10)}
        tk.Checkbutton(win, text="Live-Vorschau beim Sprechen anzeigen",
                       variable=var_prev, selectcolor="#16375c",
                       activebackground="#0d2137", activeforeground="#e0e8f0",
                       **style).grid(row=0, column=0, columnspan=2,
                                     sticky="w", pady=(0, 8))
        tk.Label(win, text="Zwischenstand alle (Sekunden):",
                 **style).grid(row=1, column=0, sticky="w")
        tk.Spinbox(win, from_=0.5, to=10.0, increment=0.5, width=5,
                   textvariable=var_int).grid(row=1, column=1, sticky="w",
                                              padx=(8, 0))
        var_hk = tk.StringVar(value=_cfg["hotkey"])
        tk.Label(win, text="Hotkey (halten = Diktat):",
                 **style).grid(row=2, column=0, sticky="w", pady=(8, 0))
        tk.Entry(win, textvariable=var_hk, width=14,
                 bg="#16375c", fg="#e0e8f0", insertbackground="#e0e8f0",
                 font=("Segoe UI", 10)).grid(row=2, column=1, sticky="w",
                                             padx=(8, 0), pady=(8, 0))
        tk.Label(win, text="z.B. f10, f4 oder Kombis wie ctrl+space\n"
                           "(engl. Namen: ctrl, alt, shift, space)",
                 justify="left", bg="#0d2137", fg="#8fa8c8",
                 font=("Segoe UI", 9)).grid(row=3, column=0, columnspan=2,
                                            sticky="w", pady=(2, 4))
        tk.Label(win, text="Hinweis: Vorschau kostet ca. 3× Kontingent\n"
                           "(kostenlos sind ~2 h Audio pro Tag).",
                 justify="left", bg="#0d2137", fg="#8fa8c8",
                 font=("Segoe UI", 9)).grid(row=4, column=0, columnspan=2,
                                            sticky="w", pady=(4, 10))
        var_key = tk.StringVar(value=_read_key())
        tk.Label(win, text="Groq-API-Key:",
                 **style).grid(row=5, column=0, sticky="w")
        tk.Entry(win, textvariable=var_key, width=28, show="•",
                 bg="#16375c", fg="#e0e8f0", insertbackground="#e0e8f0",
                 font=("Segoe UI", 10)).grid(row=5, column=1, sticky="w",
                                             padx=(8, 0))
        tk.Label(win, text="beginnt mit gsk_… — kostenlos holen auf\n"
                           "console.groq.com/keys (leer = unverändert)",
                 justify="left", bg="#0d2137", fg="#8fa8c8",
                 font=("Segoe UI", 9)).grid(row=6, column=0, columnspan=2,
                                            sticky="w", pady=(2, 10))

        def save():
            _cfg["live_preview"] = bool(var_prev.get())
            try:
                _cfg["interval"] = max(0.5, float(var_int.get()))
            except (ValueError, tk.TclError):
                pass
            hk = var_hk.get().strip().lower()
            if hk and hk != _cfg["hotkey"]:
                try:
                    keyboard.parse_hotkey(hk)             # validiert Syntax
                    _cfg["hotkey"] = hk
                    _apply_hotkey(hk)
                except ValueError:
                    import tkinter.messagebox as mb
                    mb.showerror("Ungültiger Hotkey",
                                 f"'{hk}' ist kein gültiger Hotkey.\n"
                                 "Beispiele: f10, f4, ctrl+space, alt+d",
                                 parent=win)
                    return
            new_key = var_key.get().strip()
            if new_key and new_key != _read_key():
                _store_key(new_key)
            _save_config()
            win.destroy()

        tk.Button(win, text="Speichern", command=save, bg="#16375c",
                  fg="#ffffff", activebackground="#3b82f6",
                  font=("Segoe UI", 10), bd=0, padx=14,
                  pady=4).grid(row=7, column=0, sticky="w")
        tk.Button(win, text="Abbrechen", command=win.destroy, bg="#0d2137",
                  fg="#8fa8c8", font=("Segoe UI", 10), bd=0, padx=10,
                  pady=4).grid(row=7, column=1, sticky="w", padx=(8, 0))
        win.geometry("+%d+%d" % (self.root.winfo_x(),
                                 self.root.winfo_y() + 60))

    def _poll(self):
        try:
            while True:
                cmd, arg = self._q.get_nowait()
                if self._hide_job is not None:
                    self.root.after_cancel(self._hide_job)
                    self._hide_job = None
                if cmd == "hide":
                    self.root.withdraw()
                    continue
                self.label.config(text=arg)
                self.root.update_idletasks()
                sw = self.root.winfo_screenwidth()
                w = self.root.winfo_reqwidth()
                self.root.geometry("+%d+%d" % (max(sw - w - 40, 0), 40))
                self.root.deiconify()
                if cmd == "flash":                    # kurz zeigen, dann weg
                    self._hide_job = self.root.after(
                        4000, self.root.withdraw)
        except self._empty:
            pass
        self.root.after(80, self._poll)

    def set_text(self, text):
        self._q.put(("text", text))

    def flash(self, text):
        self._q.put(("flash", text))

    def hide(self):
        self._q.put(("hide", None))

    def run(self):
        self.root.mainloop()


OVERLAY = None                                        # wird in main() gebaut


def _interim_loop():
    """Schickt waehrend der Aufnahme alle _cfg['interval'] s den bisherigen
    Puffer an Groq und zeigt das Ergebnis im Overlay. Nur eine Anfrage
    gleichzeitig; das Finale beim Loslassen laeuft unabhaengig."""
    busy = False
    while _st["on"]:
        time.sleep(_cfg["interval"])
        if (not _st["on"] or busy or OVERLAY is None
                or not _cfg["live_preview"]):
            continue
        pcm = b"".join(_st["frames"])
        if len(pcm) < SR:                             # < 0,5 s
            continue
        busy = True
        try:
            t0 = time.monotonic()
            text = _groq_transcribe(_wav_bytes(pcm), _read_key())
            if _st["on"] and text:
                shown = _postprocess(text)
                OVERLAY.set_text(shown)
                log.info("Groq-Preview (%.2fs): %r", time.monotonic() - t0, shown)
        except Exception as e:
            log.info("Preview-Fehler: %s", e)
        finally:
            busy = False


# --- Einfuegen ins aktive Feld (Clipboard + Strg+V, umlautfest) ---
def _set_clipboard(text):
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    u32 = ctypes.windll.user32
    u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    u32.SetClipboardData.restype = ctypes.c_void_p
    _k32.GlobalAlloc.restype = ctypes.c_void_p
    _k32.GlobalLock.restype = ctypes.c_void_p
    _k32.GlobalLock.argtypes = [ctypes.c_void_p]
    _k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    data = text.encode("utf-16-le") + b"\x00\x00"
    if not u32.OpenClipboard(0):
        return False
    try:
        u32.EmptyClipboard()
        h = _k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        ptr = _k32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        _k32.GlobalUnlock(h)
        u32.SetClipboardData(CF_UNICODETEXT, h)
        return True
    finally:
        u32.CloseClipboard()


_recent = {"text": "", "t": 0.0}


def _type_into_active_field(text):
    if not text or not text.strip():
        return
    norm = text.strip()
    now = time.monotonic()
    if norm == _recent["text"] and (now - _recent["t"]) < 2.0:
        log.info("Doppel-Eintrag unterdrueckt: %r", text)
        return
    _recent["text"] = norm
    _recent["t"] = now
    text = _postprocess(text)
    if not text or not text.strip():
        return
    try:
        if _set_clipboard(text):
            keyboard.send("ctrl+v")
            log.info("Ins Feld eingefuegt: %r", text)
        else:
            keyboard.write(text, delay=0)
            log.info("Ins Feld getippt (Fallback): %r", text)
    except Exception as e:
        log.info("Einfuegen fehlgeschlagen: %s", e)


# --- Push-to-talk: halten -> aufnehmen (int16 roh), loslassen -> Groq ---
_st = {"on": False, "stream": None, "frames": []}


def _press(_e):
    if _st["on"]:                                     # Auto-Repeat beim Halten
        return
    key = _read_key()
    if not key:
        log.warning("PTT: GROQ_API_KEY fehlt (setx GROQ_API_KEY <key>)")
        return
    _st["frames"] = []
    _st["on"] = True

    def cb(indata, frames, t, s):
        if _st["on"]:
            _st["frames"].append(bytes(indata))

    try:
        # RawInputStream liefert rohe int16-Bytes -> kein numpy noetig
        _st["stream"] = sd.RawInputStream(samplerate=SR, channels=1,
                                          dtype="int16", callback=cb)
        _st["stream"].start()
        log.info("PTT: Aufnahme laeuft")
        if OVERLAY is not None:
            OVERLAY.set_text("● Aufnahme … (%s halten)"
                             % _cfg["hotkey"].upper())
            if _cfg["live_preview"]:
                threading.Thread(target=_interim_loop, daemon=True).start()
    except Exception as e:
        _st["on"] = False
        _st["stream"] = None
        log.warning("PTT: Mikrofon-Fehler: %s", e)


def _release(_e):
    if not _st["on"]:
        return
    _st["on"] = False
    stream = _st["stream"]
    _st["stream"] = None
    try:
        if stream:
            stream.stop()
            stream.close()
    except Exception:
        pass
    frames = _st["frames"]
    _st["frames"] = []
    if not frames:
        log.info("PTT: keine Audiodaten")
        if OVERLAY is not None:
            OVERLAY.hide()
        return
    pcm = b"".join(frames)
    dur = len(pcm) / 2.0 / SR
    samples = array("h", pcm)
    rms = (sum(x * x for x in samples) / len(samples)) ** 0.5
    # RMS immer mitloggen: Datenbasis zum Nachjustieren des Gates
    # (Messreihe: ab RMS < ~300 beginnt die Halluzinations-Zone)
    log.info("PTT: %.2fs Audio (RMS %.0f)", dur, rms)
    if dur < 0.3:                                     # Fehlklick
        if OVERLAY is not None:
            OVERLAY.hide()
        return
    # Lautstaerke-Gate: (Fast-)Stille gar nicht erst senden — Whisper
    # halluziniert darauf ("Vielen Dank."), und es kostet Kontingent.
    if rms < 60:
        log.info("PTT: zu leise (RMS %.0f) - verworfen", rms)
        if OVERLAY is not None:
            OVERLAY.flash("Zu leise — bitte lauter/näher sprechen")
        return
    if OVERLAY is not None:
        OVERLAY.set_text("… transkribiere")

    def work():
        try:
            wav = _wav_bytes(pcm)
            # letzte Aufnahme aufheben: bei Fehl-Erkennung kann damit
            # mit dem ECHTEN Audio diagnostiziert werden (statt zu raten)
            try:
                with open(os.path.join(_log_dir(),
                                       "last_utterance.wav"), "wb") as f:
                    f.write(wav)
            except OSError:
                pass
            t0 = time.monotonic()
            text = _groq_transcribe(wav, _read_key())
            dt = time.monotonic() - t0
            log.info("Groq (%.2fs): %r", dt, text)
            if text:
                _type_into_active_field(text + " ")
                if OVERLAY is not None:               # final kurz zeigen
                    OVERLAY.flash(_postprocess(text))
            elif OVERLAY is not None:                 # leer/als Muell verworfen
                OVERLAY.flash("Nicht verstanden — bitte erneut sprechen")
        except Exception as e:
            log.warning("Groq-Aufruf fehlgeschlagen: %s", e)
            if OVERLAY is not None:
                OVERLAY.hide()

    threading.Thread(target=work, daemon=True).start()


# --- Hotkey-Registrierung (einzelne Taste ODER Kombi wie "ctrl+f10") ---
_hk_handles = []


def _apply_hotkey(hk):
    """Registriert Push-to-talk auf `hk`; entfernt vorherige Registrierung.

    Einzeltaste ("f10"): Press/Release-Hooks direkt.
    Kombi ("ctrl+f10"): add_hotkey fuer den Druck, Release-Hook auf der
    letzten (Nicht-Modifier-)Taste. Wirft ValueError bei unbekannter Taste.
    """
    global _hk_handles
    keyboard.parse_hotkey(hk)                         # validieren (ValueError)
    for kind, h in _hk_handles:
        try:
            if kind == "combo":
                keyboard.remove_hotkey(h)
            else:
                keyboard.unhook(h)
        except (KeyError, ValueError):
            pass
    _hk_handles = []
    parts = [p.strip() for p in hk.split("+") if p.strip()]
    main_key = parts[-1]
    if len(parts) == 1:
        _hk_handles.append(("hook", keyboard.on_press_key(main_key, _press)))
        _hk_handles.append(("hook", keyboard.on_release_key(main_key, _release)))
    else:
        _hk_handles.append(("combo", keyboard.add_hotkey(hk, lambda: _press(None))))
        _hk_handles.append(("hook", keyboard.on_release_key(main_key, _release)))
    log.info("Hotkey aktiv: %s", hk)


def main():
    global OVERLAY
    _apply_hotkey(_cfg["hotkey"])
    log.info("Whisproq %s bereit (Key: %s, Live-Vorschau: %s, Hotkey: %s, "
             "Intervall: %.1fs, Sprache: %s)", __version__,
             bool(_read_key()), _cfg["live_preview"], _cfg["hotkey"],
             _cfg["interval"], _cfg["language"])
    OVERLAY = _Overlay()                              # Tk braucht den Main-Thread
    OVERLAY.run()


if __name__ == "__main__":
    main()
