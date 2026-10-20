"""Bot logic tests on synthetic snapshots — no game process required."""
import unittest

from d4bot.bot.combat import Combat
from d4bot.bot.helltide import HelltidePolicy
from d4bot.bot.nav import Navigator, Waypoint
from d4bot.config import DEFAULT_BOT, deep_merge
from d4bot.reader import Entity, Snapshot
from d4bot.win.input import Input, Safety


def make_cfg():
    cfg = deep_merge(DEFAULT_BOT, {})
    cfg["panic_vk"] = 0x7B
    return cfg


class NavTests(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()
        self.inp = Input(Safety(panic_vk=0x7B, require_foreground=False, dry_run=True), dry_run=True)
        self.nav = Navigator(self.inp, self.cfg)

    def test_moves_toward_target(self):
        result = self.nav.step((0.0, 0.0, 0.0), Waypoint(x=10.0, y=0.0, radius=1.0), now=1000.0)
        self.assertEqual(result, "moving")
        self.assertEqual(self.nav._held_combo, "D", "basis D points +x, target is +x")

    def test_arrives_within_radius(self):
        result = self.nav.step((9.5, 0.0, 0.0), Waypoint(x=10.0, y=0.0, radius=1.0), now=1000.0)
        self.assertEqual(result, "arrived")
        self.assertIsNone(self.nav._held_combo)

    def test_axes_mapping(self):
        cfg = deep_merge(make_cfg(), {"movement": {"axes": [0, 2]}})
        nav = Navigator(Input(Safety(require_foreground=False, dry_run=True), dry_run=True), cfg)
        self.assertEqual(nav.horizontal((1.0, 99.0, 2.0)), (1.0, 2.0))


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()
        self.inp = Input(Safety(panic_vk=0x7B, require_foreground=False, dry_run=True), dry_run=True)

    def _combat(self, skills):
        return Combat(self.inp, {"skills": skills, "aggro_radius": 24.0, "engage_radius": 14.0})

    def _snap(self, dist):
        e = Entity(addr=0x1000, pos=(dist, 0.0, 0.0), hp=100.0, team=1, dist=dist)
        return Snapshot(t=0.0, cinders=10, hp=100.0, pos=(0.0, 0.0, 0.0), entities=[e])

    SINGLE = [{"key": "1", "kind": "attack", "range": 9.0, "cooldown": 0.5}]

    def test_attacks_target_in_range(self):
        action = self._combat(self.SINGLE).act(self._snap(3.0), now=1000.0)
        self.assertEqual(action, "attack(1)@3.0m")

    def test_respects_cooldown(self):
        combat = self._combat(self.SINGLE)
        self.assertIsNotNone(combat.act(self._snap(3.0), now=1000.0))
        self.assertIsNone(combat.act(self._snap(3.0), now=1000.05), "single skill on cooldown")

    def test_out_of_aggro_does_not_attack(self):
        combat = self._combat(self.SINGLE)
        self.assertIsNone(combat.act(self._snap(30.0), now=1000.0))

    def test_target_within_aggro_but_out_of_range_does_not_attack(self):
        combat = self._combat(self.SINGLE)
        action = combat.act(self._snap(20.0), now=1000.0)
        self.assertIsNone(action)

    def test_buff_fires_even_without_target(self):
        combat = self._combat([{"key": "4", "kind": "buff", "range": 0.0, "cooldown": 10.0, "every": 10.0}])
        empty = Snapshot(t=0.0, cinders=10, hp=100.0, pos=(0.0, 0.0, 0.0), entities=[])
        self.assertEqual(combat.act(empty, now=1000.0), "buff(4)")
        self.assertIsNone(combat.act(empty, now=1005.0), "buff on its 10 s schedule")


class HelltideTests(unittest.TestCase):
    def setUp(self):
        cfg = make_cfg()
        cfg["chest_spots"] = [
            {"x": 5.0, "y": 0.0, "label": "A"},
            {"x": 50.0, "y": 0.0, "label": "B"},
        ]
        self.policy = HelltidePolicy(cfg)

    def _snap(self, cinders):
        return Snapshot(t=0.0, cinders=cinders, hp=100.0, pos=(0.0, 0.0, 0.0))

    def test_no_chest_below_cost(self):
        self.assertIsNone(self.policy.next_chest(self._snap(74)))

    def test_nearest_chest_at_cost(self):
        spot, dist = self.policy.next_chest(self._snap(75))
        self.assertEqual(spot.label, "A")
        self.assertAlmostEqual(dist, 5.0)

    def test_opened_chest_is_skipped(self):
        spot, _ = self.policy.next_chest(self._snap(75))
        self.policy.mark_opened(spot)
        nxt = self.policy.next_chest(self._snap(75))
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt[0].label, "B")

    def test_retreat_thresholds(self):
        self.assertTrue(self.policy.should_retreat(0.3))
        self.assertFalse(self.policy.should_retreat(0.0), "hp<=0 is death, handled elsewhere")
        self.assertTrue(self.policy.should_resume(0.8))


if __name__ == "__main__":
    unittest.main()
