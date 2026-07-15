# Whisproq 🎙️

**Push-to-talk dictation for Windows** — hold a hotkey (default **F10**),
speak, release: the text appears in the **active text field** ~0.5 s later.
Works system-wide: Word, browsers, WhatsApp, even terminals and CLI tools.

The name says it all: **Whis**per + G**roq**. Transcription runs on Groq's
free cloud API using OpenAI's `whisper-large-v3-turbo` — no local models,
no GPU, no build step, no word quota.

## Features

- **Types into whatever has focus** — clipboard-based paste (umlaut-safe),
  with a typing fallback
- **Free**: Groq's free tier covers ~2 hours of dictated audio per day,
  no credit card required
- **Spoken punctuation (German)**: „Komma", „Punkt", „Fragezeichen",
  „neue Zeile" … converted deterministically — never doubled (if Whisper
  already emitted `.`, a spoken „Punkt" won't add a second one), and
  compounds like „Treffpunkt" stay intact
- **Live preview** (optional): an overlay shows the transcript *while* you
  speak, refreshed every few seconds
- **Settings via gear icon ⚙** in the overlay: live preview on/off,
  refresh interval, **configurable hotkey** (single key or combos like
  `ctrl+space`) — applied instantly, no restart
- **Tiny**: two dependencies (`keyboard`, `sounddevice`), audio + HTTP via
  the Python standard library, ~50 MB RAM, single-instance guard
- **Setup EXE** for machines without Python (PyInstaller + IExpress SFX)

## Install

**Option A — Setup EXE (recommended, no Python needed):**
Download `Whisproq_Setup.exe` from the
[Releases](../../releases) page and double-click it. The setup

- installs to `%LOCALAPPDATA%\Whisproq`
- asks for your `GROQ_API_KEY` (with step-by-step instructions, and offers
  to open the key page in your browser)
- registers autostart and launches Whisproq immediately

**Option B — from source (Python 3.9+):**
Clone/copy this repo and double-click `install.bat`. It creates a venv,
installs the two dependencies, asks for the key, sets autostart and starts
the tool.

## Get a free Groq API key (2 minutes)

1. Open <https://console.groq.com/keys>
2. Sign up / log in (Google account or e-mail, no credit card)
3. **Create API Key** → name it (e.g. "Whisproq") → **Submit**
4. Copy the key (starts with `gsk_…`) — it is shown **only once**!
5. Paste it into the setup — or later: `setx GROQ_API_KEY <key>`
   (picked up immediately, no restart needed)

The same key may be used on several machines (the daily quota is shared).

## Spoken punctuation (German)

Whisper already converts most spoken commands itself. Whisproq additionally
converts any punctuation **words** that survive as text — deterministically,
rule-based, no LLM:

| spoken | becomes |
|---|---|
| „Komma" | `,` |
| „Punkt" | `.` |
| „Fragezeichen" | `?` |
| „Ausrufezeichen" | `!` |
| „Doppelpunkt" / „Semikolon" | `:` / `;` |
| „neue Zeile" / „neuer Absatz" | line break |

Compounds like „Treffpunkt" or „Höhepunkt" are protected by a block list.
Run the test suite with `python punctuation.py` (13 cases).

## Settings

Hold the hotkey → the overlay appears top-right → click **⚙**:

| Setting | Default | Meaning |
|---|---|---|
| Live preview | on | show interim transcript while speaking (costs ~3× quota) |
| Interval (s) | 3 | refresh rate of the preview |
| Hotkey | `f10` | single key or combo: `f4`, `ctrl+space`, `alt+d` … |

Stored in `config.json` next to the program:

```json
{
  "live_preview": true,
  "live_preview_interval_s": 3.0,
  "hotkey": "f10",
  "language": "de"
}
```

### Other languages

`language` is the Whisper language code sent to Groq (`"de"`, `"en"`, …).
The punctuation-**word** conversion only runs for German; for other
languages Whisper's own punctuation is used as-is. PRs that add punctuation
rules for more languages are welcome — see `punctuation.py`.

## Building the Setup EXE

Only needed on a dev machine (the EXE in Releases is prebuilt):

```
install.bat                              # creates venv
venv\Scripts\pip install pyinstaller
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

`build.ps1` runs PyInstaller (onedir), zips the result with Python's
`zipfile` (PowerShell's `Compress-Archive` chokes on tk's tzdata files),
generates the IExpress SED with absolute paths and produces
`Whisproq_Setup.exe` (~25 MB).

## Files

| File | Purpose |
|---|---|
| `whisproq.py` | the tool (hotkey, recording, Groq upload, overlay, paste) |
| `punctuation.py` | German punctuation converter + tests |
| `config.json` | settings (also editable via the ⚙ dialog) |
| `install.bat` / `install.ps1` | source install (venv, key, autostart) |
| `build.ps1` + `build/` | Setup-EXE build (PyInstaller → zip → IExpress) |
| `whisproq.log` | rotating log next to the program |

## Troubleshooting

- **Nothing happens on F10** → check `whisproq.log` (next to the program,
  or `%LOCALAPPDATA%\Whisproq`). Most common cause: missing key →
  `setx GROQ_API_KEY <key>`.
- **Groq error 401/403** → key invalid/rotated → set a new one. (403 with
  a fresh key would mean the User-Agent header was removed — Cloudflare
  blocks Python's default UA.)
- **Text appears twice** → two variants running (EXE **and** venv)? The
  single-instance mutex only guards against double-starting the same one.
- **Remove autostart** → delete value `Whisproq` under
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

---

## Deutsch (Kurzanleitung)

**Diktat per Taste:** In ein Textfeld klicken, **F10 gedrückt halten**,
sprechen, **loslassen** → der Text erscheint nach ~0,5 s im aktiven Feld —
auch in Terminals. Erkennung über Groqs kostenlose Cloud (Whisper
large-v3-turbo, ~2 h Audio/Tag frei), Deutsch voreingestellt.

**Installation:** `Whisproq_Setup.exe` aus den
[Releases](../../releases) doppelklicken (kein Python nötig) — das Setup
fragt den Groq-Key ab (Anleitung inklusive, Key gibt es kostenlos auf
<https://console.groq.com/keys>), trägt den Autostart ein und startet
sofort. Alternativ aus dem Quellcode: `install.bat`.

**Satzzeichen mitdiktieren:** „Komma", „Punkt", „Fragezeichen",
„Ausrufezeichen", „Doppelpunkt", „neue Zeile" — wird nie verdoppelt,
Wörter wie „Treffpunkt" bleiben heil.

**Einstellungen:** Hotkey halten → Overlay oben rechts → **⚙**:
Live-Vorschau an/aus, Intervall (Default 3 s), Hotkey frei wählbar
(auch Kombis wie `ctrl+space`). Gespeichert in `config.json`.

**Bei Problemen:** `whisproq.log` neben dem Programm ansehen — häufigste
Ursache ist ein fehlender Key (`setx GROQ_API_KEY <key>`).
