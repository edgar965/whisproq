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
Double-click **`Install/Whisproq_Setup.exe`** — it ships right in the repo
(also attached to the [Releases](../../releases)). The setup

- installs to `%LOCALAPPDATA%\Whisproq` and registers Whisproq in
  Windows' installed apps (uninstall via Settings → Apps)
- asks for your `GROQ_API_KEY` (with step-by-step instructions, and offers
  to open the key page in your browser)
- asks whether Whisproq should start with Windows, then launches it
- **updates**: run the same EXE again — an existing installation is
  detected, nothing is asked, key and autostart choice are kept

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
| Live preview | off | show interim transcript while speaking (costs ~3× quota) |
| Interval (s) | 3 | refresh rate of the preview |
| Hotkey | `f10` | single key or combo: `f4`, `ctrl+space`, `alt+d` … |

Your settings are stored in `%LOCALAPPDATA%\Whisproq\config.json` — the
`config.json` in the program folder / repo only provides the defaults and
is never written to:

```json
{
  "live_preview": false,
  "live_preview_interval_s": 3.0,
  "hotkey": "f10",
  "language": "de",
  "prompt": "Deutsches Diktat. Gesprochene Satzzeichen: Komma, Punkt, ..."
}
```

`prompt` (default **empty**) is sent to Whisper as recognition context.
In field testing a punctuation-word prompt made some microphones flip
whole utterances into foreign languages, so it ships disabled — treat it
as an experimental knob. The last recording is kept as
`last_utterance.wav` next to the log for evidence-based debugging.

### Other languages

`language` is the Whisper language code sent to Groq (`"de"`, `"en"`, …).
The punctuation-**word** conversion only runs for German; for other
languages Whisper's own punctuation is used as-is. PRs that add punctuation
rules for more languages are welcome — see `punctuation.py`.

## Building the Setup EXE

Only needed on a dev machine (`Install/Whisproq_Setup.exe` is prebuilt):

```
install.bat                              # creates venv
venv\Scripts\pip install pyinstaller
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

`build.ps1` runs PyInstaller (onedir), zips the result with Python's
`zipfile` (PowerShell's `Compress-Archive` chokes on tk's tzdata files),
generates the IExpress SED with absolute paths and produces
`Install/Whisproq_Setup.exe` (~13 MB).

## Files

| File | Purpose |
|---|---|
| `Install/Whisproq_Setup.exe` | **the distributable setup** (one file, no Python needed) |
| `whisproq.py` | the tool (hotkey, recording, Groq upload, overlay, paste) |
| `punctuation.py` | German punctuation converter + tests |
| `config.json` | default settings (your own live in `%LOCALAPPDATA%\Whisproq`) |
| `install.bat` / `install.ps1` | source install (venv, key, autostart) |
| `uninstall.ps1` | uninstaller (also reachable via Windows Settings → Apps) |
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
- **Spoken punctuation words get garbled** („Fragezeichen" → fantasy word)
  → that's microphone quality; the built-in `prompt` biasing helps a lot,
  a close-talking microphone helps most. Split forms („Frage Zeichen")
  are re-joined automatically.
- **Uninstall** → Windows Settings → Apps → Whisproq (or run
  `uninstall.ps1`). Removes program, autostart and registry entries.
- **Remove autostart only** → delete value `Whisproq` under
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

---

## Deutsch (Kurzanleitung)

**Diktat per Taste:** In ein Textfeld klicken, **F10 gedrückt halten**,
sprechen, **loslassen** → der Text erscheint nach ~0,5 s im aktiven Feld —
auch in Terminals. Erkennung über Groqs kostenlose Cloud (Whisper
large-v3-turbo, ~2 h Audio/Tag frei), Deutsch voreingestellt.

**Installation:** `Install\Whisproq_Setup.exe` doppelklicken (liegt direkt
im Repo, kein Python nötig) — das Setup fragt den Groq-Key ab (Anleitung
inklusive, Key gibt es kostenlos auf <https://console.groq.com/keys>),
fragt, ob Whisproq in den Autostart soll, und startet sofort. Whisproq
erscheint unter Windows-Einstellungen → Apps und ist dort deinstallierbar.
**Update:** dieselbe EXE einfach erneut ausführen — bestehende Installation
wird erkannt, es wird nichts erneut gefragt. Alternativ aus dem Quellcode:
`install.bat`.

**Satzzeichen mitdiktieren:** „Komma", „Punkt", „Fragezeichen",
„Ausrufezeichen", „Doppelpunkt", „neue Zeile" — wird nie verdoppelt,
Wörter wie „Treffpunkt" bleiben heil.

**Einstellungen:** Hotkey halten → Overlay oben rechts → **⚙**:
Live-Vorschau an/aus, Intervall (Default 3 s), Hotkey frei wählbar
(auch Kombis wie `ctrl+space`). Gespeichert in
`%LOCALAPPDATA%\Whisproq\config.json`.

**Bei Problemen:** `whisproq.log` neben dem Programm ansehen — häufigste
Ursache ist ein fehlender Key (`setx GROQ_API_KEY <key>`).
