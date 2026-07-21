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
                 hook_busy_since, restart, interval=5.0, stuck_after=8.0):
        self._log = log
        self._heartbeat = heartbeat            # callable(healthy: bool)
        self._is_hotkey_ok = is_hotkey_ok      # callable() -> bool
        self._reinstall = reinstall            # callable() (Hotkey neu anmelden)
        self._hook_busy_since = hook_busy_since  # callable() -> float (0=frei)
        self._restart = restart                # callable() (frische Instanz spawnen)
        self._interval = float(interval)
        self._stuck_after = float(stuck_after)

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
        busy = self._hook_busy_since()
        if busy and (time.monotonic() - busy) > self._stuck_after:
            # processing_thread haengt in einem Callback -> nicht heilbar.
            self._log.error("Watchdog: Hotkey-Callback haengt seit %.0fs - "
                            "Neustart.", time.monotonic() - busy)
            self._heartbeat(False)                     # manueller Neustart darf ran
            self._reexec()
            return
        if not self._is_hotkey_ok():
            self._log.warning("Watchdog: Hotkey-Registrierung weg - neu anmelden.")
            try:
                self._reinstall()
            except Exception as e:                     # noqa: BLE001
                self._log.error("Watchdog: Neuanmeldung fehlgeschlagen: %s", e)
        self._heartbeat(True)

    def _reexec(self):
        try:
            self._restart()                            # frische Instanz starten
            self._log.error("Watchdog: frische Instanz gestartet, beende diese.")
        except Exception as e:                         # noqa: BLE001
            self._log.error("Watchdog: Neustart fehlgeschlagen: %s", e)
        finally:
            os._exit(1)                                # harter Abgang der haengenden
