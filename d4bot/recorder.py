"""Waypoint / chest-spot recorder logic (ui-free, testable)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class RecorderError(Exception):
    pass


@dataclass
class Recorder:
    """Collects route waypoints and chest spots in world coordinates."""

    axes: tuple[int, int] = (0, 1)
    waypoints: list[dict] = field(default_factory=list)
    chests: list[dict] = field(default_factory=list)
    _order: list[str] = field(default_factory=list)

    def _xy(self, pos) -> tuple[float, float]:
        ax, ay = self.axes
        if pos is None:
            raise RecorderError("no position in snapshot")
        if max(ax, ay) >= len(pos):
            raise RecorderError(f"position has {len(pos)} components, axes={self.axes}")
        return round(float(pos[ax]), 2), round(float(pos[ay]), 2)

    def add_waypoint(self, pos, kind: str = "walk") -> dict:
        x, y = self._xy(pos)
        wp = {
            "x": x,
            "y": y,
            "label": f"wp-{len(self.waypoints) + 1}",
            "kind": kind,
        }
        self.waypoints.append(wp)
        self._order.append("w")
        return wp

    def add_chest(self, pos) -> dict:
        x, y = self._xy(pos)
        chest = {"x": x, "y": y, "label": f"chest-{len(self.chests) + 1}"}
        self.chests.append(chest)
        self._order.append("c")
        return chest

    def undo(self) -> str:
        if not self._order:
            raise RecorderError("nothing to undo")
        kind = self._order.pop()
        if kind == "w":
            wp = self.waypoints.pop()
            return f"removed waypoint {wp['label']}"
        chest = self.chests.pop()
        return f"removed chest {chest['label']}"

    def summary(self) -> str:
        return f"{len(self.waypoints)} waypoint(s), {len(self.chests)} chest spot(s)"

    def save(self, bot_path: str | Path) -> Path:
        """Merge route/chest_spots into an existing bot.json (creating it if needed)."""
        path = Path(bot_path)
        doc: dict = {}
        if path.exists():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RecorderError(f"existing {path} is not valid JSON: {exc}") from exc
        doc["route"] = self.waypoints
        doc["chest_spots"] = self.chests
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return path
