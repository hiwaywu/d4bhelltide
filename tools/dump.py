#!/usr/bin/env python3
"""Hexdump / qword inspector for module-relative addresses.

    python tools/dump.py --addr 0x1234560 --size 256
    python tools/dump.py --addr 0x1234560 --qwords 8
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

from d4bot.config import load_offsets_file  # noqa: E402
from d4bot.errors import D4BotError  # noqa: E402
from d4bot.re.probe import hexdump, qwords  # noqa: E402
from d4bot.reader import Reader  # noqa: E402
from d4bot.win.memory import Process  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="diablo")
    ap.add_argument("--offsets", default="config/offsets.json")
    ap.add_argument("--addr", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--size", type=lambda s: int(s, 0), default=256)
    ap.add_argument("--qwords", type=int, default=8)
    ap.add_argument("--absolute", action="store_true", help="treat --addr as absolute")
    args = ap.parse_args()

    try:
        proc = Process.attach(args.game)
        base = 0
        if not args.absolute:
            try:
                base = Reader(proc, load_offsets_file(args.offsets)).base
            except D4BotError:
                base = proc.main_module("diablo").base
        addr = base + args.addr
        print(qwords(proc, addr, args.qwords)) if args.qwords else None
        print(hexdump(proc, addr, args.size))
        return 0
    except D4BotError as exc:
        print(f"FAIL: {exc}")
        return 2
    finally:
        try:
            proc.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
