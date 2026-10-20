"""Configuration loading (offsets.json + bot.json) with sane defaults."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .reader import Offsets, load_offsets

DEFAULT_BOT: dict[str, Any] = {
    "panic_vk": 123,                 # F12
    "require_foreground": True,
    "live_input": False,             # must be enabled explicitly with --live
    "keys": {
        "forward": "W",
        "back": "S",
        "left": "A",
        "right": "D",
        "stance": "SPACE",
        "evade": "SPACE",
        "potion": "Q",
        "mount": "R",
        "interact": "F",
    },
    "movement": {
        "axes": [0, 1],
        "basis": {
            "W": [0.0, -1.0],
            "S": [0.0, 1.0],
            "A": [-1.0, 0.0],
            "D": [1.0, 0.0],
        },
        "calibrated": False,
        "keys_per_step": 100,
        "step_hold_s": 0.09,
    },
    "thresholds": {
        "retreat_hp": 0.35,
        "resume_hp": 0.6,
        "chest_cost": 75,
        "interact_radius": 2.5,
        "waypoint_radius": 3.0,
        "engage_radius": 14.0,
        "aggro_radius": 24.0,
    },
    "combat": {
        "hostile_team": None,
        "skills": [
            {"key": "1", "kind": "attack", "range": 9.0, "cooldown": 0.5},
            {"key": "2", "kind": "attack", "range": 12.0, "cooldown": 1.0},
            {"key": "3", "kind": "attack", "range": 6.0, "cooldown": 2.0},
            {"key": "4", "kind": "buff", "range": 0.0, "cooldown": 10.0, "every": 10.0},
        ],
    },
    "route": [],               # list of {"x":..,"y":..,"label":..,"kind":"walk"|"mount"}
    "chest_spots": [],         # list of {"x":..,"y":..,"label":..}
    "loop": {"tick_s": 0.1, "max_runtime_s": 0, "loot": False},
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_bot(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULT_BOT)
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return deep_merge(DEFAULT_BOT, doc)


def load_offsets_file(path: str | Path) -> Offsets:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_offsets(doc)


VK_ALIASES = {
    "SPACE": 0x20,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
}


def vk_for(key: str) -> int:
    key = key.upper()
    if key in VK_ALIASES:
        return VK_ALIASES[key]
    if len(key) == 1:
        return ord(key)
    raise ConfigError(f"unknown key name {key!r}")
