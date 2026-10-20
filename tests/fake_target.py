"""Synthetic target process for end-to-end tests without the game.

Child process plants a known chain:
    root  --[0x00]-->  obj  --[0x10]-->  leaf
                                           leaf+0x08: int32  424242   (cinders)
                                           leaf+0x10: float  61.5     (hp)
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Sandbox note: child processes may only write inside the session workspace,
# and dirs made by tempfile.mkdtemp carry an ACL the sandbox filter mishandles,
# so the handoff uses a plain inherited-ACL directory under <repo>/.tmp.
TMP_DIR = ROOT / ".tmp"
_counter = 0


def _fresh_dir() -> str:
    global _counter
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    _counter += 1
    path = TMP_DIR / f"fake-{os.getpid()}-{_counter}"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def child_main(json_path: str) -> None:
    root = ctypes.create_string_buffer(0x2000)
    obj = ctypes.create_string_buffer(0x2000)
    leaf = ctypes.create_string_buffer(0x2000)

    ctypes.memmove(ctypes.addressof(leaf) + 8, ctypes.byref(ctypes.c_int32(424242)), 4)
    ctypes.memmove(ctypes.addressof(leaf) + 16, ctypes.byref(ctypes.c_float(61.5)), 4)

    ptr = ctypes.c_uint64(ctypes.addressof(leaf))
    ctypes.memmove(ctypes.addressof(obj) + 0x10, ctypes.byref(ptr), 8)
    ptr2 = ctypes.c_uint64(ctypes.addressof(obj))
    ctypes.memmove(ctypes.addressof(root) + 0x0, ctypes.byref(ptr2), 8)

    info = {
        "pid": os.getpid(),
        "root": ctypes.addressof(root),
        "root_size": 0x2000,
        "obj": ctypes.addressof(obj),
        "leaf": ctypes.addressof(leaf),
        "cinders_addr": ctypes.addressof(leaf) + 8,
        "cinders": 424242,
        "hp_addr": ctypes.addressof(leaf) + 16,
        "hp": 61.5,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(info, fh)
    while True:
        time.sleep(0.25)


class FakeTarget:
    def __init__(self) -> None:
        self.dir = _fresh_dir()
        self.info_path = os.path.join(self.dir, "info.json")
        self._err_path = os.path.join(self.dir, "child-err.txt")
        self._err = open(self._err_path, "wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", os.path.abspath(__file__), "child", self.info_path],
            stdout=subprocess.DEVNULL,
            stderr=self._err,
            cwd=self.dir,
        )
        try:
            self.info = self._wait_info()
        except Exception:
            self._err.close()
            raise
        self._err.close()

    def _wait_info(self) -> dict:
        for _ in range(300):
            if os.path.exists(self.info_path):
                try:
                    with open(self.info_path, "r", encoding="utf-8") as fh:
                        return json.load(fh)
                except Exception:
                    pass
            if self.proc.poll() is not None:
                detail = ""
                try:
                    detail = open(self._err_path, "r", encoding="utf-8", errors="replace").read()[-2000:]
                except Exception:
                    pass
                raise RuntimeError(f"fake target died during startup: {detail}")
            time.sleep(0.05)
        raise TimeoutError("fake target did not publish info")

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def __enter__(self) -> "FakeTarget":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "child":
        child_main(sys.argv[2])
    else:
        t = FakeTarget()
        try:
            print(json.dumps(t.info, indent=2))
        finally:
            t.close()
