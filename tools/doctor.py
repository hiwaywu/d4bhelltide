#!/usr/bin/env python3
"""One-command setup doctor: python bitness, numpy, configs, game presence.

    python tools\\doctor.py
    python tools\\doctor.py --offsets config/offsets.json --bot config/bot.json

Exit code 0 = environment/config healthy (game may be absent), 1 = a real
problem to fix.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402

from d4bot.diagnostics import run_all, worst_status  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offsets", default="config/offsets.json")
    ap.add_argument("--bot", default="config/bot.json")
    args = ap.parse_args()

    checks = run_all(args.offsets, args.bot)
    for c in checks:
        print(f"[{c.status:4}] {c.name:<14} {c.detail}")

    status = worst_status(checks)
    print()
    if status == "fail":
        print("RESULT: fix the failing checks above before continuing.")
        return 1
    game_ok = any(c.name == "game" and c.status == "ok" for c in checks)
    print("RESULT: environment looks healthy.")
    if game_ok:
        print("Next: python tools\\probe_attach.py  (Phase 0)")
    else:
        print("Next: start Diablo IV, then python tools\\probe_attach.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
