"""Prevent the OS screensaver / display sleep while a macro is playing.

Synthetic input (pynput uses SetCursorPos / SendInput) does not reliably
reset the OS idle timer, so a macro that only moves the mouse, or that
waits (Scheduled start, Interval, long Delay), lets the screensaver kick in.
The fix is to ask the OS directly for a "display required" assertion.
"""
from subprocess import Popen, DEVNULL
from sys import platform
from threading import Lock


class KeepAwake:
    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self):
        self._lock = Lock()
        self._active = False
        self._proc = None

    def start(self):
        """Must be called from the thread that stays alive during playback
        (on Windows the assertion is per-thread)."""
        with self._lock:
            if self._active:
                return
            try:
                if platform == "win32":
                    from ctypes import windll
                    windll.kernel32.SetThreadExecutionState(
                        self._ES_CONTINUOUS
                        | self._ES_SYSTEM_REQUIRED
                        | self._ES_DISPLAY_REQUIRED
                    )
                elif platform == "darwin":
                    # -d display, -i idle sleep, -u declare user activity
                    self._proc = Popen(["caffeinate", "-d", "-i", "-u"],
                                       stdout=DEVNULL, stderr=DEVNULL)
                else:  # linux / bsd
                    self._proc = self._linux_inhibit()
                self._active = True
            except Exception as e:
                print(f"KeepAwake: could not inhibit screensaver ({e})")

    def stop(self):
        with self._lock:
            if not self._active:
                return
            try:
                if platform == "win32":
                    from ctypes import windll
                    windll.kernel32.SetThreadExecutionState(self._ES_CONTINUOUS)
                elif self._proc is not None:
                    self._proc.terminate()
                    self._proc = None
            except Exception as e:
                print(f"KeepAwake: could not release inhibit ({e})")
            self._active = False

    @staticmethod
    def _linux_inhibit():
        # systemd-inhibit keeps the lock as long as the child lives.
        try:
            return Popen(
                ["systemd-inhibit", "--what=idle:sleep",
                 "--who=PyMacroRecord", "--why=Macro playback",
                 "sleep", "infinity"],
                stdout=DEVNULL, stderr=DEVNULL)
        except FileNotFoundError:
            pass
        # Fallback for systems without systemd: poke the X screensaver
        # every 50 s until the child is terminated in stop().
        try:
            return Popen(
                ["sh", "-c",
                 "while true; do xdg-screensaver reset; sleep 50; done"],
                stdout=DEVNULL, stderr=DEVNULL)
        except FileNotFoundError:
            return None
