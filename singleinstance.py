#!/usr/bin/env python3
r"""Selbstheilende Einzelinstanz fuer Whisproq (Ebene 1).

Frueher verhinderte ein benannter Windows-Mutex den Doppelstart, konnte aber
einen GESUNDEN Halter nicht von einem HAENGENDEN unterscheiden. Hing der
laufende Prozess (Symptom 2026-07-18: der Tastatur-Hook lebte, verarbeitete
aber nichts mehr), hielt er den Mutex weiter — und JEDER Neustart, auch ein
manueller, beendete sich sofort mit ERROR_ALREADY_EXISTS. Der Nutzer war
ausgesperrt, bis er den Zombie von Hand killte oder neu bootete.

Jetzt schreibt die aktive Instanz einen Heartbeat (%LOCALAPPDATA%\Whisproq\
whisproq.pid: PID + Zeitstempel + gesund-Flag) und frischt ihn im Watchdog-Takt
auf. Eine neu startende Instanz liest ihn und entscheidet:
  * frisch UND gesund UND PID lebt -> gesunder Vorgaenger: wir beenden uns
    (Doppelstart bleibt verhindert, wie bisher).
  * veraltet / unhealthy / PID tot -> Vorgaenger haengt: wir raeumen ihn weg
    (TerminateProcess, aber nur wenn es wirklich ein Whisproq-/Python-Prozess
    ist — Schutz vor PID-Recycling) und uebernehmen.
  * Mutex belegt, aber KEIN Heartbeat (alte Version <0.28) -> konservativ
    beenden wie frueher; das Setup killt Vorgaenger ohnehin vor dem Update.
"""
import ctypes
import json
import os
import time

_ERROR_ALREADY_EXISTS = 183
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_TERMINATE = 0x0001


class SingleInstance:
    def __init__(self, mutex_name, pid_path, log, stale_after=20.0):
        self._name = mutex_name
        self._pid_path = pid_path
        self._log = log
        self._stale_after = float(stale_after)
        self._k32 = ctypes.windll.kernel32
        self._handle = None
        self._decl()

    def _decl(self):
        """argtypes/restypes setzen — sonst trunkiert ctypes 64-bit-HANDLES auf
        int und wir arbeiten mit falschen Handles."""
        k = self._k32
        k.CreateMutexW.restype = ctypes.c_void_p
        k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                   ctypes.c_wchar_p]
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        k.QueryFullProcessImageNameW.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_void_p]

    # -- oeffentlich --
    def acquire(self):
        """True  -> wir sind ab jetzt die aktive Instanz (Heartbeat geschrieben).
        False -> ein GESUNDER Vorgaenger laeuft; der Aufrufer soll sich beenden."""
        self._handle = self._k32.CreateMutexW(None, False, self._name)
        if self._k32.GetLastError() != _ERROR_ALREADY_EXISTS:
            self._write_beat(True)                     # wir sind die erste
            return True
        beat = self._read_beat()
        if beat is None:                               # kein Heartbeat: alt/unklar
            self._log.warning("Whisproq laeuft bereits (Mutex belegt, kein "
                              "Heartbeat) - diese Instanz beendet sich.")
            return False
        pid, fresh, healthy = beat
        if fresh and healthy and pid and self._pid_alive(pid):
            self._log.warning("Whisproq laeuft bereits (Heartbeat frisch, "
                              "pid=%s) - diese Instanz beendet sich.", pid)
            return False
        self._log.warning("Vorgaenger wirkt haengend (pid=%s frisch=%s "
                          "gesund=%s) - uebernehme.", pid, fresh, healthy)
        if pid and self._pid_alive(pid):
            self._terminate(pid)
        self._write_beat(True)
        return True

    def beat(self, healthy=True):
        """Heartbeat auffrischen — der Watchdog ruft das im Takt auf."""
        self._write_beat(bool(healthy))

    # -- Heartbeat-Datei --
    def _write_beat(self, healthy):
        try:
            os.makedirs(os.path.dirname(self._pid_path), exist_ok=True)
            tmp = self._pid_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "ts": time.time(),
                           "healthy": healthy}, f)
            os.replace(tmp, self._pid_path)            # atomar
        except OSError as e:
            self._log.warning("Heartbeat nicht schreibbar: %s", e)

    def _read_beat(self):
        """None -> keine Heartbeat-Datei. Sonst (pid, frisch, gesund);
        vorhanden-aber-kaputt gilt als veraltet (uebernehmen)."""
        if not os.path.exists(self._pid_path):
            return None
        try:
            with open(self._pid_path, encoding="utf-8") as f:
                d = json.load(f)
            fresh = (time.time() - float(d.get("ts", 0))) < self._stale_after
            return int(d.get("pid", 0)), fresh, bool(d.get("healthy", True))
        except (OSError, ValueError, TypeError):
            return 0, False, True

    # -- Prozess-Helfer --
    def _pid_alive(self, pid):
        h = self._k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False,
                                  int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if self._k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == _STILL_ACTIVE
            return True
        finally:
            self._k32.CloseHandle(h)

    def _is_whisproq(self, pid):
        """Schutz vor PID-Recycling: nur beenden, wenn das Prozessabbild
        wirklich nach Whisproq/Python aussieht."""
        h = self._k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False,
                                  int(pid))
        if not h:
            return False
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if not self._k32.QueryFullProcessImageNameW(h, 0, buf,
                                                        ctypes.byref(size)):
                return False
            name = os.path.basename(buf.value).lower()
            # "whisproq" trifft die produktive EXE (Whisproq.exe); "python*"
            # jede venv-/Dev-Variante (python.exe, pythonw.exe, python3.14t.exe).
            return "whisproq" in name or name.startswith("python")
        finally:
            self._k32.CloseHandle(h)

    def _terminate(self, pid):
        if not self._is_whisproq(pid):
            self._log.warning("PID %s ist kein Whisproq/Python-Prozess - nicht "
                              "beendet (PID-Recycling?).", pid)
            return
        h = self._k32.OpenProcess(_PROCESS_TERMINATE, False, int(pid))
        if not h:
            self._log.warning("Vorgaenger-PID %s nicht oeffenbar.", pid)
            return
        try:
            if self._k32.TerminateProcess(h, 1):
                self._log.warning("Haengenden Vorgaenger (PID %s) beendet.", pid)
                self._k32.WaitForSingleObject(h, 3000)  # bis Handle/Mutex frei
            else:
                self._log.warning("TerminateProcess(%s) fehlgeschlagen.", pid)
        finally:
            self._k32.CloseHandle(h)
