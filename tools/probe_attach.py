#!/usr/bin/env python3
"""Phase 0 gate: can we open Diablo IV read-only and read its memory?

Run this with the game logged in (title screen is enough):

    python tools/probe_attach.py

Exit codes: 0 = read path is OPEN, 1 = no game, 2 = access denied/blocked.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from d4bot.errors import MemError  # noqa: E402
from d4bot.win.memory import Process, find_process  # noqa: E402


def main() -> int:
    matches = find_process("diablo")
    if not matches:
        print("NO GAME: no process whose image name contains 'diablo' is running.")
        print("Start Diablo IV (the 64-bit PC client) and re-run.")
        return 1
    for pid, name in matches:
        print(f"found: pid={pid} name={name}")
    try:
        proc = Process.attach("diablo")
    except MemError as exc:
        print(f"\nBLOCKED: {exc}")
        print("The read path is closed on this machine/build.")
        print("Per the project rules we do NOT work around anti-cheat - this is where the memory path ends.")
        return 2

    try:
        mod = proc.main_module("diablo")
        regions = proc.readable_regions()
        total = sum(r.size for r in regions) / (1024 * 1024)
        head = proc.read(mod.base, 2)
        first64 = proc.read(mod.base, 16)
        print(f"\nmodule   : {mod.name or '(image, no name)'}")
        print(f"base     : {mod.base:#x}")
        print(f"size     : {mod.size:#x} ({mod.size / 1024 / 1024:.0f} MiB)")
        print(f"regions  : {len(proc.regions())} total, {len(regions)} readable ({total:.0f} MiB)")
        print(f"MZ header: {head!r}")
        print(f"bytes    : {first64.hex(' ')}")
        if head == b"MZ":
            print("\nPASS - read-only memory access works. Proceed to Phase 2A (cinder hunt).")
            return 0
        print("\nUNEXPECTED - read returned data but no MZ header; offsets may be wrong.")
        return 0
    finally:
        proc.close()


if __name__ == "__main__":
    sys.exit(main())
