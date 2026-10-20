#!/usr/bin/env python3
"""Live snapshot printer — the 'eyes' during offset hunting and route recording.

    python tools/watch.py                 # once per second: cinders/hp/pos/entities
    python tools/watch.py --interval 0.2  # faster

Use it to:
  * confirm a chain tracks reality after every in-game change
  * record route coordinates (walk somewhere, copy x/y)
  * check that restart-validation still holds on a new session
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

from d4bot.config import load_offsets_file  # noqa: E402
from d4bot.errors import D4BotError  # noqa: E402
from d4bot.reader import Reader  # noqa: E402
from d4bot.win.memory import Process  # noqa: E402


def fmt(v, digits: int = 1) -> str:
    if v is None:
        return "?"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offsets", default="config/offsets.json")
    ap.add_argument("--game", default="diablo")
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    try:
        offsets = load_offsets_file(args.offsets)
        proc = Process.attach(args.game)
    except D4BotError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        reader = Reader(proc, offsets)
        print("watching (Ctrl-C to stop)")
        while True:
            t0 = time.time()
            try:
                snap = reader.poll()
            except D4BotError as exc:
                print(f"[unreadable] {exc}")
                time.sleep(max(0.0, args.interval - (time.time() - t0)))
                continue
            pos = "?" if snap.pos is None else ",".join(f"{v:.1f}" for v in snap.pos)
            tgt = snap.nearest()
            print(
                f"cinders={fmt(snap.cinders)} hp={fmt(snap.hp)} res={fmt(snap.resource)} "
                f"pos=({pos}) entities={len(snap.entities)} "
                f"nearest={'?' if tgt is None else f'{tgt.dist:.1f}m'}"
                f"{'  missing=' + ','.join(sorted(snap.missing)) if snap.missing else ''}"
            )
            time.sleep(max(0.0, args.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        return 0
    finally:
        proc.close()


if __name__ == "__main__":
    sys.exit(main())
