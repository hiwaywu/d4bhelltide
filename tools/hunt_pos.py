#!/usr/bin/env python3
"""Find the position (f32x3) field by diffing a window around the cinder field.

Requires a validated `cinders` chain in offsets.json (Phase 2A). Then:

    python tools\\hunt_pos.py

1. Stand still and press Enter (snapshot A)
2. Walk straight ~10 m and press Enter (snapshot B)
3. Paste the printed chain into offsets.json as `position`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

from d4bot.config import load_offsets_file  # noqa: E402
from d4bot.errors import D4BotError  # noqa: E402
from d4bot.reader import Reader, resolve_chain  # noqa: E402
from d4bot.re.position import find_moved_triples  # noqa: E402
from d4bot.win.memory import Process  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offsets", default="config/offsets.json")
    ap.add_argument("--game", default="diablo")
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--window", type=lambda s: int(s, 0), default=0x2000)
    ap.add_argument("--align", type=int, default=4)
    args = ap.parse_args()

    try:
        offsets = load_offsets_file(args.offsets)
        if "cinders" not in offsets.fields:
            print("no 'cinders' field in offsets.json; finish Phase 2A first")
            return 1
        proc = Process.open(args.pid) if args.pid else Process.attach(args.game)
    except D4BotError as exc:
        print(f"FAIL: {exc}")
        return 2

    try:
        reader = Reader(proc, offsets)
        cinders = offsets.fields["cinders"]
        c_addr = resolve_chain(proc, reader.base, cinders.static_off, cinders.offsets)
        start = max(0, c_addr - args.window)
        size = args.window * 2 + 16
        print(f"cinder field at {c_addr:#x}; window {start:#x}..{start + size:#x}")
        print(f"cinders chain: static+{cinders.static_off:#x} offsets={[hex(o) for o in cinders.offsets]}")

        input("1) stand still, then press Enter > ")
        before = proc.read(start, size)
        input("2) walk straight ~10 m (hold W), stop, then press Enter > ")
        after = proc.read(start, size)

        cands = find_moved_triples(before, after, align=args.align)
        if not cands:
            print("no coherent float triples moved; try a bigger window or a longer walk")
            return 1

        object_base = c_addr - cinders.offsets[-1]
        print(f"\n{len(cands)} candidate(s):")
        shown = 0
        for cand in cands[:10]:
            field_addr = start + cand.offset
            new_off = field_addr - object_base
            header = (
                f"  [{shown:>2}] +{cand.offset:#06x} "
                f"before=({cand.before[0]:.2f},{cand.before[1]:.2f},{cand.before[2]:.2f}) "
                f"after=({cand.after[0]:.2f},{cand.after[1]:.2f},{cand.after[2]:.2f}) "
                f"|d|={cand.delta:.2f} chg={cand.changed_components}"
            )
            print(header)
            if 0 <= new_off <= 0x20000:
                chain = {
                    "static_off": hex(cinders.static_off),
                    "offsets": [hex(o) for o in cinders.offsets[:-1]] + [hex(new_off)],
                    "type": "f32x3",
                    "axes": [0, 1],
                }
                print("       " + json.dumps(chain))
            shown += 1
        print("\nPick the one whose before/after matches your walk; validate with watch.py.")
        return 0
    finally:
        proc.close()


if __name__ == "__main__":
    sys.exit(main())
