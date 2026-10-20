"""Environment / configuration diagnostics: one command to find setup problems."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .config import load_bot, load_offsets_file
from .errors import D4BotError


@dataclass
class Check:
    name: str
    status: str          # ok | warn | fail | skip
    detail: str = ""


def environment_checks() -> list[Check]:
    checks: list[Check] = []
    bits = struct.calcsize("P") * 8
    checks.append(
        Check("python-bitness", "ok" if bits == 64 else "fail", f"{bits}-bit")
    )
    checks.append(
        Check("python-version", "ok" if __import__("sys").version_info >= (3, 10) else "fail",
              __import__("sys").version.split()[0])
    )
    try:
        import numpy

        major = int(numpy.__version__.split(".")[0])
        checks.append(
            Check("numpy", "ok" if major >= 2 else "warn", numpy.__version__)
        )
    except Exception as exc:  # pragma: no cover - import error path
        checks.append(Check("numpy", "fail", f"not importable: {exc}"))
    return checks


def config_checks(offsets_path: str | Path, bot_path: str | Path) -> list[Check]:
    checks: list[Check] = []
    try:
        offsets = load_offsets_file(offsets_path)
        if not offsets.fields:
            checks.append(
                Check("offsets", "warn", f"{offsets_path}: no fields configured yet (Phase 2)")
            )
        else:
            missing = [f for f in offsets.required if f not in offsets.fields]
            detail = (
                f"{len(offsets.fields)} field(s), required={offsets.required or '[]'}"
                + (f", missing={missing}" if missing else "")
            )
            checks.append(
                Check("offsets", "fail" if missing else "ok", f"{offsets_path}: {detail}")
            )
    except (D4BotError, OSError, ValueError) as exc:
        checks.append(Check("offsets", "fail", f"{offsets_path}: {exc}"))

    try:
        cfg = load_bot(bot_path)
        panic = int(cfg.get("panic_vk", 0))
        checks.append(
            Check(
                "bot-config",
                "ok" if panic else "warn",
                f"{bot_path}: panic_vk={panic} route={len(cfg.get('route', []))} "
                f"chests={len(cfg.get('chest_spots', []))}",
            )
        )
    except (D4BotError, OSError, ValueError) as exc:
        checks.append(Check("bot-config", "fail", f"{bot_path}: {exc}"))
    return checks


def game_check() -> list[Check]:
    from .win.memory import find_process

    try:
        matches = find_process("diablo")
    except Exception as exc:  # pragma: no cover
        return [Check("game", "warn", f"process lookup failed: {exc}")]
    if not matches:
        return [Check("game", "skip", "Diablo IV is not running (fine until Phase 0)")]
    pid, name = matches[0]
    return [Check("game", "ok", f"{name} pid={pid}")]


def run_all(offsets_path: str | Path, bot_path: str | Path) -> list[Check]:
    checks = environment_checks()
    checks += config_checks(offsets_path, bot_path)
    checks += game_check()
    return checks


def worst_status(checks: list[Check]) -> str:
    order = {"ok": 0, "warn": 1, "skip": 1, "fail": 2}
    return max(checks, key=lambda c: order.get(c.status, 2)).status if checks else "fail"
