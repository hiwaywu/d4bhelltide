#!/usr/bin/env python3
"""Interactive route / chest-spot recorder.

Run while in the Helltide zone; walk your farming loop and press Enter to drop
waypoints, `c` at Mystery Chest candidate spots. Saves straight into bot.json.

    python tools\\record_route.py
    python tools\\record_route.py --bot config/bot.json

Commands: [Enter]=waypoint  c=chest  m=mount waypoint  u=undo  l=list  s=save  q=quit+save
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

from d4bot.config import load_bot, load_offsets_file  # noqa: E402
from d4bot.errors import D4BotError  # noqa: E402
from d4bot.reader import Reader  # noqa: E402
from d4bot.recorder import Recorder, RecorderError  # noqa: E402
from d4bot.win.memory import Process  # noqa: E402


def attach(args) -> Process:
    if args.pid:
        return Process.open(int(args.pid))
    return Process.attach(args.game)


def fmt_pos(snap, axes) -> str:
    if snap.pos is None:
        return "?"
    ax, ay = axes
    if max(ax, ay) < len(snap.pos):
        return f"x={snap.pos[ax]:8.1f} y={snap.pos[ay]:8.1f}"
    return "(" + ",".join(f"{v:.1f}" for v in snap.pos) + ")"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offsets", default="config/offsets.json")
    ap.add_argument("--bot", default="config/bot.json")
    ap.add_argument("--game", default="diablo")
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--interval", type=float, default=0.5)
    args = ap.parse_args()

    try:
        offsets = load_offsets_file(args.offsets)
        cfg = load_bot(args.bot)
        proc = attach(args)
    except D4BotError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        reader = Reader(proc, offsets)
        axes = tuple(cfg.get("movement", {}).get("axes", [0, 1]))
        rec = Recorder(axes=axes)  # type: ignore[arg-type]
        print("recorder ready. [Enter]=waypoint  c=chest  m=mount-wp  u=undo  l=list  s=save  q=quit+save")
        print("NOTE: position field must be configured (Phase 2C) for this to work.\n")
        while True:
            t0 = time.time()
            try:
                snap = reader.poll()
            except D4BotError as exc:
                print(f"[read failed] {exc}")
                time.sleep(args.interval)
                continue
            print(
                f"pos {fmt_pos(snap, axes)}  cinders={snap.cinders} hp={snap.hp}  "
                f"route={len(rec.waypoints)} chests={len(rec.chests)}"
            )
            try:
                line = input("[Enter]wp  c chest  m mount  u undo  l list  s save  q quit > ")
            except (EOFError, KeyboardInterrupt):
                line = "q"
            cmd = line.strip().lower()
            try:
                if cmd in ("", "w"):
                    print("added", rec.add_waypoint(snap.pos))
                elif cmd == "c":
                    print("added", rec.add_chest(snap.pos))
                elif cmd == "m":
                    print("added", rec.add_waypoint(snap.pos, kind="mount"))
                elif cmd == "u":
                    print(rec.undo())
                elif cmd == "l":
                    print(rec.summary())
                    for wp in rec.waypoints:
                        print(f"  wp  {wp['label']:<8} ({wp['x']}, {wp['y']}) kind={wp['kind']}")
                    for ch in rec.chests:
                        print(f"  chest {ch['label']:<8} ({ch['x']}, {ch['y']})")
                elif cmd == "s":
                    print("saved", rec.save(args.bot))
                elif cmd in ("q", "quit", "exit"):
                    if rec.waypoints or rec.chests:
                        print("saved", rec.save(args.bot))
                    break
                else:
                    print("unknown command")
            except RecorderError as exc:
                print(f"cannot record: {exc}")
            time.sleep(max(0.0, args.interval - (time.time() - t0)))
        return 0
    finally:
        proc.close()


if __name__ == "__main__":
    sys.exit(main())
