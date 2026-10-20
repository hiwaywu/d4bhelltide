"""Pointer-chain discovery: find a static path from the module to an address.

A chain is written as   base+static_off -> o1 -> o2 -> ... -> ok
meaning: read pointer at base+static_off and dereference; add o1; dereference;
add o2; ...; the value of interest finally lives at (last pointer + ok).

Search strategy: for a target field address A, find every memory word V with
0 <= A - V <= max_off  (V = enclosing object, A-V = field offset). If the word
that holds V is itself inside the module image it is a static root; otherwise
we grow one level: find words pointing at that word's location, and so on.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..win.memory import Process, Region
from .scanner import CHUNK


@dataclass
class Chain:
    static_base: int          # absolute base that static_off is relative to
    static_off: int
    offsets: list[int]        # deepest -> shallowest (reader order)
    depth: int = 0

    def describe(self) -> str:
        steps = " -> ".join(f"{o:#x}" for o in self.offsets)
        return f"static+{self.static_off:#x} -> {steps}"


def _is_static(loc: int, ranges: list[tuple[int, int]]) -> tuple[bool, int]:
    for base, size in ranges:
        if base <= loc < base + size:
            return True, base
    return False, 0


class ChainFinder:
    def __init__(
        self,
        proc: Process,
        static_ranges: list[tuple[int, int]] | None = None,
        max_off: int = 0x2000,
        max_depth: int = 4,
        max_frontier: int = 4096,
        max_hits: int = 400_000,
        chunk: int = CHUNK,
    ) -> None:
        self.proc = proc
        self.max_off = max_off
        self.max_depth = max_depth
        self.max_frontier = max_frontier
        self.max_hits = max_hits
        self.chunk = chunk
        if static_ranges is None:
            static_ranges = self._module_ranges()
        if not static_ranges:
            raise ValueError("no static ranges (module images) found")
        self.static_ranges = static_ranges

    def _module_ranges(self) -> list[tuple[int, int]]:
        mod = self.proc.main_module()
        ranges = [(mod.base, mod.size)]
        for r in self.proc.regions():
            if r.is_image and r.base >= mod.base and r.end <= mod.end:
                ranges.append((r.base, r.size))
        return ranges

    # -- low-level pointer scan -------------------------------------------
    def _iter_qwords(self, region: Region):
        cursor = region.base
        while cursor < region.end:
            take = min(self.chunk, region.end - cursor)
            take -= take % 8
            if take <= 0:
                break
            data = self.proc.try_read(cursor, take)
            if data:
                yield cursor, data
            cursor += take

    def scan_points(self, points: list[int], budget: int | None = None) -> list[tuple[int, int, int, int]]:
        """Return [(pointer_location, object_base, field_offset, matched_point)]."""
        if not points:
            return []
        pts = np.unique(np.asarray(points, dtype=np.uint64))
        out: list[tuple[int, int, int, int]] = []
        remaining = budget if budget is not None else self.max_hits
        for region in self.proc.readable_regions(min_size=0x1000):
            for base, data in self._iter_qwords(region):
                usable = len(data) - (len(data) % 8)
                if usable <= 0:
                    continue
                arr = np.frombuffer(data, dtype="<u8", count=usable // 8)
                # V (object base) <= point (field address), offset = point - V
                idx = np.searchsorted(pts, arr, side="left")
                ok_idx = np.flatnonzero(idx < len(pts))
                if ok_idx.size == 0:
                    continue
                matched = pts[idx[ok_idx]]
                off = matched - arr[ok_idx]
                good_pos = np.flatnonzero((off <= self.max_off) & ((off & 3) == 0))
                if good_pos.size == 0:
                    continue
                for pos in good_pos:
                    k = int(ok_idx[pos])
                    out.append((base + k * 8, int(arr[k]), int(off[pos]), int(matched[pos])))
                    remaining -= 1
                    if remaining <= 0:
                        return out
        return out

    # -- chain search ------------------------------------------------------
    def find(self, target: int, validate: bool = True) -> list[Chain]:
        from ..reader import resolve_chain

        frontier: dict[int, list[int]] = {int(target): []}
        results: list[Chain] = []
        seen: set[tuple[int, tuple[int, ...]]] = set()

        for depth in range(1, self.max_depth + 1):
            hits = self.scan_points(list(frontier.keys()))
            next_frontier: dict[int, list[int]] = {}
            for loc, base, off, point in hits:
                path = frontier.get(point)
                if path is None:
                    continue
                new_path = path + [off]
                is_static, sbase = _is_static(loc, self.static_ranges)
                if is_static:
                    offsets = list(reversed(new_path))
                    key = (loc - sbase, tuple(offsets))
                    if key in seen:
                        continue
                    seen.add(key)
                    chain = Chain(
                        static_base=sbase,
                        static_off=loc - sbase,
                        offsets=offsets,
                        depth=depth,
                    )
                    if validate:
                        ok = False
                        for attempt in range(2):
                            try:
                                ok = (
                                    resolve_chain(
                                        self.proc, sbase, chain.static_off, chain.offsets
                                    )
                                    == target
                                )
                                break
                            except Exception:
                                # transient read hiccup: retry once before dropping
                                if attempt == 0:
                                    time.sleep(0.02)
                        if not ok:
                            continue
                    results.append(chain)
                else:
                    prev = next_frontier.get(loc)
                    if prev is None or len(new_path) < len(prev):
                        next_frontier[loc] = new_path
            if not next_frontier:
                break
            if len(next_frontier) > self.max_frontier:
                items = sorted(next_frontier.items(), key=lambda kv: len(kv[1]))
                next_frontier = dict(items[: self.max_frontier])
            frontier = next_frontier

        results.sort(key=lambda c: (c.depth, c.static_off))
        return results
