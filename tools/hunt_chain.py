#!/usr/bin/env python3
"""Find stable pointer chains for a live address found by hunt_value.py.

    python tools/hunt_chain.py --addr 0x1A2B3C4D5E

Outputs ready-to-paste offset-chain JSON. A chain only counts as real after it
survives a game restart (see OFFSETS-HUNTING.md).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

from d4bot.errors import MemError  # noqa: E402
from d4bot.re.pointer_scan import ChainFinder  # noqa: E402
from d4bot.win.memory import Process  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", required=True, help="target field address (absolute or 0x...)")
    ap.add_argument("--game", default="diablo")
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--max-off", type=lambda s: int(s, 0), default=0x2000)
    ap.add_argument("--max-chains", type=int, default=20)
    args = ap.parse_args()

    try:
        proc = Process.attach(args.game)
    except MemError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        mod = proc.main_module("diablo")
        finder = ChainFinder(proc, max_depth=args.depth, max_off=args.max_off)
        print(f"searching chains for {args.addr} (module base {mod.base:#x}, depth<={args.depth}) ...")
        chains = finder.find(args.addr)
        print(f"{len(chains)} chain(s) found\n")
        for c in chains[: args.max_chains]:
            relative = c.static_base == mod.base
            print(f"  {c.describe()}  depth={c.depth}")
            if not relative:
                print(f"    NOTE: static base {c.static_base:#x} != module base")
        if chains:
            best = chains[0]
            snippet = {
                "static_off": hex(best.static_off),
                "offsets": [hex(o) for o in best.offsets],
                "type": "REPLACE_TYPE",
            }
            print("\nbest chain (paste into config/offsets.json fields.<name>):")
            print(json.dumps(snippet, indent=2))
            print("\nThen validate:  python -m d4bot validate")
        return 0 if chains else 1
    finally:
        proc.close()


if __name__ == "__main__":
    sys.exit(main())
