"""Deterministische Behandlung diktierter Satzzeichen (Deutsch).

Groqs Whisper (large-v3-turbo) setzt Satzzeichen selbst gut — inklusive der
Umwandlung gesprochener Befehle ("Fragezeichen" -> "?"). Deshalb gilt:

  1. Whispers Satzzeichen BLEIBEN erhalten (nichts wird gestrippt).
  2. Bleibt ein Satzzeichen-Wort als WORT stehen ("Punkt", "Komma",
     "Testfragezeichen" verklebt), wird es zusaetzlich in das Symbol
     umgewandelt.
  3. Haengt am Wort davor schon ein Satzzeichen ("Hause." + "Punkt"),
     wird es ERSETZT statt verdoppelt (nie "..").

Fuer "-punkt" gibt es eine Kompositum-Blockliste, damit "Treffpunkt",
"Standpunkt" usw. NICHT zerlegt werden. Regelbasiert - kein LLM.
"""
import re

_SYMBOL = {
    "komma": ",",
    "punkt": ".",
    "fragezeichen": "?",
    "ausrufezeichen": "!",
    "rufzeichen": "!",
    "doppelpunkt": ":",
    "semikolon": ";",
    "strichpunkt": ";",
}

# Reihenfolge: laengere zuerst (doppelpunkt vor punkt!), damit nicht "punkt"
# faelschlich in "doppelpunkt" matcht.
_SUFFIXES = ["ausrufezeichen", "fragezeichen", "rufzeichen", "doppelpunkt",
             "semikolon", "strichpunkt", "komma", "punkt"]

# echte Woerter auf "-punkt" (kein Satzzeichen)
_PUNKT_COMPOUNDS = {
    "treffpunkt", "standpunkt", "hoehepunkt", "höhepunkt", "zeitpunkt",
    "mittelpunkt", "schwerpunkt", "stuetzpunkt", "stützpunkt", "blickpunkt",
    "gesichtspunkt", "knotenpunkt", "wendepunkt", "endpunkt", "ausgangspunkt",
    "haltepunkt", "brennpunkt", "fixpunkt", "nullpunkt", "tiefpunkt",
    "streitpunkt", "kritikpunkt", "gefrierpunkt", "siedepunkt", "drehpunkt",
    "aussichtspunkt", "sammelpunkt", "kontrollpunkt", "zielpunkt",
    "tagesordnungspunkt", "eckpunkt", "ruhepunkt", "weltpunkt",
}

_PUNCT_CHARS = ".,!?;:…"


def _attach(out, sym):
    """Symbol an das vorige Wort haengen; vorhandenes Satzzeichen dort wird
    ERSETZT (Whisper "Hause." + gesprochenes "Punkt" -> "Hause.", nie "..")."""
    if out and out[-1]:
        out[-1] = out[-1].rstrip().rstrip(_PUNCT_CHARS) + sym
    else:
        out.append(sym.lstrip())


def convert(text):
    if not text or not text.strip():
        return text

    text = re.sub(r'\bneue[rs]?\s+(zeile|absatz|abschnitt)\b', '\n', text,
                  flags=re.IGNORECASE)

    # Whisper reisst Satzzeichen-Woerter manchmal auseinander
    # ("Frage Zeichen") -> vor der Tokenisierung wieder zusammenkleben.
    text = re.sub(r'\b(frage|ausrufe|ruf)\s+zeichen\b',
                  lambda m: m.group(1) + 'zeichen', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(doppel|strich)\s+punkt\b',
                  lambda m: m.group(1) + 'punkt', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsemi\s+kolon\b', 'semikolon', text, flags=re.IGNORECASE)

    out = []
    for tok in text.split(' '):
        core = tok.strip(_PUNCT_CHARS)
        low = core.lower()
        if not core:
            out.append(tok)
            continue
        # 1) eigenstaendiges Satzzeichen-Wort ("Punkt", "Fragezeichen?")
        if low in _SYMBOL:
            _attach(out, _SYMBOL[low])
            continue
        # 2) verklebtes Satzzeichen-Wort als Suffix ("Testfragezeichen")
        hit = None
        for suf in _SUFFIXES:
            if low.endswith(suf) and len(low) > len(suf):
                if suf == "punkt" and low in _PUNKT_COMPOUNDS:
                    break                      # echtes Kompositum -> nicht zerlegen
                hit = suf
                break
        if hit:
            out.append(core[:len(core) - len(hit)])   # Praefix (Gross/klein bleibt)
            _attach(out, _SYMBOL[hit])
        else:
            out.append(tok)                    # Whisper-Satzzeichen bleiben dran

    result = ' '.join(out)
    result = re.sub(r'\s+([,.!?;:])', r'\1', result)
    result = re.sub(r'[ \t]{2,}', ' ', result)
    result = re.sub(r'[ \t]*\n[ \t]*', '\n', result)
    result = re.sub(r'([.!?]\s+|\n)([a-zäöüß])',
                    lambda m: m.group(1) + m.group(2).upper(), result)
    result = re.sub(r'^(\s*)([a-zäöüß])',
                    lambda m: m.group(1) + m.group(2).upper(), result)
    return result


if __name__ == "__main__":
    tests = [
        # Whisper-Satzzeichen bleiben erhalten (Groq setzt sie korrekt):
        ("Meinst du, dass das alles noch funktionieren wird?",
         "Meinst du, dass das alles noch funktionieren wird?"),
        ("Ist das ein guter Test?", "Ist das ein guter Test?"),
        ("Das ist ein deutsches Diktat.", "Das ist ein deutsches Diktat."),
        # diktierte Woerter werden (zusaetzlich) umgewandelt:
        ("Das ist ein Test Fragezeichen", "Das ist ein Test?"),
        ("Ist das ein Testfragezeichen?", "Ist das ein Test?"),      # verklebt
        ("Hallo Komma bitte bring die Unterlagen mit Fragezeichen",
         "Hallo, bitte bring die Unterlagen mit?"),
        ("das ist gut Ausrufezeichen und du Fragezeichen",
         "Das ist gut! Und du?"),
        # Wort + Whisper-Symbol kollidieren -> ersetzen, nie doppeln:
        ("Ich bin jetzt zu Hause. Punkt", "Ich bin jetzt zu Hause."),
        ("Ich bin zu Hause, Komma und du", "Ich bin zu Hause, und du"),
        # Komposita bleiben heil:
        ("wir treffen uns am Treffpunkt Komma wie besprochen Punkt",
         "Wir treffen uns am Treffpunkt, wie besprochen."),
        ("das war der Hoehepunkt Punkt", "Das war der Hoehepunkt."),
        # Zeilenumbruch + Zahlen:
        ("erste Zeile neue Zeile zweite Zeile Punkt",
         "Erste Zeile\nZweite Zeile."),
        ("Wir kommen um 10.000 Uhr Punkt", "Wir kommen um 10.000 Uhr."),
        # auseinandergerissene Satzzeichen-Woerter:
        ("Kommst du morgen Frage Zeichen", "Kommst du morgen?"),
        ("Achtung Ausrufe Zeichen", "Achtung!"),
        ("Es gilt Doppel Punkt sofort anfangen Punkt",
         "Es gilt: sofort anfangen."),
    ]
    ok = 0
    for inp, exp in tests:
        got = convert(inp)
        good = got == exp
        ok += good
        print(("PASS" if good else "FAIL"), "|", repr(inp))
        if not good:
            print("     erwartet:", repr(exp))
            print("     bekommen:", repr(got))
    print(f"\n{ok}/{len(tests)} bestanden")
