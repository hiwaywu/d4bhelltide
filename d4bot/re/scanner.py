"""Value scanning: find where a known number lives in the target process.

Workflow (the "Cheat Engine lite" loop):

    scan  -> change value in game -> filter -> change again -> filter -> ...

Candidates keep addresses plus last-seen raw values so filters compare without
rescanning the whole process. Scans use numpy; a few GB readable footprint
scans in seconds.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..win.memory import Process, Region

DTYPES = {
    "int32": np.dtype("<i4"),
    "uint32": np.dtype("<u4"),
    "int64": np.dtype("<i8"),
    "uint64": np.dtype("<u8"),
    "float": np.dtype("<f4"),
    "double": np.dtype("<f8"),
}
ITEMSIZE = {k: v.itemsize for k, v in DTYPES.items()}
CHUNK = 4 * 1024 * 1024


@dataclass
class Candidates:
    """A narrowed set of memory addresses and their last-seen raw bytes."""

    addrs: np.ndarray          # uint64, sorted ascending
    values: np.ndarray         # uint8 matrix, one row per address
    vtype: str

    def __len__(self) -> int:
        return len(self.addrs)

    @classmethod
    def empty(cls, vtype: str) -> "Candidates":
        return cls(
            np.empty(0, dtype=np.uint64),
            np.empty((0, ITEMSIZE[vtype]), dtype=np.uint8),
            vtype,
        )


class ValueScanner:
    def __init__(
        self,
        proc: Process,
        align: int = 4,
        chunk: int = CHUNK,
        include_images: bool = True,
        max_candidates: int = 4_000_000,
    ) -> None:
        self.proc = proc
        self.align = align
        self.chunk = chunk
        self.include_images = include_images
        self.max_candidates = max_candidates

    # -- region helpers -------------------------------------------------
    def _regions(self) -> list[Region]:
        regs = self.proc.readable_regions(min_size=0x1000)
        if not self.include_images:
            regs = [r for r in regs if not r.is_image]
        return regs

    def _iter_bytes(self, region: Region, chunk: int, retry: bool = True):
        """Yield (absolute_address, bytes). Splits on read failures."""
        cursor = region.base
        end = region.end
        while cursor < end:
            take = min(chunk, end - cursor)
            data = self.proc.try_read(cursor, take)
            if data:
                yield cursor, data
                cursor += take
            elif retry and take > 0x1000:
                # retry as two halves to route around a bad page
                half = take // 2
                for item in self._iter_bytes(Region(cursor, half, 0, 0, 0), half, retry):
                    yield item
                for item in self._iter_bytes(
                    Region(cursor + half, take - half, 0, 0, 0), take - half, retry
                ):
                    yield item
                cursor += take
            else:
                cursor += take

    # -- scanning -------------------------------------------------------
    def first_scan(
        self, value, vtype: str = "int32", tol: float | None = None, progress=None
    ) -> Candidates:
        if vtype not in DTYPES:
            raise ValueError(f"unsupported vtype {vtype!r}")
        dt = DTYPES[vtype]
        itemsize = dt.itemsize
        addrs: list[np.ndarray] = []
        vals: list[np.ndarray] = []
        total = 0
        scanned = 0
        target = np.array([value], dtype=dt)[0]

        for region in self._regions():
            for base, data in self._iter_bytes(region, self.chunk):
                scanned += len(data)
                usable = len(data) - (len(data) % itemsize)
                if usable <= 0:
                    continue
                arr = np.frombuffer(data, dtype=dt, count=usable // itemsize)
                if tol is not None and vtype in ("float", "double"):
                    mask = np.abs(arr.astype(np.float64) - float(value)) <= tol
                else:
                    mask = arr == target
                idx = np.flatnonzero(mask)
                if idx.size == 0:
                    continue
                found = idx.astype(np.uint64) * itemsize + np.uint64(base)
                if self.align > 1:
                    keep = (found % np.uint64(self.align)) == 0
                    found = found[keep]
                    idx = idx[keep]
                if found.size == 0:
                    continue
                raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, itemsize)[idx]
                addrs.append(found)
                vals.append(np.ascontiguousarray(raw))
                total += found.size
            if total > self.max_candidates:
                break
            if progress is not None:
                progress(scanned)

        if not addrs:
            return Candidates.empty(vtype)
        a = np.concatenate(addrs)
        v = np.concatenate(vals, axis=0)
        order = np.argsort(a)
        return Candidates(a[order], v[order], vtype)

    # -- batched reads ---------------------------------------------------
    def _read_many(self, cands: Candidates) -> tuple[np.ndarray, np.ndarray]:
        """Return (raw matrix, valid mask) for current candidate addresses."""
        addrs = cands.addrs
        itemsize = ITEMSIZE[cands.vtype]
        n = len(addrs)
        out = np.zeros((n, itemsize), dtype=np.uint8)
        valid = np.ones(n, dtype=bool)
        order = np.argsort(addrs)
        saddrs = addrs[order]
        i = 0
        while i < n:
            start = int(saddrs[i])
            j = i + 1
            while (
                j < n
                and int(saddrs[j]) - start < 262144
                and j - i < 4096
            ):
                j += 1
            span = int(saddrs[j - 1]) - start + itemsize
            data = self.proc.try_read(start, span) if span > 0 else None
            if data is not None and len(data) == span:
                buf = np.frombuffer(data, dtype=np.uint8)
                for k in range(i, j):
                    off = int(saddrs[k]) - start
                    if 0 <= off and off + itemsize <= len(buf):
                        out[order[k]] = buf[off : off + itemsize]
                    else:
                        valid[order[k]] = False
            else:
                for k in range(i, j):
                    raw = self.proc.try_read(int(saddrs[k]), itemsize)
                    if raw is None:
                        valid[order[k]] = False
                    else:
                        out[order[k]] = np.frombuffer(raw, dtype=np.uint8)
            i = j
        return out, valid

    # -- filters ---------------------------------------------------------
    def refresh(self, cands: Candidates) -> Candidates:
        if len(cands) == 0:
            return cands
        vals, valid = self._read_many(cands)
        return Candidates(cands.addrs[valid], vals[valid], cands.vtype)

    def filter_exact(
        self, cands: Candidates, value, tol: float | None = None
    ) -> Candidates:
        if len(cands) == 0:
            return cands
        dt = DTYPES[cands.vtype]
        cur, valid = self._read_many(cands)
        if tol is not None and cands.vtype in ("float", "double"):
            as_vals = np.frombuffer(cur[valid].tobytes(), dtype=dt)
            eq = np.abs(as_vals.astype(np.float64) - float(value)) <= tol
        else:
            target = np.array([value], dtype=dt).tobytes()
            eq = np.all(cur[valid] == np.frombuffer(target, dtype=np.uint8), axis=1)
        return Candidates(cands.addrs[valid][eq], cur[valid][eq], cands.vtype)

    def filter_changed(self, cands: Candidates) -> tuple[Candidates, Candidates]:
        if len(cands) == 0:
            return cands, cands
        cur, valid = self._read_many(cands)
        prev = cands.values[valid]
        changed = np.any(cur[valid] != prev, axis=1)
        keep_addrs = cands.addrs[valid]
        return (
            Candidates(keep_addrs[changed], cur[valid][changed], cands.vtype),
            Candidates(keep_addrs[~changed], cur[valid][~changed], cands.vtype),
        )
