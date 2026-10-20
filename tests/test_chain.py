import unittest

from d4bot.reader import read_typed, resolve_chain
from d4bot.re.pointer_scan import ChainFinder
from d4bot.win.memory import Process

from tests.fake_target import FakeTarget


class ChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = FakeTarget()
        cls.proc = Process.open(cls.target.info["pid"])
        info = cls.target.info
        cls.root = info["root"]
        cls.finder = ChainFinder(
            cls.proc,
            static_ranges=[(info["root"], info["root_size"])],
            max_depth=3,
        )

    @classmethod
    def tearDownClass(cls):
        cls.proc.close()
        cls.target.close()

    def test_finds_chain_to_cinders(self):
        target = self.target.info["cinders_addr"]
        chains = self.finder.find(target)
        self.assertTrue(chains, "expected at least one chain")
        specs = [(c.static_off, tuple(c.offsets)) for c in chains]
        self.assertIn((0x0, (0x10, 0x8)), specs)

    def test_chain_resolves_and_reads_value(self):
        target = self.target.info["cinders_addr"]
        chain = next(
            c for c in self.finder.find(target) if c.offsets == [0x10, 0x8]
        )
        addr = resolve_chain(self.proc, chain.static_base, chain.static_off, chain.offsets)
        self.assertEqual(addr, target)
        self.assertEqual(read_typed(self.proc, addr, "int32"), self.target.info["cinders"])

    def test_no_valid_chain_for_bogus_target(self):
        chains = self.finder.find(0xDEADBEEF0000)
        self.assertEqual(chains, [])


if __name__ == "__main__":
    unittest.main()
