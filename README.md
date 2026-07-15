# Whisproq 🎙️

**Push-to-talk dictation for Windows** — hold a hotkey (default **F10**),
speak, release: the text appears in the **active text field** ~0.5 s later.
Works system-wide: Word, browsers, WhatsApp, even terminals and CLI tools.

The name says it all: **Whis**per + G**roq**. Transcription runs on Groq's
free cloud API using OpenAI's `whisper-large-v3-turbo` — no local models,
no GPU, no build step. The free quota is measured in audio time
(up to 8 h of audio per day), not in words.

## Features

- **Types into whatever has focus** — Word, browser, WhatsApp, terminals
  and CLI tools; clipboard-based paste (umlaut-safe) with typing fallback
- **Configurable hotkey** (default **F10**): single key or combos like
  `ctrl+space`, changeable at runtime via the gear dialog ⚙ — no restart
- **Guided Groq key setup**: the installer asks for the free API key with
  step-by-step instructions and opens the key page in your browser on
  request; later the key can be **changed in the gear dialog ⚙** — it is
  re-read on every keypress, so changes take effect without restarting
- **Autostart built in**: asked once at install, preserved across updates
- **No Python environment needed**: the Setup EXE is fully self-contained —
  no interpreter, no local models, no GPU, no build step, ~50 MB RAM
- **Free tier that fits dictation**: Groq's free quota for
  `whisper-large-v3-turbo` is a **time** quota, not a word limit —
  28,800 audio-seconds/day (≈ up to **8 h of audio daily**; further
  limits: 7,200 audio-seconds/hour, 20 requests/min, 2,000/day — see
  [Groq's rate-limit docs](https://console.groq.com/docs/rate-limits));
  no credit card required
- **Fast**: the text lands ~0.5 s after releasing the key
  (whisper-large-v3-turbo on Groq's cloud)
- **Spoken punctuation (German)**: „Komma", „Punkt", „Fragezeichen",
  „neue Zeile" … converted deterministically — never doubled (if Whisper
  already emitted `.`, a spoken „Punkt" won't add a second one), and
  compounds like „Treffpunkt" stay intact
- **Hallucination guards**: too-quiet or garbled recordings are rejected
  with a „Nicht verstanden" overlay instead of typing foreign-language
  nonsense into your document
- **Live preview** (optional): an overlay shows the transcript *while* you
  speak, refreshed every few seconds
- **Clean install lifecycle**: appears under Windows **Installed Apps**,
  uninstalls cleanly, and updating = just run the setup again (asks
  nothing, keeps your settings)
- **Small & hackable**: two dependencies (`keyboard`, `sounddevice`),
  audio + HTTP via the Python standard library, single-instance guard,
  rotating log + `last_utterance.wav` for diagnosis, MIT license

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
| Groq API key | — | change/rotate the key right here (masked field; stored in the user environment, empty = keep current) |

Defaults live in the code; a fresh installation has **no** `config.json`.
The file is created in `%LOCALAPPDATA%\Whisproq\config.json` the first
time you save something in the gear dialog — so updates can never
overwrite a real decision. (The `config.json` in the repo is a
documented example for the source/venv variant.) All keys:

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
| `config.json` | defaults example (your settings: `%LOCALAPPDATA%\Whisproq\config.json`, created on first ⚙-save) |
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
large-v3-turbo, bis zu 8 h Audio/Tag frei), Deutsch voreingestellt.

**Vorteile auf einen Blick:** Hotkey frei konfigurierbar (Default F10,
auch Kombis, ohne Neustart) · geführtes Setzen des Groq-Keys im Setup,
**änderbar jederzeit im Zahnrad-Dialog ⚙** · Autostart
eingebaut · **keine Python-Umgebung nötig** (Setup-EXE ist eigenständig,
keine lokalen Modelle, keine GPU) · kostenlos mit großzügigem
Zeit-Kontingent (bis zu 8 h Audio/Tag, kein Wort-Limit) ·
diktierte deutsche Satzzeichen · Halluzinations-Wächter statt
Kauderwelsch im Text · erscheint unter „Installierte Apps" und ist
sauber deinstallierbar · Updates fragen nichts und erhalten die
Einstellungen.

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
(auch Kombis wie `ctrl+space`), **Groq-API-Key ändern**. Gespeichert in
`%LOCALAPPDATA%\Whisproq\config.json` (der Key in der User-Umgebung).

**Bei Problemen:** `whisproq.log` neben dem Programm ansehen — häufigste
Ursache ist ein fehlender Key (`setx GROQ_API_KEY <key>`).
