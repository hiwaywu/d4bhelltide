"""Position-triple finder tests (pure numpy logic, no process needed)."""
import struct
import unittest

from d4bot.re.position import find_moved_triples


def make_buf(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


class PositionFinderTests(unittest.TestCase):
    def test_finds_horizontal_move(self):
        n = 32
        before = [float(i) for i in range(n)]
        after = list(before)
        # triple at index 8 moves by (10, 0, 0) — one axis, like a cardinal walk
        after[8] += 10.0
        cands = find_moved_triples(make_buf(before), make_buf(after))
        offsets = [c.offset for c in cands]
        self.assertIn(8 * 4, offsets)
        hit = next(c for c in cands if c.offset == 8 * 4)
        self.assertAlmostEqual(hit.delta, 10.0, places=3)
        self.assertEqual(hit.changed_components, 1)

    def test_single_component_change_is_detected(self):
        before = [0.0] * 16
        after = list(before)
        after[4] += 50.0  # one axis moves: valid walking signature
        cands = find_moved_triples(make_buf(before), make_buf(after))
        self.assertIn(4 * 4, [c.offset for c in cands])

    def test_identical_buffers_yield_nothing(self):
        buf = make_buf([1.0] * 32)
        self.assertEqual(find_moved_triples(buf, buf), [])

    def test_horizontal_move_ranks_above_three_axis_mover(self):
        before = [0.0] * 40
        after = list(before)
        after[6] += 9.0     # single-axis: like walking one direction
        after[20] += 5.0    # three-axis mover: animation-like
        after[21] += 5.0
        after[22] += 5.0
        cands = find_moved_triples(make_buf(before), make_buf(after))
        self.assertTrue(cands)
        top = cands[0]
        # the single float change appears in three overlapping windows (4,5,6)
        self.assertIn(top.offset, (4 * 4, 5 * 4, 6 * 4))
        self.assertEqual(top.changed_components, 1)
        self.assertAlmostEqual(top.delta, 9.0, places=3)

    def test_alignment_filter(self):
        before = [0.0] * 32
        after = list(before)
        for k in range(3):
            after[9 + k] += 3.0  # offset 36 bytes is 4-aligned but not 8-aligned
        cands = find_moved_triples(make_buf(before), make_buf(after), align=8)
        self.assertNotIn(9 * 4, [c.offset for c in cands])

    def test_large_delta_rejected(self):
        before = [0.0] * 16
        after = list(before)
        for k in range(3):
            after[2 + k] += 5000.0
        cands = find_moved_triples(make_buf(before), make_buf(after), max_delta=200.0)
        self.assertEqual(cands, [])

    def test_non_finite_values_are_excluded_from_results(self):
        import math

        before = make_buf([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        after = make_buf([float("nan"), 1.0, 1.0, 2.0, 2.0, 0.0])
        cands = find_moved_triples(before, after)
        for cand in cands:
            for value in cand.before + cand.after:
                self.assertTrue(math.isfinite(value), cand)

    def test_short_buffers(self):
        self.assertEqual(find_moved_triples(b"", b""), [])
        self.assertEqual(find_moved_triples(b"\x00" * 4, b"\x00" * 4), [])


if __name__ == "__main__":
    unittest.main()
