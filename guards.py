"""Client-seitige Halluzinations-Waechter fuer deutsche Diktate.

Messbefund (tests/test_hallucination.py): Whisper-turbo liefert bei leisem/
verrauschtem Audio selbstbewusst ENGLISCHE Saetze ('No, you kind of.',
'Arbitrating.') — mit gutem avg_logprob (-0,2..-0,7), language='German' in
der Antwort (echot nur den Parameter) und no_speech_prob=0.0 sogar bei
purer Stille. Server-Signale sind also nutzlos; gefiltert wird am TEXT:

  1. avg_logprob < -1.0          -> Muell ('Dopportunates.' -1,20,
                                    ' Ewa, P' -2,23; korrektes lag >= -0,73)
  2. >=2 Buchstaben ausserhalb des dt. Alphabets -> Fremdsprache (Islaendisch)
  3. Prompt-Echo: >=60% der Woerter stammen aus dem Whisper-prompt UND
     mindestens ein GERUESTWORT des Prompts ist dabei ("gesprochene",
     "Satzzeichen", ...) -> Whisper hat bei Fast-Stille den Prompt
     zurueckgelesen. Befehlswoerter allein ("... neuer Absatz") sind
     legitimes Diktat und zaehlen nicht als Echo.
  4. >=2 englische Funktionswoerter UND 0 deutsche -> englischer Satz
  5. "-ing"-Wort (ohne dt. Lehnwoerter) UND 0 deutsche Funktionswoerter

Regelbasiert, deterministisch, kein LLM.
"""
import re

# englische Funktionswoerter, die es im Deutschen NICHT gibt
# (bewusst ohne "in", "was", "so", "her", "will", "man" - alles deutsch!)
_EN_STOP = {
    "the", "you", "your", "it's", "its", "are", "were", "of", "and",
    "this", "that", "these", "those", "what", "how", "why", "who",
    "kind", "just", "have", "has", "had", "would", "could", "should",
    "don't", "can't", "i'm", "they", "we", "but", "not", "no", "yes",
    "there", "here", "with", "from", "about", "because", "very",
}

# deutsche Funktionswoerter — ist eines davon da, ist der Satz wohl deutsch
_DE_STOP = {
    "der", "die", "das", "und", "ist", "ein", "eine", "einen", "nicht",
    "ich", "du", "wir", "ihr", "sie", "es", "mit", "für", "fuer", "auf",
    "zu", "im", "in", "den", "dem", "des", "auch", "bitte", "um", "uhr",
    "am", "an", "bei", "nach", "vor", "über", "ueber", "aber", "oder",
    "wenn", "dass", "was", "wie", "wo", "wer", "noch", "schon", "sehr",
    "morgen", "heute", "gestern", "neue", "neuer", "zeile", "absatz",
    "komma", "punkt", "fragezeichen", "ausrufezeichen",
}

# im Deutschen gebraeuchliche "-ing"-Lehnwoerter
_ING_OK = {
    "meeting", "marketing", "timing", "training", "ranking", "recycling",
    "styling", "casting", "catering", "branding", "leasing", "mobbing",
    "jogging", "shopping", "camping", "doping", "controlling", "consulting",
    "coaching", "banking", "piercing", "peeling", "bowling", "dressing",
    "housing", "factoring", "monitoring", "streaming",
}

_WORD = re.compile(r"[a-zA-Zäöüß']+")

# Satzzeichen-Befehle duerfen im Diktat vorkommen — Prompt-Woerter, die
# NICHT hier stehen, sind Geruestwoerter und verraten ein Prompt-Echo.
_COMMAND_WORDS = {"komma", "punkt", "fragezeichen", "ausrufezeichen",
                  "doppelpunkt", "semikolon", "neue", "neuer", "zeile",
                  "absatz"}


def check(text, worst_logprob=0.0, language="de", prompt=""):
    """(ok, grund) — ok=False heisst: Transkript verwerfen, nicht tippen."""
    if not text:
        return True, ""
    if worst_logprob < -1.0:
        return False, f"avg_logprob {worst_logprob:.2f}"

    low = text.lower()
    words = _WORD.findall(low)
    if prompt and len(words) >= 3:
        pw = set(_WORD.findall(prompt.lower()))
        hits = sum(1 for w in words if w in pw)
        scaffold = sum(1 for w in words
                       if w in pw and w not in _COMMAND_WORDS)
        if hits >= 0.6 * len(words) and scaffold >= 1:
            return False, f"Prompt-Echo ({hits}/{len(words)} Woerter)"
    if not language.startswith("de"):
        return True, ""

    allowed = set("abcdefghijklmnopqrstuvwxyzäöüßéèêàáç")
    bad_chars = {c for c in low if c.isalpha() and c not in allowed}
    if len(bad_chars) >= 2:
        return False, "fremde Zeichen: " + "".join(sorted(bad_chars))
    de_hits = sum(1 for w in words if w in _DE_STOP)
    if de_hits == 0:
        en_hits = sum(1 for w in words if w in _EN_STOP)
        if en_hits >= 2:
            return False, f"englische Funktionswoerter ({en_hits})"
        ing = [w for w in words
               if len(w) >= 6 and w.endswith("ing") and w not in _ING_OK]
        if ing:
            return False, "englisches -ing-Wort: " + ing[0]
    return True, ""


if __name__ == "__main__":
    P = ("Deutsches Diktat. Gesprochene Satzzeichen: Komma, Punkt, "
         "Fragezeichen, Ausrufezeichen, Doppelpunkt, Semikolon, "
         "neue Zeile, neuer Absatz.")
    tests = [
        # (Text, logprob, prompt, erwartet_ok) — Muell = ECHTE Messwerte
        ("Das ist ein deutsches Diktat.", -0.3, P, True),
        ("Neue Zeile", -0.4, P, True),                   # kurz -> kein Echo
        ("Wir treffen uns morgen um zehn Uhr.", -0.3, P, True),
        ("Das Meeting ist um zehn.", -0.4, P, True),     # Lehnwort + deutsch
        ("Beim Jogging war es kalt.", -0.4, P, True),
        ("Hallo Komma bitte bring die Unterlagen mit", -0.4, P, True),
        ("No, you kind of.", -0.55, "", False),          # Test-Reproduktion
        ("No, it's Ailer.", -0.5, P, False),             # Edgars Fall
        ("Arbitrating.", -0.21, P, False),
        ("Harder typing.", -0.73, "", False),
        ("Hún er aðeins í þessu.", -0.5, P, False),      # Islaendisch
        ("Gjörg, neuer Absatz.", -0.4, P, True),         # deutsch genug
        (" Ewa, P", -2.23, P, False),                    # Logprob-Muell
        ("Dopportunates.", -1.20, P, False),             # lag exakt auf -1,2
        ("No, ja, ja.", -1.02, "", False),
        ("Gesprochene Satsang, Doppelpunkt, Semikolon, Neuer Absatz.",
         -0.25, P, False),                               # Prompt-Echo
        ("Vielen Dank.", -0.28, P, True),  # kommt nicht mehr vor (RMS-Gate),
                                           # waere aber harmlos
    ]
    ok = 0
    for text, lp, prm, want in tests:
        got, reason = check(text, lp, "de", prm)
        good = got == want
        ok += good
        print(("PASS" if good else "FAIL"),
              f"| ok={got} ({reason or 'ok'}) | {text!r}")
    print(f"\n{ok}/{len(tests)} bestanden")
