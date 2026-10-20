"""CSV telemetry for offline analysis of runs."""
from __future__ import annotations

import csv
import time
from pathlib import Path


class Telemetry:
    FIELDS = [
        "t",
        "uptime_s",
        "x",
        "y",
        "hp",
        "cinders",
        "target_dist",
        "action",
        "note",
    ]

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._fh, fieldnames=self.FIELDS)
        self._w.writeheader()
        self._t0 = time.time()

    def write(
        self,
        x=None,
        y=None,
        hp=None,
        cinders=None,
        target_dist=None,
        action="",
        note="",
    ) -> None:
        self._w.writerow(
            {
                "t": round(time.time(), 3),
                "uptime_s": round(time.time() - self._t0, 1),
                "x": "" if x is None else round(x, 2),
                "y": "" if y is None else round(y, 2),
                "hp": "" if hp is None else round(hp, 1),
                "cinders": "" if cinders is None else cinders,
                "target_dist": "" if target_dist is None else round(target_dist, 2),
                "action": action,
                "note": note,
            }
        )
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass
