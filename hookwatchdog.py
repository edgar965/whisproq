#!/usr/bin/env python3
"""Watchdog fuer die Tastatur-Hook-Kette (Ebene 2).

Die keyboard-Lib ruft ihre Callbacks in einem EIGENEN processing_thread auf
(nicht im OS-Hook-Thread): der OS-Hook enqueued nur, ein zweiter Thread
verarbeitet die Queue und ruft unsere Handler. Blockiert ein Handler dort,
staut die Queue und KEIN Hotkey wird mehr verarbeitet — das Diktat ist tot,
der Prozess lebt aber weiter. Ein blosses keyboard.hook()-Neuinstallieren
HILFT dann NICHT: der neue Handler landet in derselben, blockierten Queue.

Darum zwei Stufen:
  1. Guenstige Heilung: fehlt der keyboard-Listener oder unsere PTT-
     Registrierung, den Hotkey neu anmelden (z.B. falls die Registrierung
     verloren ging). Behebt den haeufigen, harmlosen Fall.
  2. Harte Heilung: haengt ein Handler laenger als `stuck_after` im Callback,
     ist der processing_thread nicht mehr zu retten -> Prozess NEU STARTEN
     (re-exec, nicht bloss beenden — Autostart feuert nur beim Login). Die
     frische Instanz uebernimmt via SingleInstance und raeumt diese haengende
     weg.

Zusaetzlich frischt der Watchdog im Takt den Heartbeat auf (Datenquelle fuer
SingleInstance/Ebene 1). Erkennt er einen Haenger, schreibt er den Heartbeat
als UNHEALTHY, damit auch ein manueller Neustart sofort uebernehmen darf.
"""
import os
import threading
import time


class HookWatchdog:
    def __init__(self, log, *, heartbeat, is_hotkey_ok, reinstall,
                 hook_busy_since, restart, open_stuck_since=None,
                 interval=5.0, stuck_after=8.0, open_stuck_after=15.0):
        self._log = log
        self._heartbeat = heartbeat            # callable(healthy: bool)
        self._is_hotkey_ok = is_hotkey_ok      # callable() -> bool
        self._reinstall = reinstall            # callable() (Hotkey neu anmelden)
        self._hook_busy_since = hook_busy_since  # callable() -> float (0=frei)
        self._open_stuck_since = open_stuck_since  # callable()->float | None
        self._restart = restart                # callable() (frische Instanz spawnen)
        self._interval = float(interval)
        self._stuck_after = float(stuck_after)
        self._open_stuck_after = float(open_stuck_after)

    def start(self):
        t = threading.Thread(target=self._loop, name="whisproq-watchdog",
                             daemon=True)
        t.start()
        return t

    def _loop(self):
        while True:
            time.sleep(self._interval)
            try:
                self._tick()
            except Exception as e:                     # noqa: BLE001
                self._log.warning("Watchdog-Fehler: %s", e)

    def _tick(self):
        stuck = self._stuck_reason()
        if stuck:
            # Weder ein haengender Callback (processing_thread) noch ein
            # haengender Mikrofon-Open (Worker) ist im laufenden Prozess zu
            # retten -> Neustart. Heartbeat vorher UNHEALTHY, damit auch ein
            # manueller Neustart sofort uebernehmen darf (Ebene 1).
            self._log.error("Watchdog: %s - Neustart.", stuck)
            self._heartbeat(False)
            self._reexec()
            return
        if not self._is_hotkey_ok():
            self._log.warning("Watchdog: Hotkey-Registrierung weg - neu anmelden.")
            try:
                self._reinstall()
            except Exception as e:                     # noqa: BLE001
                self._log.error("Watchdog: Neuanmeldung fehlgeschlagen: %s", e)
        self._heartbeat(True)

    def _stuck_reason(self):
        """Grund fuer einen unheilbaren Haenger (str) oder None. Zwei Quellen:
        (1) ein Hotkey-Callback laeuft zu lange (on_evt blockiert), (2) ein
        Mikrofon-Open steckt fest (Worker haengt in RawInputStream.start() —
        typisch nach S0ix-Resume). Fall (2) fehlte v0.28 komplett."""
        now = time.monotonic()
        busy = self._hook_busy_since()
        if busy and (now - busy) > self._stuck_after:
            return "Hotkey-Callback haengt seit %.0fs" % (now - busy)
        if self._open_stuck_since is not None:
            op = self._open_stuck_since()
            if op and (now - op) > self._open_stuck_after:
                return "Mikrofon-Open haengt seit %.0fs" % (now - op)
        return None

    def _reexec(self):
        try:
            self._restart()                            # frische Instanz starten
            self._log.error("Watchdog: frische Instanz gestartet, beende diese.")
        except Exception as e:                         # noqa: BLE001
            self._log.error("Watchdog: Neustart fehlgeschlagen: %s", e)
        finally:
            os._exit(1)                                # harter Abgang der haengenden
