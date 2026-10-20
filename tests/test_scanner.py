import os
import sys
import unittest

from d4bot.re.scanner import Candidates, ValueScanner
from d4bot.win.memory import Process

from tests.fake_target import FakeTarget


class ScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = FakeTarget()
        cls.proc = Process.open(cls.target.info["pid"])
        cls.scanner = ValueScanner(cls.proc, max_candidates=2_000_000)

    @classmethod
    def tearDownClass(cls):
        cls.proc.close()
        cls.target.close()

    def test_finds_planted_int32(self):
        cands = self.scanner.first_scan(424242, "int32")
        addrs = {int(a) for a in cands.addrs}
        self.assertIn(self.target.info["cinders_addr"], addrs)
        self.assertLess(len(addrs), 50, "value should be nearly unique in a fresh process")

    def test_exact_filter_keeps_the_value(self):
        cands = self.scanner.first_scan(424242, "int32")
        filtered = self.scanner.filter_exact(cands, 424242)
        self.assertIn(int(self.target.info["cinders_addr"]), {int(a) for a in filtered.addrs})

    def test_exact_filter_rejects_wrong_value(self):
        cands = self.scanner.first_scan(424242, "int32")
        filtered = self.scanner.filter_exact(cands, 111111)
        self.assertEqual(len(filtered), 0)

    def test_float_scan(self):
        cands = self.scanner.first_scan(61.5, "float")
        addrs = {int(a) for a in cands.addrs}
        self.assertIn(self.target.info["hp_addr"], addrs)

    def test_changed_filter_detects_nothing_for_static_value(self):
        cands = self.scanner.first_scan(424242, "int32")
        changed, unchanged = self.scanner.filter_changed(cands)
        self.assertEqual(len(changed), 0)

    def test_unreadable_candidates_are_dropped(self):
        addrs = [0xDEADBEEF0000, 0x10]
        import numpy as np

        values = np.zeros((2, 4), dtype=np.uint8)
        bogus = Candidates(np.array(addrs, dtype=np.uint64), values, "int32")
        self.assertEqual(len(self.scanner.filter_exact(bogus, 424242)), 0)


if __name__ == "__main__":
    unittest.main()
