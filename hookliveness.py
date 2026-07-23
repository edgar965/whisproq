#!/usr/bin/env python3
"""Ebene 3: von der keyboard-Lib unabhaengiges Tastatur-Lebenszeichen.

Warum eine EIGENE Low-Level-Hook? Windows entfernt eine WH_KEYBOARD_LL-Hook
STILL, sobald ihre Callback-Prozedur einmal die LowLevelHooksTimeout-Grenze
(Default 300 ms) reisst. Passiert das der keyboard-Lib, kommen bei ihr keine
Tasten mehr an — aber ihr internes `listening`-Flag bleibt True, sie merkt den
Verlust NICHT. Ebene 1/2 sind dann blind: es laeuft nie ein Callback, also
schlaegt weder der Callback-Haenger- (hook_busy) noch der Mikrofon-Open-Detektor
an, der Heartbeat bleibt "healthy" und das Diktat ist trotzdem tot.

Diese Hook macht pro Event fast NICHTS (nur einen monotonen Zeitstempel setzen
und sofort CallNextHookEx) — sie reisst den Timeout also nie und wird von Windows
nie entfernt. Damit ist sie ein verlaesslicher Ist-Zeuge: "es kam real eine
Taste". Der Watchdog vergleicht diesen Zeitstempel mit dem letzten Event, das die
keyboard-Lib ausgeliefert hat: liefern reale Tasten, aber die Lib schweigt, ist
ihre Hook tot und nur ein Prozess-Neustart hilft (ein blosses Neu-Anmelden fuegt
nur einen Callback in denselben toten Listener ein).

Faellt diese Hook selbst aus, friert ihr Zeitstempel ein -> der Watchdog sieht
keine "reale Aktivitaet" mehr und loest NICHTS aus (fail-safe: nie ein
faelschlicher Neustart, nur der Verlust des Sicherheitsnetzes).

Eine WH_KEYBOARD_LL-Hook wird nur bedient, solange der installierende Thread eine
Message-Loop faehrt — daher der eigene Daemon-Thread mit GetMessage-Schleife.
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time

WH_KEYBOARD_LL = 13
HC_ACTION = 0
LRESULT = ctypes.c_ssize_t                              # LONG_PTR (64-bit-sicher)
_HOOKPROC = ctypes.CFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)


class KeyboardLiveness:
    """Unabhaengige WH_KEYBOARD_LL-Hook, die nur den Zeitpunkt der letzten realen
    Taste (monoton) festhaelt. `last_key_ts()` == 0.0 solange noch keine Taste
    kam oder die Hook nicht installiert werden konnte."""

    def __init__(self, log):
        self._log = log
        self._last_ts = 0.0            # monotone Zeit der letzten realen Taste
        self._proc = None             # Referenz halten (sonst GC -> Absturz)
        self._hook = None
        self._thread = None

    def last_key_ts(self):
        return self._last_ts

    def start(self):
        self._thread = threading.Thread(target=self._run,
                                        name="whisproq-liveness", daemon=True)
        self._thread.start()
        return self._thread

    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.SetWindowsHookExW.restype = wt.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC,
                                             wt.HINSTANCE, wt.DWORD]
        user32.CallNextHookEx.restype = LRESULT
        user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int,
                                          wt.WPARAM, wt.LPARAM]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND,
                                       wt.UINT, wt.UINT]
        kernel32.GetModuleHandleW.restype = wt.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]

        def _cb(nCode, wParam, lParam):
            # Minimal halten: nur Zeitstempel, sofort weiterreichen. Kein Logging,
            # keine Allokation im heissen Pfad -> reisst den Timeout nie.
            if nCode == HC_ACTION:
                self._last_ts = time.monotonic()
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._proc = _HOOKPROC(_cb)
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            self._log.warning("Liveness-Hook nicht installiert (Ebene 3 inaktiv "
                              "- kein Netz gegen still entfernte Hook).")
            return
        self._log.info("Ebene 3: Tastatur-Liveness aktiv (unabhaengige Hook)")
        msg = wt.MSG()
        # Blockierende Message-Loop; GetMessage kehrt erst bei WM_QUIT (<=0)
        # zurueck. Daemon-Thread -> stirbt automatisch mit dem Prozess.
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
