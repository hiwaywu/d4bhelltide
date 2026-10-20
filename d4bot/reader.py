"""Turn validated pointer chains into typed game state (a Snapshot)."""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Any

from .errors import ConfigError, SnapshotError
from .win.memory import ModuleInfo, Process

TYPES = {"int32", "uint32", "int64", "uint64", "float", "double", "f32x2", "f32x3"}


def h(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, str):
        return int(value, 0)
    return int(value)


@dataclass
class FieldSpec:
    name: str
    static_off: int
    offsets: list[int]
    type: str = "int32"
    min: float | None = None
    max: float | None = None
    axes: list[int] | None = None

    @classmethod
    def parse(cls, name: str, raw: dict) -> "FieldSpec":
        if "static_off" not in raw:
            raise ConfigError(f"field {name}: missing static_off")
        ftype = raw.get("type", "int32")
        if ftype not in TYPES:
            raise ConfigError(f"field {name}: unsupported type {ftype!r}")
        offsets = [h(o) for o in raw.get("offsets", [])]
        return cls(
            name=name,
            static_off=h(raw["static_off"]),
            offsets=offsets,
            type=ftype,
            min=raw.get("min"),
            max=raw.get("max"),
            axes=raw.get("axes"),
        )


@dataclass
class Offsets:
    patch: str
    module: str
    fields: dict[str, FieldSpec]
    required: list[str]
    entity_manager: dict | None
    entity: dict | None

    def has(self, name: str) -> bool:
        return name in self.fields

    def get(self, name: str) -> FieldSpec | None:
        return self.fields.get(name)


def load_offsets(doc: dict) -> Offsets:
    fields = {
        name: FieldSpec.parse(name, raw)
        for name, raw in (doc.get("fields") or {}).items()
    }
    required = list(doc.get("required_fields") or [])
    for name in required:
        if name not in fields:
            raise ConfigError(f"required field {name!r} not present in fields")
    return Offsets(
        patch=doc.get("patch", ""),
        module=doc.get("module", "Diablo IV.exe"),
        fields=fields,
        required=required,
        entity_manager=doc.get("entity_manager"),
        entity=doc.get("entity"),
    )


# ---------------------------------------------------------------------------
# chain resolution
# ---------------------------------------------------------------------------
def resolve_chain(proc: Process, base: int, static_off: int, offsets: list[int]) -> int:
    """Walk base+static_off -> offsets... and return the final address.

    Semantics: dereference the root, then for every offset except the last,
    add it, dereference; the last offset is added to the final pointer and the
    value lives there. (Matches the classic CE display order.)
    """
    if not offsets:
        raise SnapshotError("empty offset chain")
    p = proc.read_u64(base + static_off)
    for off in offsets[:-1]:
        p = proc.read_u64(p + off)
    return p + offsets[-1]


def read_typed(proc: Process, addr: int, ftype: str):
    if ftype == "int32":
        return struct.unpack("<i", proc.read(addr, 4))[0]
    if ftype == "uint32":
        return struct.unpack("<I", proc.read(addr, 4))[0]
    if ftype == "int64":
        return struct.unpack("<q", proc.read(addr, 8))[0]
    if ftype == "uint64":
        return struct.unpack("<Q", proc.read(addr, 8))[0]
    if ftype == "float":
        return struct.unpack("<f", proc.read(addr, 4))[0]
    if ftype == "double":
        return struct.unpack("<d", proc.read(addr, 8))[0]
    if ftype == "f32x2":
        return struct.unpack("<2f", proc.read(addr, 8))
    if ftype == "f32x3":
        return struct.unpack("<3f", proc.read(addr, 12))
    raise ConfigError(f"unsupported type {ftype!r}")


def read_field(proc: Process, base: int, spec: FieldSpec):
    addr = resolve_chain(proc, base, spec.static_off, spec.offsets)
    return read_typed(proc, addr, spec.type)


# ---------------------------------------------------------------------------
# snapshots
# ---------------------------------------------------------------------------
@dataclass
class Entity:
    addr: int
    pos: tuple[float, ...] | None = None
    hp: float | None = None
    team: int | None = None
    kind: int | None = None
    dist: float | None = None


@dataclass
class Snapshot:
    t: float
    cinders: int | None = None
    hp: float | None = None
    resource: float | None = None
    pos: tuple[float, ...] | None = None
    entities: list[Entity] = field(default_factory=list)
    missing: dict[str, str] = field(default_factory=dict)

    def nearest(self, hostile_team: int | None = None, radius: float = 1e9) -> Entity | None:
        best: Entity | None = None
        bestd = radius
        for e in self.entities:
            if e.dist is None or e.hp is None:
                continue
            if e.hp <= 0:
                continue
            if hostile_team is not None and e.team is not None and e.team == hostile_team:
                continue
            if e.dist <= bestd:
                best, bestd = e, e.dist
        return best


class Reader:
    def __init__(self, proc: Process, offsets: Offsets, module: ModuleInfo | None = None):
        self.proc = proc
        self.offsets = offsets
        self.module = module or proc.main_module(offsets.module)
        self._check_binding()

    def _check_binding(self) -> None:
        off = self.offsets
        self.base = self.module.base
        # a quick smoke check: resolve the first required field
        for name in off.required:
            spec = off.fields[name]
            try:
                resolve_chain(self.proc, self.base, spec.static_off, spec.offsets)
            except Exception as exc:
                raise SnapshotError(
                    f"required field {name!r} did not resolve on this build: {exc}"
                ) from exc

    def _read_named(self, name: str, snap: Snapshot) -> None:
        spec = self.offsets.fields.get(name)
        if spec is None:
            return
        try:
            value = read_field(self.proc, self.base, spec)
        except Exception as exc:
            snap.missing[name] = str(exc)
            return
        if spec.min is not None and isinstance(value, (int, float)) and value < spec.min:
            snap.missing[name] = f"below minimum ({value})"
            return
        if spec.max is not None and isinstance(value, (int, float)) and value > spec.max:
            snap.missing[name] = f"above maximum ({value})"
            return
        if name == "cinders":
            snap.cinders = int(value)
        elif name == "hp":
            snap.hp = float(value)
        elif name == "resource":
            snap.resource = float(value)
        elif name == "position":
            snap.pos = tuple(float(v) for v in value)

    def _read_entities(self, snap: Snapshot) -> None:
        mgr = self.offsets.entity_manager
        ent = self.offsets.entity
        if not mgr or not ent:
            return
        try:
            manager = resolve_chain(
                self.proc, self.base, h(mgr["static_off"]), [h(o) for o in mgr.get("offsets", [])]
            )
            count_type = str(mgr.get("count_type", "int32"))
            count = int(read_typed(self.proc, manager + h(mgr.get("count_off", 0)), count_type))
            count = max(0, min(count, int(mgr.get("max_count", 512))))
            array_ptr = self.proc.read_u64(manager + h(mgr.get("array_off", 0)))
            mode = mgr.get("mode", "pointer_array")
            stride = int(mgr.get("stride", 8))
            for i in range(count):
                if mode == "inline":
                    eaddr = array_ptr + i * stride
                else:
                    eaddr = self.proc.read_u64(array_ptr + i * stride)
                if eaddr < 0x10000:
                    continue
                try:
                    e_pos_raw = read_typed(self.proc, eaddr + h(ent["pos_off"]), "f32x3")
                    e_hp = read_typed(self.proc, eaddr + h(ent["hp_off"]), "float")
                    e_team = (
                        read_typed(self.proc, eaddr + h(ent["team_off"]), "int32")
                        if "team_off" in ent
                        else None
                    )
                    e_kind = (
                        read_typed(self.proc, eaddr + h(ent["type_off"]), "int32")
                        if "type_off" in ent
                        else None
                    )
                except Exception:
                    continue
                e = Entity(addr=eaddr, pos=e_pos_raw, hp=e_hp, team=e_team, kind=e_kind)
                if snap.pos is not None:
                    e.dist = _dist(snap.pos, e_pos_raw)
                snap.entities.append(e)
        except Exception as exc:
            snap.missing["entities"] = str(exc)

    def poll(self) -> Snapshot:
        snap = Snapshot(t=time.time())
        for name in ("cinders", "hp", "resource", "position"):
            if self.offsets.has(name):
                self._read_named(name, snap)
        for name in self.offsets.required:
            if name in snap.missing:
                raise SnapshotError(
                    f"required field {name!r} unreadable: {snap.missing[name]}"
                )
        if snap.pos is not None:
            self._read_entities(snap)
            if snap.pos is not None:
                for e in snap.entities:
                    if e.dist is None and e.pos is not None:
                        e.dist = _dist(snap.pos, e.pos)
        return snap


def _dist(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
