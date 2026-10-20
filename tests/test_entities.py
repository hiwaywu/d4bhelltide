"""Entity-list decoding against the synthetic target's planted manager."""
import unittest

from d4bot.reader import Reader, load_offsets
from d4bot.win.memory import Process

from tests.fake_target import FakeTarget


def build_offsets(info: dict, module_base: int, with_entities: bool = True) -> dict:
    root = hex(info["root"] - module_base)
    doc = {
        "patch": "synthetic",
        "module": "",
        "required_fields": ["cinders", "position"],
        "fields": {
            "cinders": {"static_off": root, "offsets": ["0x10", "0x8"], "type": "int32", "min": 0, "max": 10**9},
            "hp": {"static_off": root, "offsets": ["0x10", "0x10"], "type": "float", "min": 0.0, "max": 10**6},
            "position": {"static_off": root, "offsets": ["0x10", "0x18"], "type": "f32x3", "axes": [0, 1]},
        },
        "entity_manager": {
            "static_off": root,
            "offsets": ["0x0"],
            "count_off": "0x20",
            "array_off": "0x28",
            "mode": "pointer_array",
            "stride": 8,
            "max_count": 64,
        },
        "entity": {"pos_off": "0x0", "hp_off": "0x10", "team_off": "0x14"},
    }
    if not with_entities:
        doc.pop("entity_manager")
        doc.pop("entity")
    return doc


class EntityReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = FakeTarget()
        cls.proc = Process.open(cls.target.info["pid"])
        module = cls.proc.main_module()
        cls.reader = Reader(cls.proc, load_offsets(build_offsets(cls.target.info, module.base)))

    @classmethod
    def tearDownClass(cls):
        cls.proc.close()
        cls.target.close()

    def test_snapshot_has_base_fields(self):
        snap = self.reader.poll()
        self.assertEqual(snap.cinders, 424242)
        self.assertAlmostEqual(snap.hp, 61.5, places=3)
        self.assertEqual(len(snap.pos), 3)
        self.assertAlmostEqual(snap.pos[0], 0.0)

    def test_entity_list_decoded(self):
        snap = self.reader.poll()
        self.assertEqual(len(snap.entities), 2)
        self.assertEqual({e.team for e in snap.entities}, {1})
        by_addr = {e.addr: e for e in snap.entities}
        e1 = by_addr[self.target.info["ent1"]]
        e2 = by_addr[self.target.info["ent2"]]
        self.assertAlmostEqual(e1.hp, 50.0)
        self.assertAlmostEqual(e1.dist, 10.0)
        self.assertAlmostEqual(e2.hp, 0.0)
        self.assertAlmostEqual(e2.dist, 5.0)

    def test_nearest_skips_dead_entities(self):
        snap = self.reader.poll()
        nearest = snap.nearest()
        self.assertIsNotNone(nearest)
        self.assertAlmostEqual(nearest.dist, 10.0, msg="hp<=0 entity must be skipped")

    def test_dead_entities_are_kept_in_list(self):
        snap = self.reader.poll()
        hp_values = sorted(e.hp for e in snap.entities)
        self.assertEqual(hp_values, [0.0, 50.0])


class EntityAbsentTests(unittest.TestCase):
    def test_no_entity_config_means_no_entities(self):
        target = FakeTarget()
        proc = Process.open(target.info["pid"])
        try:
            module = proc.main_module()
            reader = Reader(proc, load_offsets(build_offsets(target.info, module.base, with_entities=False)))
            snap = reader.poll()
            self.assertEqual(snap.entities, [])
            self.assertEqual(snap.cinders, 424242)
        finally:
            proc.close()
            target.close()


if __name__ == "__main__":
    unittest.main()
