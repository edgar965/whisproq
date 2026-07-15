r"""Reproduziert die Fremdsprachen-Halluzinationen des deutschen Diktats.

Vorher einmal:  powershell -File make_audio.ps1   (erzeugt tts_*.wav)
Dann:           ..\venv\Scripts\python.exe test_hallucination.py

Jagt jedes TTS-Audio in 3 Qualitaetsstufen (sauber / leise+Rauschen /
sehr leise+Rauschen) plus Stille und reines Rauschen A/B durch die
Groq-API — einmal MIT dem Whisper-prompt des Tools, einmal OHNE.
Bewertet jede Antwort mit guards.check() (dieselbe Logik wie im Tool)
und zaehlt, ob fremdsprachiger Muell durchrutscht. Kostet ~30 kurze
Gratis-Requests; zwischen den Aufrufen wird pausiert (Rate-Limit).
"""
import io
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from array import array

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import guards                                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
SR = 16000
PROMPT = ("Deutsches Diktat. Gesprochene Satzzeichen: Komma, Punkt, "
          "Fragezeichen, Ausrufezeichen, Doppelpunkt, Semikolon, "
          "neue Zeile, neuer Absatz.")


def read_key():
    k = os.environ.get("GROQ_API_KEY", "")
    if k:
        return k
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
        return winreg.QueryValueEx(reg, "GROQ_API_KEY")[0]


KEY = read_key()


def wav_bytes(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return buf.getvalue()


def load_pcm(path):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return w.readframes(w.getnframes())


def degrade(pcm, gain, noise_sigma, seed=42):
    """Fernfeld-Simulation: leiser + weisses Rauschen (deterministisch)."""
    rng = random.Random(seed)
    a = array("h", pcm)
    out = array("h", (max(-32768, min(32767,
                int(x * gain + rng.gauss(0, noise_sigma)))) for x in a))
    return out.tobytes()


def rms(pcm):
    a = array("h", pcm)
    return (sum(x * x for x in a) / max(len(a), 1)) ** 0.5


def groq(pcm, with_prompt):
    boundary = "----whisproqtest" + uuid.uuid4().hex
    nl = b"\r\n"

    def part(name, value):
        return (b"--" + boundary.encode() + nl
                + f'Content-Disposition: form-data; name="{name}"'.encode()
                + nl + nl + value.encode() + nl)

    body = (part("model", "whisper-large-v3-turbo")
            + part("language", "de")
            + part("temperature", "0")
            + part("response_format", "verbose_json")
            + (part("prompt", PROMPT) if with_prompt else b"")
            + b"--" + boundary.encode() + nl
            + b'Content-Disposition: form-data; name="file"; '
              b'filename="audio.wav"' + nl
            + b"Content-Type: audio/wav" + nl + nl
            + wav_bytes(pcm) + nl
            + b"--" + boundary.encode() + b"--" + nl)
    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Authorization": "Bearer " + KEY,
                 "Content-Type": "multipart/form-data; boundary=" + boundary,
                 "User-Agent": "whisproq-test/0.1"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                print("   (429 - warte 65 s ...)")
                time.sleep(65)
            else:
                raise
    text = (d.get("text") or "").strip()
    segs = d.get("segments") or []
    worst = min((s.get("avg_logprob", 0.0) for s in segs), default=0.0)
    return d.get("language"), text, worst


def main():
    cases = []
    for name in ("neue_zeile", "fragezeichen", "test_fragezeichen",
                 "neuer_absatz", "normaler_satz"):
        p = os.path.join(HERE, f"tts_{name}.wav")
        if not os.path.exists(p):
            sys.exit(f"FEHLT: {p} - erst make_audio.ps1 ausfuehren")
        pcm = load_pcm(p)
        cases.append((f"{name}/sauber", pcm))
        cases.append((f"{name}/leise+rauschen", degrade(pcm, 0.10, 120)))
        cases.append((f"{name}/sehr-leise+rauschen", degrade(pcm, 0.03, 150)))
    cases.append(("stille", b"\x00\x00" * (SR + SR // 2)))
    rng = random.Random(7)
    cases.append(("nur-rauschen",
                  array("h", (int(rng.gauss(0, 200))
                              for _ in range(SR * 2))).tobytes()))

    bad_typed = 0
    for label, pcm in cases:
        print(f"\n=== {label}  (RMS {rms(pcm):.0f}) ===")
        for wp in (True, False):
            try:
                lang, text, worst = groq(pcm, wp)
            except Exception as e:
                print(f"  prompt={int(wp)}: FEHLER {e}")
                continue
            ok, reason = guards.check(text, worst, "de",
                                      PROMPT if wp else "")
            mark = f"verworfen ({reason})" if not ok else "GETIPPT"
            # englischer/fremder Text, den die Waechter NICHT stoppen:
            if ok and text:
                en = sum(1 for w in text.lower().split()
                         if w.strip(".,!?") in guards._EN_STOP)
                if en >= 2:
                    mark += "  <-- FREMDSPRACHE KOMMT DURCH!"
                    bad_typed += 1
            print(f"  prompt={int(wp)}: lang={lang!r:10} logprob={worst:6.2f} "
                  f"{mark}: {text!r}")
            time.sleep(2.5)                            # Rate-Limit schonen
    print(f"\nDurchgerutschte Fremdsprachen-Ausgaben: {bad_typed}")
    sys.exit(1 if bad_typed else 0)


if __name__ == "__main__":
    main()
