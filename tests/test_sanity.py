import unittest

from d4bot.config import DEFAULT_BOT, deep_merge, load_offsets
from d4bot.errors import ConfigError
from d4bot.reader import FieldSpec, Offsets, resolve_chain

from tests.fake_target import FakeTarget
from d4bot.win.memory import Process


class ConfigTests(unittest.TestCase):
    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(ConfigError):
            load_offsets(
                {
                    "fields": {"cinders": {"static_off": "0x0", "offsets": ["0x8"], "type": "int32"}},
                    "required_fields": ["hp"],
                }
            )

    def test_unsupported_type_is_rejected(self):
        with self.assertRaises(ConfigError):
            FieldSpec.parse("x", {"static_off": "0x0", "type": "banana"})

    def test_deep_merge_keeps_defaults(self):
        merged = deep_merge(DEFAULT_BOT, {"thresholds": {"retreat_hp": 0.5}})
        self.assertEqual(merged["thresholds"]["retreat_hp"], 0.5)
        self.assertEqual(merged["thresholds"]["chest_cost"], 75)

    def test_hex_parsing(self):
        spec = FieldSpec.parse("x", {"static_off": "0x10", "offsets": ["0x8", 16], "type": "int32"})
        self.assertEqual(spec.static_off, 0x10)
        self.assertEqual(spec.offsets, [0x8, 16])


class SnapshotIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = FakeTarget()
        cls.proc = Process.open(cls.target.info["pid"])

    @classmethod
    def tearDownClass(cls):
        cls.proc.close()
        cls.target.close()

    def test_wrong_chain_does_not_silently_pass(self):
        off = Offsets(
            patch="test",
            module="",
            fields={
                "cinders": FieldSpec(
                    name="cinders",
                    static_off=0x100,  # wrong on purpose
                    offsets=[0x8],
                    type="int32",
                )
            },
            required=["cinders"],
            entity_manager=None,
            entity=None,
        )
        from d4bot.reader import Reader

        with self.assertRaises(Exception):
            reader = Reader(self.proc, off)
            reader.poll()


if __name__ == "__main__":
    unittest.main()
