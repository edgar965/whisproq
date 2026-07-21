r"""Deterministischer Test der Selbstheilung (Ebene 1 + 2) ohne echte Instanz:
  * SingleInstance.acquire() — die vier Entscheidungszweige (erste Instanz /
    gesunder Vorgaenger / haengender Vorgaenger / kein Heartbeat).
  * SingleInstance._read_beat() — fehlt / kaputt / gueltig.
  * HookWatchdog._tick() — gesund / Registrierung weg / Callback haengt
    (der harte Neustart wird abgefangen, damit der Testlauf nicht stirbt).
Ausfuehren: ..\venv\Scripts\python.exe tests\test_resilience.py
"""
import ctypes
import json
import os
import sys
import time

sys.path.insert(0, r"A:\repos\Whisproq")
from singleinstance import SingleInstance            # noqa: E402
from hookwatchdog import HookWatchdog                # noqa: E402

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_beat_tmp")
os.makedirs(_TMP, exist_ok=True)
_k32 = ctypes.windll.kernel32
_held = []                                           # gehaltene Test-Mutex-Handles
results = []


class _Log:                                          # stiller Logger-Ersatz
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def info(self, *a, **k): pass


def check(name, ok):
    print(f"[{'OK ' if ok else 'FAIL'}] {name}")
    results.append(bool(ok))


def _hold_mutex(name):
    """Belegt den benannten Mutex im Testprozess (haelt Handle) -> die
    folgende acquire() sieht ERROR_ALREADY_EXISTS."""
    _held.append(_k32.CreateMutexW(None, False, name))


def _write_beat(path, pid, ts, healthy):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pid": pid, "ts": ts, "healthy": healthy}, f)


def _pid_path(tag):
    return os.path.join(_TMP, f"beat_{tag}.pid")


# 1) Erste Instanz: frischer, einzigartiger Mutex -> True + Heartbeat da
p = _pid_path("fresh")
if os.path.exists(p):
    os.remove(p)
si = SingleInstance("Whisproq_Test_Fresh", p, _Log())
check("erste Instanz -> acquire True", si.acquire() is True)
check("erste Instanz schreibt Heartbeat", os.path.exists(p))

# 2) Gesunder Vorgaenger: Mutex belegt + frischer, gesunder Heartbeat mit
#    lebender PID (wir selbst) -> acquire False (Doppelstart verhindert)
p = _pid_path("healthy")
_write_beat(p, os.getpid(), time.time(), True)
_hold_mutex("Whisproq_Test_Healthy")
si = SingleInstance("Whisproq_Test_Healthy", p, _Log())
check("gesunder Vorgaenger -> acquire False", si.acquire() is False)

# 3) Haengender Vorgaenger: Mutex belegt + VERALTETER Heartbeat (pid=0, damit
#    nichts wirklich gekillt wird) -> acquire True (uebernehmen)
p = _pid_path("stale")
_write_beat(p, 0, time.time() - 999, True)
_hold_mutex("Whisproq_Test_Stale")
si = SingleInstance("Whisproq_Test_Stale", p, _Log())
check("haengender Vorgaenger -> acquire True", si.acquire() is True)

# 3b) unhealthy-Flag alleine (Heartbeat frisch, aber healthy=False) -> uebernehmen
p = _pid_path("unhealthy")
_write_beat(p, 0, time.time(), False)
_hold_mutex("Whisproq_Test_Unhealthy")
si = SingleInstance("Whisproq_Test_Unhealthy", p, _Log())
check("unhealthy-Vorgaenger -> acquire True", si.acquire() is True)

# 4) Mutex belegt, aber KEIN Heartbeat (alte Version) -> konservativ False
p = _pid_path("noheartbeat")
if os.path.exists(p):
    os.remove(p)
_hold_mutex("Whisproq_Test_NoBeat")
si = SingleInstance("Whisproq_Test_NoBeat", p, _Log())
check("kein Heartbeat -> acquire False (konservativ)", si.acquire() is False)

# 5) _read_beat: fehlt / kaputt / gueltig
si = SingleInstance("Whisproq_Test_Read", _pid_path("missing"), _Log())
check("_read_beat fehlend -> None", si._read_beat() is None)
p = _pid_path("corrupt")
with open(p, "w", encoding="utf-8") as f:
    f.write("{kaputt")
si = SingleInstance("Whisproq_Test_Read2", p, _Log())
check("_read_beat kaputt -> nicht frisch", si._read_beat() == (0, False, True))
check("_is_whisproq(self) -> True (python.exe)", si._is_whisproq(os.getpid()))

# 6) HookWatchdog._tick — Neustart abfangen, damit os._exit den Test nicht killt
class _Spy(HookWatchdog):
    reexec_called = False

    def _reexec(self):
        _Spy.reexec_called = True                    # KEIN os._exit im Test


state = {"beats": [], "reinstalled": 0}


def make(busy, hotkey_ok):
    _Spy.reexec_called = False
    state["beats"] = []
    state["reinstalled"] = 0
    return _Spy(
        _Log(),
        heartbeat=lambda h: state["beats"].append(h),
        is_hotkey_ok=lambda: hotkey_ok,
        reinstall=lambda: state.__setitem__("reinstalled",
                                            state["reinstalled"] + 1),
        hook_busy_since=lambda: busy,
        restart=lambda: None,
        stuck_after=8.0,
    )


# gesund: kein Neustart, keine Neuanmeldung, Heartbeat healthy=True
w = make(busy=0.0, hotkey_ok=True)
w._tick()
check("Watchdog gesund -> kein re-exec", not _Spy.reexec_called)
check("Watchdog gesund -> Heartbeat True", state["beats"] == [True])
check("Watchdog gesund -> keine Neuanmeldung", state["reinstalled"] == 0)

# Registrierung weg: Neuanmeldung + Heartbeat True, kein Neustart
w = make(busy=0.0, hotkey_ok=False)
w._tick()
check("Watchdog Reg weg -> Neuanmeldung", state["reinstalled"] == 1)
check("Watchdog Reg weg -> kein re-exec", not _Spy.reexec_called)

# Callback haengt (busy weit in der Vergangenheit): re-exec + Heartbeat False
w = make(busy=time.monotonic() - 20, hotkey_ok=True)
w._tick()
check("Watchdog Haenger -> re-exec", _Spy.reexec_called)
check("Watchdog Haenger -> Heartbeat False", state["beats"] == [False])

# frischer Callback (busy gerade eben) darf NICHT als Haenger gelten
w = make(busy=time.monotonic(), hotkey_ok=True)
w._tick()
check("Watchdog frischer Callback -> kein re-exec", not _Spy.reexec_called)

# --- Aufraeumen ---
for h in _held:
    try:
        _k32.CloseHandle(ctypes.c_void_p(h))
    except Exception:
        pass
try:
    for f in os.listdir(_TMP):
        os.remove(os.path.join(_TMP, f))
    os.rmdir(_TMP)
except OSError:
    pass

print(f"\n{sum(results)}/{len(results)} bestanden")
sys.exit(0 if all(results) else 1)
