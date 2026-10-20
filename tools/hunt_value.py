#!/usr/bin/env python3
"""Interactive value scanner (the Cheat-Engine-lite loop) against live D4.

Usage:
    python tools/hunt_value.py --type int32 --value 812
    python tools/hunt_value.py --type float --value 61.7 --approx 0.05

Then, inside the prompt:
    s 843        rescan for exact new value
    c            keep candidates that changed since last scan
    u            keep candidates that did NOT change
    l            list candidates (addresses)
    a 0x1234     hexdump + qword annotations around an address
    h            help
    q            quit
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

from d4bot.errors import MemError  # noqa: E402
from d4bot.re.probe import hexdump, qwords  # noqa: E402
from d4bot.re.scanner import DTYPES, Candidates, ValueScanner  # noqa: E402
from d4bot.win.memory import Process  # noqa: E402


def parse_value(text: str, vtype: str):
    if vtype in ("float", "double"):
        return float(text)
    return int(text, 0)


def show(cands: Candidates, limit: int = 40) -> None:
    print(f"{len(cands)} candidate(s)")
    for i, addr in enumerate(cands.addrs[:limit]):
        raw = bytes(cands.values[i])
        print(f"  [{i:>4}] {int(addr):#014x}  raw={raw.hex()}")
    if len(cands) > limit:
        print(f"  ... {len(cands) - limit} more")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="diablo")
    ap.add_argument("--type", default="int32", choices=sorted(DTYPES))
    ap.add_argument("--value", default=None)
    ap.add_argument("--approx", type=float, default=None, help="tolerance for float scans")
    ap.add_argument("--align", type=int, default=4)
    args = ap.parse_args()

    try:
        proc = Process.attach(args.game)
    except MemError as exc:
        print(f"FAIL: {exc}")
        return 2
    try:
        scanner = ValueScanner(proc, align=args.align)
        cands: Candidates | None = None
        if args.value is not None:
            value = parse_value(args.value, args.type)
            print(f"first scan: {args.type} == {value} ...")
            cands = scanner.first_scan(value, args.type, tol=args.approx)
            show(cands)
        help_text = "s <value> exact-filter | c changed | u unchanged | l list | a <addr> inspect | q"
        print(help_text + ("\n(no initial value given - use s <value> to start)" if cands is None else ""))
        while True:
            try:
                line = input("scan> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            cmd, _, rest = line.partition(" ")
            if cmd in ("q", "quit", "exit"):
                break
            if cmd in ("h", "help"):
                print(help_text)
            elif cmd == "s":
                if cands is None:
                    cands = scanner.first_scan(parse_value(rest, args.type), args.type, tol=args.approx)
                else:
                    cands = scanner.filter_exact(cands, parse_value(rest, args.type), tol=args.approx)
                show(cands)
            elif cmd == "c":
                if cands is None:
                    print("nothing to filter")
                    continue
                cands, _ = scanner.filter_changed(cands)
                show(cands)
            elif cmd == "u":
                if cands is None:
                    print("nothing to filter")
                    continue
                _, cands = scanner.filter_changed(cands)
                show(cands)
            elif cmd == "l":
                if cands is None:
                    print("nothing scanned yet")
                else:
                    show(cands, limit=200)
            elif cmd == "a":
                addr = int(rest, 0)
                print(qwords(proc, addr, 8))
                print(hexdump(proc, addr, 64))
            else:
                print(help_text)
        if cands is not None and len(cands) <= 8:
            print("\nfinal candidates:")
            show(cands)
            print("\nNext: python tools/hunt_chain.py --addr <address>")
        return 0
    finally:
        proc.close()


if __name__ == "__main__":
    sys.exit(main())
