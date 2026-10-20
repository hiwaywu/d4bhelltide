"""Helltide-specific policy: cinders, Tortured Gift spots, retreat thresholds."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ChestSpot:
    x: float
    y: float
    label: str = ""
    radius: float = 2.5

    @classmethod
    def from_dict(cls, d: dict) -> "ChestSpot":
        return cls(
            x=float(d["x"]),
            y=float(d["y"]),
            label=str(d.get("label", "")),
            radius=float(d.get("radius", 2.5)),
        )


class HelltidePolicy:
    def __init__(self, cfg: dict) -> None:
        t = cfg.get("thresholds", {})
        self.cost = int(t.get("chest_cost", 75))
        self.retreat_hp = float(t.get("retreat_hp", 0.35))
        self.resume_hp = float(t.get("resume_hp", 0.6))
        self.interact_radius = float(t.get("interact_radius", 2.5))
        self.chests = [ChestSpot.from_dict(c) for c in cfg.get("chest_spots", [])]
        self.axes: tuple[int, int] = tuple(cfg.get("movement", {}).get("axes", [0, 1]))  # type: ignore[assignment]
        self.opened: set[str] = set()

    # -- chest selection ------------------------------------------------
    def horizontal(self, pos) -> tuple[float, float] | None:
        if pos is None:
            return None
        ax, ay = self.axes
        if max(ax, ay) >= len(pos):
            return None
        return float(pos[ax]), float(pos[ay])

    def chest_distance(self, snap, spot: ChestSpot) -> float | None:
        here = self.horizontal(snap.pos)
        if here is None:
            return None
        return math.hypot(spot.x - here[0], spot.y - here[1])

    def next_chest(self, snap) -> tuple[ChestSpot, float] | None:
        if snap.cinders is None or snap.cinders < self.cost:
            return None
        best: tuple[ChestSpot, float] | None = None
        for spot in self.chests:
            if spot.label in self.opened:
                continue
            d = self.chest_distance(snap, spot)
            if d is None:
                continue
            if best is None or d < best[1]:
                best = (spot, d)
        return best

    def mark_opened(self, spot: ChestSpot) -> None:
        self.opened.add(spot.label)

    def should_retreat(self, hp: float | None) -> bool:
        return hp is not None and 0.0 < hp <= self.retreat_hp

    def should_resume(self, hp: float | None) -> bool:
        return hp is not None and hp >= self.resume_hp
