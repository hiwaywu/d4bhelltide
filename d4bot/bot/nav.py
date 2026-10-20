"""Route following in world space using WASD (isometric, no camera control)."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ..config import vk_for
from ..win.input import Input

# combination name -> key roles
COMBOS: list[tuple[str, tuple[str, ...]]] = [
    ("W", ("forward",)),
    ("WD", ("forward", "right")),
    ("D", ("right",)),
    ("SD", ("back", "right")),
    ("S", ("back",)),
    ("SA", ("back", "left")),
    ("A", ("left",)),
    ("WA", ("forward", "left")),
]


@dataclass
class Waypoint:
    x: float
    y: float
    label: str = ""
    kind: str = "walk"
    radius: float = 3.0

    @classmethod
    def from_dict(cls, d: dict) -> "Waypoint":
        return cls(
            x=float(d["x"]),
            y=float(d["y"]),
            label=str(d.get("label", "")),
            kind=str(d.get("kind", "walk")),
            radius=float(d.get("radius", 3.0)),
        )


def parse_waypoints(items: list[dict] | None) -> list[Waypoint]:
    return [Waypoint.from_dict(d) for d in (items or [])]


class Navigator:
    def __init__(self, inp: Input, cfg: dict) -> None:
        self.inp = inp
        self.keys = cfg.get("keys", {})
        self.mv = cfg.get("movement", {})
        self.axes: tuple[int, int] = tuple(self.mv.get("axes", [0, 1]))  # type: ignore[assignment]
        self.basis: dict[str, list[float]] = self.mv.get("basis", {})
        self.step_hold = float(self.mv.get("step_hold_s", 0.09))
        self._held_combo: str | None = None
        self._last_pos: tuple[float, float] | None = None
        self._last_move_t = 0.0
        self._stuck_ticks = 0
        self._vks = {role: vk_for(key) for role, key in self.keys.items()}

    # -- geometry -------------------------------------------------------
    def horizontal(self, pos: tuple[float, ...]) -> tuple[float, float] | None:
        if pos is None:
            return None
        ax, ay = self.axes
        if max(ax, ay) >= len(pos):
            return None
        return float(pos[ax]), float(pos[ay])

    def _combo_vectors(self) -> dict[str, tuple[float, float]]:
        out: dict[str, tuple[float, float]] = {}
        for name, roles in COMBOS:
            vx = vy = 0.0
            for role in roles:
                b = self.basis.get(role.upper()) or self.basis.get(role)
                if b:
                    vx += b[0]
                    vy += b[1]
            norm = math.hypot(vx, vy) or 1.0
            out[name] = (vx / norm, vy / norm)
        return out

    # -- movement -------------------------------------------------------
    def set_combo(self, combo: str) -> None:
        if combo == self._held_combo:
            return
        wanted = set(dict(COMBOS)[combo])
        for role in ("forward", "back", "left", "right"):
            vk = self._vks.get(role)
            if vk is None:
                continue
            if role in wanted:
                self.inp.key_down(vk)
            else:
                self.inp.key_up(vk)
        self._held_combo = combo

    def release(self) -> None:
        for role in ("forward", "back", "left", "right"):
            vk = self._vks.get(role)
            if vk is not None:
                self.inp.key_up(vk)
        self._held_combo = None

    def step(self, pos: tuple[float, ...], target: Waypoint | tuple[float, float], now: float) -> str:
        """Move one tick toward target. Returns 'arrived' | 'moving' | 'stuck'."""
        here = self.horizontal(pos)
        if here is None:
            return "stuck"
        if isinstance(target, Waypoint):
            tx, ty = target.x, target.y
            radius = target.radius
        else:
            tx, ty = target
            radius = float(self.mv.get("waypoint_radius", 3.0))

        dx, dy = tx - here[0], ty - here[1]
        dist = math.hypot(dx, dy)
        if dist <= radius:
            self.release()
            return "arrived"

        # stuck detection: if we have been "moving" without displacement
        if self._last_pos is not None:
            moved = math.hypot(here[0] - self._last_pos[0], here[1] - self._last_pos[1])
            elapsed = now - self._last_move_t
            if elapsed > 1.5 and moved < 0.05:
                self._stuck_ticks += 1
                if self._stuck_ticks >= 2:
                    self._stuck_ticks = 0
                    self.release()
                    return "stuck"
            elif moved >= 0.05:
                self._stuck_ticks = 0
                self._last_move_t = now
        if self._last_pos is None:
            self._last_move_t = now
        self._last_pos = here

        nx, ny = dx / dist, dy / dist
        best, best_dot = "W", -2.0
        for name, (vx, vy) in self._combo_vectors().items():
            dot = vx * nx + vy * ny
            if dot > best_dot:
                best, best_dot = name, dot
        self.set_combo(best)
        return "moving"

    # -- unstuck ---------------------------------------------------------
    def nudge(self, direction: str = "A") -> None:
        """Brief perpendicular shove to escape a corner."""
        self.set_combo(direction)
        time.sleep(0.35)
        self.release()
