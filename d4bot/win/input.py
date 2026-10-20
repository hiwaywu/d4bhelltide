"""Synthetic input via SendInput (keyboard + mouse), with a hard safety gate.

Every injection is preceded by a Safety.check(); if the game is not the
foreground window, or the panic key is held, nothing is sent.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from ..config import vk_for
from ..errors import D4BotError

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

ULONG_PTR = ctypes.c_ulonglong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


user32.SendInput.restype = wintypes.UINT
user32.SendInput.argtypes = [
    wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

SM_CXSCREEN = 0
SM_CYSCREEN = 1


class InputBlocked(D4BotError):
    """Safety gate refused to send input."""


class Safety:
    """Panic key + foreground checks. Construct once, share with Input."""

    def __init__(
        self,
        panic_vk: int = 0x7B,          # F12
        require_foreground: bool = True,
        target_pid: int = 0,
        dry_run: bool = True,
    ) -> None:
        self.panic_vk = panic_vk
        self.require_foreground = require_foreground
        self.target_pid = target_pid
        self.dry_run = dry_run
        self.stopped = False
        self.stop_reason = ""

    def panic_held(self) -> bool:
        try:
            return bool(_get_async_key_state(self.panic_vk) & 0x8000)
        except OSError:
            return False

    def stop(self, reason: str) -> None:
        self.stopped = True
        self.stop_reason = reason

    def blocked_reason(self) -> str | None:
        if self.stopped:
            return f"stopped: {self.stop_reason}"
        if self.panic_held():
            self.stop("panic key held")
            return "stopped: panic key held"
        if self.require_foreground and self.target_pid:
            from .memory import foreground_pid

            fg = foreground_pid()
            if fg != self.target_pid:
                return f"game not foreground (foreground pid {fg})"
        return None

    def ensure(self) -> None:
        reason = self.blocked_reason()
        if reason:
            raise InputBlocked(reason)


def _get_async_key_state(vk: int) -> int:
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    return int(user32.GetAsyncKeyState(vk))


def _key_input(vk: int, up: bool) -> INPUT:
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = KEYEVENTF_SCANCODE
    if up:
        flags |= KEYEVENTF_KEYUP
    ki = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = ki
    return inp


class Input:
    def __init__(self, safety: Safety | None = None, dry_run: bool = True) -> None:
        self.safety = safety or Safety(dry_run=dry_run)
        self.dry_run = dry_run
        self._held: set[int] = set()
        self.last_error = ""

    # -- plumbing -------------------------------------------------------
    def _send(self, inputs: list[INPUT], force: bool = False) -> None:
        # force=True is only used for key-release paths: letting keys stay held
        # after a panic/stop would be dangerous, so releases bypass the gate.
        if not force:
            self.safety.ensure()
        if self.dry_run:
            return
        arr = (INPUT * len(inputs))(*inputs)
        sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            err = ctypes.get_last_error()
            self.last_error = f"SendInput sent {sent}/{len(inputs)} (err {err})"

    # -- keyboard -------------------------------------------------------
    def key_down(self, vk: int) -> None:
        if vk in self._held:
            return
        self._send([_key_input(vk, up=False)])
        self._held.add(vk)

    def key_up(self, vk: int) -> None:
        if vk not in self._held:
            return
        self._send([_key_input(vk, up=True)], force=True)
        self._held.discard(vk)

    def tap(self, vk: int, hold: float = 0.02) -> None:
        self._send([_key_input(vk, up=False)])
        if hold > 0 and not self.dry_run:
            time.sleep(hold)
        self._send([_key_input(vk, up=True)], force=True)

    def tap_name(self, name: str, hold: float = 0.02) -> None:
        self.tap(vk_for(name), hold)

    def release_all(self) -> None:
        for vk in list(self._held):
            try:
                self._send([_key_input(vk, up=True)], force=True)
            except Exception:
                pass
            self._held.discard(vk)

    # -- mouse ----------------------------------------------------------
    def click(self, button: str = "left") -> None:
        if button == "left":
            down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        else:
            down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        for flag in (down, up):
            mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
            inp = INPUT(type=INPUT_MOUSE)
            inp.mi = mi
            self._send([inp])

    def move_to(self, x: int, y: int) -> None:
        w = user32.GetSystemMetrics(SM_CXSCREEN)
        h = user32.GetSystemMetrics(SM_CYSCREEN)
        if w <= 1 or h <= 1:
            return
        ax = int(x * 65535 / (w - 1))
        ay = int(y * 65535 / (h - 1))
        mi = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, 0)
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = mi
        self._send([inp])
