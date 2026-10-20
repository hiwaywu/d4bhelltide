"""Main bot loop: snapshot -> policy -> movement/combat -> telemetry."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from ..config import vk_for
from ..errors import SnapshotError
from ..reader import Offsets, Reader, Snapshot
from ..win.input import Input, Safety
from ..win.memory import Process
from .combat import Combat
from .helltide import HelltidePolicy
from .nav import Navigator, parse_waypoints
from .telemetry import Telemetry


class BotLoop:
    def __init__(
        self,
        proc: Process,
        offsets: Offsets,
        cfg: dict,
        live: bool = False,
        log_dir: str | Path = "logs",
        reader: Reader | None = None,
    ) -> None:
        self.proc = proc
        self.cfg = cfg
        self.live = live
        self.reader = reader if reader is not None else Reader(proc, offsets)
        target_pid = getattr(proc, "pid", 0) if proc is not None else 0
        self.safety = Safety(
            panic_vk=int(cfg.get("panic_vk", 123)),
            require_foreground=bool(cfg.get("require_foreground", True)),
            target_pid=target_pid,
            dry_run=not live,
        )
        self.inp = Input(self.safety, dry_run=not live)
        self.nav = Navigator(self.inp, cfg)
        combat_cfg = dict(cfg.get("combat", {}))
        combat_cfg.setdefault("engage_radius", cfg.get("thresholds", {}).get("engage_radius", 14.0))
        combat_cfg.setdefault("aggro_radius", cfg.get("thresholds", {}).get("aggro_radius", 24.0))
        self.combat = Combat(self.inp, combat_cfg)
        self.policy = HelltidePolicy(cfg)
        self.route = parse_waypoints(cfg.get("route"))
        self.route_i = 0
        self.tick_s = float(cfg.get("loop", {}).get("tick_s", 0.1))
        self.max_runtime = float(cfg.get("loop", {}).get("max_runtime_s", 0) or 0)
        self.keys = cfg.get("keys", {})
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.telemetry = Telemetry(Path(log_dir) / f"run-{stamp}.csv")
        self._chest_tries = 0
        self._chest_label: str | None = None
        self._potion_t = 0.0
        self._prev_cinders: int | None = None
        self._hp_max: float | None = None
        self._last_mount_i: int | None = None

    # ------------------------------------------------------------------
    def run(self) -> None:
        fails = 0
        started = time.time()
        print(f"[d4bot] loop start (live={self.live})")
        try:
            while not self.safety.stopped:
                if self.max_runtime and time.time() - started > self.max_runtime:
                    self.safety.stop("max runtime reached")
                    break
                loop_t = time.time()
                try:
                    snap = self.reader.poll()
                    fails = 0
                except SnapshotError as exc:
                    fails += 1
                    print(f"[d4bot] snapshot failed ({fails}/3): {exc}")
                    if fails >= 3:
                        self.safety.stop("reader unhealthy")
                        break
                    time.sleep(0.3)
                    continue
                action = self._tick(snap)
                x = y = None
                here = self.nav.horizontal(snap.pos)
                if here:
                    x, y = here
                target = snap.nearest(self.combat.hostile_team, self.combat.aggro_radius)
                self.telemetry.write(
                    x=x,
                    y=y,
                    hp=snap.hp,
                    cinders=snap.cinders,
                    target_dist=target.dist if target else None,
                    action=action,
                )
                print(f"[d4bot] {action}")
                time.sleep(max(0.0, self.tick_s - (time.time() - loop_t)))
        except KeyboardInterrupt:
            self.safety.stop("ctrl-c")
        finally:
            try:
                self.nav.release()
            finally:
                self.inp.release_all()
            self.telemetry.close()
            print(f"[d4bot] stopped: {self.safety.stop_reason or 'done'}")

    # ------------------------------------------------------------------
    def _tick(self, snap: Snapshot) -> str:
        now = time.time()
        if self._prev_cinders is None:
            self._prev_cinders = snap.cinders
        if snap.hp is not None and snap.hp > 0:
            self._hp_max = max(self._hp_max or 0.0, snap.hp)
        if snap.hp is not None and snap.hp <= 0:
            self.safety.stop("death detected (hp <= 0)")
            return "dead"

        if self.policy.retreat_now(snap.hp, self._hp_max):
            return self._retreat(snap, now)

        chest = self.policy.next_chest(snap)
        if chest is not None:
            spot, dist = chest
            if dist <= self.policy.interact_radius:
                return self._try_open_chest(spot, snap)
            result = self.nav.step(snap.pos, (spot.x, spot.y), now)
            if result == "stuck":
                self.nav.nudge("A")
                return "unstuck (chest approach)"
            return f"chest->{spot.label} {dist:.0f}m"

        target = snap.nearest(self.combat.hostile_team, self.combat.engage_radius)
        if target is not None:
            act = self.combat.act(snap, now)
            return act or "target-close"

        if self.route:
            wp = self.route[self.route_i]
            if wp.kind == "mount" and self._last_mount_i != self.route_i:
                self.inp.tap_name(self.keys.get("mount", "R"))
                self._last_mount_i = self.route_i
            result = self.nav.step(snap.pos, wp, now)
            if result == "arrived":
                self.route_i = (self.route_i + 1) % len(self.route)
                return f"waypoint {wp.label or f'#{self.route_i}'} done"
            if result == "stuck":
                self.nav.nudge("A")
                return "unstuck (route)"
            return f"to {wp.label or f'#{self.route_i}'} ({wp.x:.0f},{wp.y:.0f})"

        return "idle"

    # ------------------------------------------------------------------
    def _retreat(self, snap: Snapshot, now: float) -> str:
        here = self.nav.horizontal(snap.pos)
        target = snap.nearest(self.combat.hostile_team, self.combat.aggro_radius)
        if here and target and target.pos is not None:
            ax, ay = self.nav.axes
            if max(ax, ay) < len(target.pos):
                ex, ey = float(target.pos[ax]), float(target.pos[ay])
                dx, dy = here[0] - ex, here[1] - ey
                d = (dx * dx + dy * dy) ** 0.5 or 1.0
                self.nav.step(snap.pos, (here[0] + dx / d * 8.0, here[1] + dy / d * 8.0), now)
        else:
            self.nav.release()
        if now - self._potion_t > 1.5:
            self.inp.tap_name(self.keys.get("potion", "Q"))
            self._potion_t = now
        hp = "?" if snap.hp is None else f"{snap.hp:.0f}"
        return f"retreat (hp={hp})"

    # ------------------------------------------------------------------
    def _try_open_chest(self, spot, snap: Snapshot) -> str:
        self.nav.release()
        self.inp.tap_name(self.keys.get("interact", "F"))
        time.sleep(0.45)
        try:
            after = self.reader.poll()
        except SnapshotError:
            return "chest: read failed"
        if (
            after.cinders is not None
            and self._prev_cinders is not None
            and after.cinders <= self._prev_cinders - self.policy.cost
        ):
            self.policy.mark_opened(spot)
            self._prev_cinders = after.cinders
            self._chest_tries = 0
            return f"opened {spot.label}"
        self._chest_tries += 1
        if self._chest_tries >= 4:
            self.policy.mark_opened(spot)
            self._chest_tries = 0
            return f"give up {spot.label}"
        return f"chest retry {self._chest_tries} ({spot.label})"
