"""Find the player's position triple by diffing a memory window around a known field.

Typical use: after the cinders chain is validated, the position vector lives in
the same player object. Two dumps of a window around the cinder field, taken
before and after walking, reveal which aligned float triples moved coherently.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TripleCandidate:
    offset: int                       # byte offset within the provided window
    before: tuple[float, float, float]
    after: tuple[float, float, float]
    delta: float                      # euclidean length of the change
    changed_components: int


def find_moved_triples(
    before: bytes,
    after: bytes,
    align: int = 4,
    min_delta: float = 0.05,
    max_delta: float = 200.0,
    min_changed_components: int = 1,
    max_value: float = 1e7,
    limit: int = 40,
) -> list[TripleCandidate]:
    """Return aligned float triples whose values moved coherently between dumps.

    A straight walk can change one axis (cardinal direction) or two (diagonal),
    so one changed component is enough. Ranking prefers fewer changed
    components: animations/rotations move all three, world position rarely does.
    """
    n = min(len(before), len(after))
    n -= n % 4
    if n < 12:
        return []
    b = np.frombuffer(before[:n], dtype="<f4")
    a = np.frombuffer(after[:n], dtype="<f4")
    if len(b) < 3:
        return []

    wb = np.lib.stride_tricks.sliding_window_view(b, 3)
    wa = np.lib.stride_tricks.sliding_window_view(a, 3)
    d = wa - wb

    finite = np.isfinite(d).all(axis=1) & np.isfinite(wb).all(axis=1)
    sane = (np.abs(wb) < max_value).all(axis=1)
    norm = np.linalg.norm(d, axis=1)
    changed = (np.abs(d) >= min_delta).sum(axis=1)

    ok = finite & sane & (norm >= min_delta) & (norm <= max_delta)
    ok &= changed >= min_changed_components

    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return []

    step = max(1, align // 4)
    idx = idx[idx % step == 0]

    # rank: fewer changed components first (position moves 1-2 axes; animation
    # floats move all three), then by larger displacement.
    order = sorted(
        idx,
        key=lambda i: (int(changed[i]), -float(norm[i])),
    )

    out: list[TripleCandidate] = []
    for i in order[:limit]:
        out.append(
            TripleCandidate(
                offset=int(i) * 4,
                before=tuple(float(v) for v in wb[i]),
                after=tuple(float(v) for v in wa[i]),
                delta=float(norm[i]),
                changed_components=int(changed[i]),
            )
        )
    return out
