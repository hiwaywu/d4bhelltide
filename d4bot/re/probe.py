"""Human-facing inspection helpers: hexdumps and field-shape probing."""
from __future__ import annotations

import struct

from ..win.memory import Process


def hexdump(proc: Process, addr: int, size: int = 256, width: int = 16) -> str:
    try:
        data = proc.read(addr, size)
    except Exception as exc:  # pragma: no cover - diagnostic path
        return f"<unreadable {addr:#x}: {exc}>"
    lines = []
    for off in range(0, len(data), width):
        row = data[off : off + width]
        hexpart = " ".join(f"{b:02x}" for b in row)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        lines.append(f"{addr + off:#014x}  {hexpart:<{width * 3}}  {asciipart}")
    return "\n".join(lines)


def qwords(proc: Process, addr: int, count: int = 8) -> str:
    """Show qwords near an address annotated as pointer / int / float."""
    try:
        data = proc.read(addr, count * 8)
    except Exception as exc:  # pragma: no cover
        return f"<unreadable {addr:#x}: {exc}>"
    lines = []
    for i in range(0, len(data), 8):
        raw = data[i : i + 8]
        q = struct.unpack("<Q", raw)[0]
        i32, u32 = struct.unpack("<iI", raw[:4])
        f32 = struct.unpack("<f", raw[:4])[0]
        region = proc.region_containing(q)
        ptr = f"ptr->{q:#x}" if region and q > 0x10000 else "not-a-ptr"
        lines.append(
            f"{addr + i:#014x}  {q:#018x}  {i32:>12d}  {u32:>10d}  {f32:>12.4f}  {ptr}"
        )
    return "\n".join(lines)


def scan_summary(addr: int, region_hint: str = "") -> str:
    return f"{addr:#x} {region_hint}".strip()
