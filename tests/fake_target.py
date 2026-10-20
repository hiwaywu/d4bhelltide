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
    ent1 = ctypes.create_string_buffer(0x40)
    ent2 = ctypes.create_string_buffer(0x40)
    array = ctypes.create_string_buffer(0x100)

    def f32(buf, off, value):
        ctypes.memmove(ctypes.addressof(buf) + off, ctypes.byref(ctypes.c_float(value)), 4)

    def i32(buf, off, value):
        ctypes.memmove(ctypes.addressof(buf) + off, ctypes.byref(ctypes.c_int32(value)), 4)

    def u64(buf, off, value):
        ctypes.memmove(ctypes.addressof(buf) + off, ctypes.byref(ctypes.c_uint64(value)), 8)

    # leaf: cinders @0x08, hp @0x10, player pos @0x18
    i32(leaf, 0x08, 424242)
    f32(leaf, 0x10, 61.5)
    f32(leaf, 0x18, 0.0)
    f32(leaf, 0x1C, 0.0)
    f32(leaf, 0x20, 0.0)

    # entities: pos @0x00 (f32x3), hp @0x10, team @0x14
    f32(ent1, 0x00, 10.0)
    f32(ent1, 0x04, 0.0)
    f32(ent1, 0x08, 0.0)
    f32(ent1, 0x10, 50.0)
    i32(ent1, 0x14, 1)
    f32(ent2, 0x00, 5.0)
    f32(ent2, 0x04, 0.0)
    f32(ent2, 0x08, 0.0)
    f32(ent2, 0x10, 0.0)   # dead
    i32(ent2, 0x14, 1)

    u64(array, 0x00, ctypes.addressof(ent1))
    u64(array, 0x08, ctypes.addressof(ent2))

    # obj: pointer to leaf @0x10; entity manager: count @0x20, array ptr @0x28
    u64(obj, 0x10, ctypes.addressof(leaf))
    i32(obj, 0x20, 2)
    u64(obj, 0x28, ctypes.addressof(array))

    # root: pointer to obj @0x00
    u64(root, 0x00, ctypes.addressof(obj))

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
        "pos_addr": ctypes.addressof(leaf) + 0x18,
        "ent1": ctypes.addressof(ent1),
        "ent2": ctypes.addressof(ent2),
        "entities": 2,
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
