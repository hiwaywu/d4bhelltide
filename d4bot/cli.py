"""Command line interface: python -m d4bot <command>."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import load_bot, load_offsets_file, vk_for
from .errors import ConfigError, D4BotError, MemError, SnapshotError
from .reader import Reader
from .win.input import Input, Safety
from .win.memory import Process

DEFAULT_OFFSETS = "config/offsets.json"
DEFAULT_BOT = "config/bot.json"


def _attach(args: argparse.Namespace) -> Process:
    """Attach by explicit --pid (tests/debug) or by process-name match."""
    pid = getattr(args, "pid", None)
    if pid:
        return Process.open(int(pid))
    return Process.attach(args.game)


def cmd_probe(args: argparse.Namespace) -> int:
    try:
        proc = _attach(args)
    except MemError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        mod = proc.main_module("diablo")
        regions = proc.readable_regions()
        total = sum(r.size for r in regions) / (1024 * 1024)
        head = proc.read(mod.base, 2)
        print(f"PASS: pid={proc.pid} module={mod.name or '(image)'} base={mod.base:#x} size={mod.size:#x}")
        print(f"      readable regions={len(regions)} total={total:.0f} MiB, MZ={head == b'MZ'}")
        return 0
    finally:
        proc.close()


def cmd_validate(args: argparse.Namespace) -> int:
    offsets = load_offsets_file(args.offsets)
    if not offsets.fields:
        print("No fields configured yet - fill config/offsets.json first (see OFFSETS-HUNTING.md).")
        return 1
    try:
        proc = _attach(args)
    except MemError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        reader = Reader(proc, offsets)
        snap = reader.poll()
        print(f"module base {reader.base:#x} patch {offsets.patch or '?'}")
        print(f"cinders={snap.cinders} hp={snap.hp} resource={snap.resource} pos={snap.pos}")
        print(f"entities={len(snap.entities)}")
        if snap.missing:
            print("unreadable: " + ", ".join(sorted(snap.missing)))
            return 1
        return 0
    except SnapshotError as exc:
        print(f"INVALID: {exc}")
        return 1
    finally:
        proc.close()


def cmd_run(args: argparse.Namespace) -> int:
    from .bot.loop import BotLoop

    offsets = load_offsets_file(args.offsets)
    cfg = load_bot(args.bot)
    try:
        proc = _attach(args)
    except MemError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        loop = BotLoop(proc, offsets, cfg, live=args.live, log_dir=args.log_dir)
        loop.run()
        return 0
    finally:
        proc.close()


def cmd_calibrate(args: argparse.Namespace) -> int:
    offsets = load_offsets_file(args.offsets)
    cfg = load_bot(args.bot)
    if not args.live:
        print("calibration needs --live (it moves your character)")
        return 2
    try:
        proc = _attach(args)
    except MemError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        reader = Reader(proc, offsets)
        safety = Safety(panic_vk=int(cfg.get("panic_vk", 123)), require_foreground=True, target_pid=proc.pid, dry_run=False)
        inp = Input(safety, dry_run=False)
        axes = tuple(cfg.get("movement", {}).get("axes", [0, 1]))
        keys = cfg.get("keys", {})
        roles = {"forward": "W", "back": "S", "left": "A", "right": "D"}

        def pos() -> tuple[float, float] | None:
            snap = reader.poll()
            if snap.pos is None or max(axes) >= len(snap.pos):
                return None
            return float(snap.pos[axes[0]]), float(snap.pos[axes[1]])

        basis: dict[str, list[float]] = {}
        print("Calibration: hold each movement key for 1.2 s. Keep the game focused. F12 aborts.")
        try:
            for role, label in roles.items():
                vk = vk_for(keys[role])
                p0 = pos()
                if p0 is None:
                    print("no position field configured - cannot calibrate")
                    return 1
                inp.key_down(vk)
                time.sleep(1.2)
                inp.key_up(vk)
                time.sleep(0.3)
                p1 = pos()
                if p1 is None:
                    print(f"{label}: lost position reading")
                    return 1
                dx, dy = (p1[0] - p0[0]) / 1.2, (p1[1] - p0[1]) / 1.2
                basis[label] = [round(dx, 4), round(dy, 4)]
                print(f"{label}: d=({dx:+.3f}, {dy:+.3f}) units/s")
        finally:
            # never leave a movement key held if anything goes wrong mid-hold
            inp.release_all()
        print(json.dumps({"movement": {"basis": basis, "calibrated": True}}, indent=2))
        if args.write:
            bot_path = Path(args.bot)
            doc = json.loads(bot_path.read_text(encoding="utf-8")) if bot_path.exists() else {}
            doc.setdefault("movement", {})
            doc["movement"]["basis"] = basis
            doc["movement"]["calibrated"] = True
            bot_path.parent.mkdir(parents=True, exist_ok=True)
            bot_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            print(f"written to {bot_path}")
        return 0
    except SnapshotError as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        proc.close()


def cmd_dump(args: argparse.Namespace) -> int:
    offsets = load_offsets_file(args.offsets)
    try:
        proc = _attach(args)
    except MemError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        reader = Reader(proc, offsets)
        base = reader.base + args.addr
        from .re.probe import hexdump

        print(hexdump(proc, base, args.size))
        return 0
    finally:
        proc.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="d4bot", description="read-only Diablo 4 Helltide assistant")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("--pid", type=int, default=None, help="attach to this pid instead of the game name (testing)")
        return sp

    probe = common(sub.add_parser("probe", help="attach-test: can we read the game?"))
    probe.add_argument("--game", default="diablo")
    probe.set_defaults(func=cmd_probe)

    val = common(sub.add_parser("validate", help="check offsets.json against the live game"))
    val.add_argument("--offsets", default=DEFAULT_OFFSETS)
    val.add_argument("--game", default="diablo")
    val.set_defaults(func=cmd_validate)

    run = common(sub.add_parser("run", help="run the bot (dry-run unless --live)"))
    run.add_argument("--offsets", default=DEFAULT_OFFSETS)
    run.add_argument("--bot", default=DEFAULT_BOT)
    run.add_argument("--game", default="diablo")
    run.add_argument("--live", action="store_true", help="actually send input")
    run.add_argument("--log-dir", default="logs")
    run.set_defaults(func=cmd_run)

    cal = common(sub.add_parser("calibrate", help="measure WASD -> world basis (live)"))
    cal.add_argument("--offsets", default=DEFAULT_OFFSETS)
    cal.add_argument("--bot", default=DEFAULT_BOT)
    cal.add_argument("--game", default="diablo")
    cal.add_argument("--live", action="store_true")
    cal.add_argument("--write", action="store_true", help="save basis into bot.json")
    cal.set_defaults(func=cmd_calibrate)

    dump = common(sub.add_parser("dump", help="hexdump module-relative address"))
    dump.add_argument("--offsets", default=DEFAULT_OFFSETS)
    dump.add_argument("--game", default="diablo")
    dump.add_argument("--addr", type=lambda s: int(s, 0), required=True)
    dump.add_argument("--size", type=lambda s: int(s, 0), default=256)
    dump.set_defaults(func=cmd_dump)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, MemError, D4BotError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
