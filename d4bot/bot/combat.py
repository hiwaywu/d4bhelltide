"""Combat rotation driven by config. Self-centred skills only in v1."""
from __future__ import annotations

import time
from dataclasses import dataclass

from ..config import vk_for
from ..win.input import Input


@dataclass
class SkillCfg:
    key: str
    kind: str = "attack"       # attack | buff | heal
    range: float = 8.0
    cooldown: float = 0.5
    every: float = 0.0


@dataclass
class CombatTarget:
    dist: float | None


class Combat:
    def __init__(self, inp: Input, cfg: dict) -> None:
        self.inp = inp
        self.hostile_team = cfg.get("hostile_team")
        self.aggro_radius = float(cfg.get("aggro_radius", 24.0))
        self.engage_radius = float(cfg.get("engage_radius", 14.0))
        self.skills = [
            SkillCfg(
                key=s["key"],
                kind=s.get("kind", "attack"),
                range=float(s.get("range", 8.0)),
                cooldown=float(s.get("cooldown", 0.5)),
                every=float(s.get("every", 0.0)),
            )
            for s in cfg.get("skills", [])
        ]
        self._ready: dict[str, float] = {}

    def act(self, snap, now: float) -> str | None:
        target = snap.nearest(self.hostile_team, self.aggro_radius)
        actions: list[str] = []

        # buffs fire on their own schedule, at most one per tick
        for skill in self.skills:
            if skill.kind != "buff":
                continue
            if now >= self._ready.get(skill.key, 0.0):
                self.inp.tap_name(skill.key)
                self._ready[skill.key] = now + max(skill.every or skill.cooldown, 0.1)
                actions.append(f"buff({skill.key})")
                break

        # fire exactly one attack skill per tick: the first ready one in range
        if target is not None and target.dist is not None:
            for skill in self.skills:
                if skill.kind != "attack":
                    continue
                if target.dist > skill.range:
                    continue
                if now < self._ready.get(skill.key, 0.0):
                    continue
                self.inp.tap_name(skill.key)
                self._ready[skill.key] = now + max(skill.cooldown, 0.05)
                actions.append(f"attack({skill.key})@{target.dist:.1f}m")
                break

        return " ".join(actions) if actions else None


def time_now() -> float:
    return time.time()
