"""Read-only access to a live Windows process's memory.

The only write-like operation anywhere in d4bot is synthetic keyboard/mouse
input (d4bot.win.input) — this module never writes to the target process.
"""
from __future__ import annotations

import ctypes
import struct
import time
from ctypes import wintypes
from dataclasses import dataclass

from ..errors import ACC_DENIED, AccessDenied, MemError

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

MEM_COMMIT = 0x1000
MEM_IMAGE = 0x1000000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
READABLE_MASK = 0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80

LIST_MODULES_ALL = 0x03


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wintypes.DWORD),
        ("__alignment1", wintypes.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("__alignment2", wintypes.DWORD),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION64),
    ctypes.c_size_t,
]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32FirstW.restype = wintypes.BOOL
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.restype = wintypes.BOOL
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

psapi.EnumProcessModulesEx.restype = wintypes.BOOL
psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HMODULE),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
]
psapi.GetModuleInformation.restype = wintypes.BOOL
psapi.GetModuleInformation.argtypes = [
    wintypes.HANDLE,
    wintypes.HMODULE,
    ctypes.POINTER(MODULEINFO),
    wintypes.DWORD,
]
psapi.GetModuleBaseNameW.restype = wintypes.DWORD
psapi.GetModuleBaseNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.HMODULE,
    wintypes.LPWSTR,
    wintypes.DWORD,
]


@dataclass(frozen=True)
class Region:
    base: int
    size: int
    protect: int
    state: int
    type: int

    @property
    def end(self) -> int:
        return self.base + self.size

    @property
    def readable(self) -> bool:
        if self.state != MEM_COMMIT:
            return False
        if self.protect & PAGE_GUARD:
            return False
        if self.protect == PAGE_NOACCESS:
            return False
        return bool(self.protect & READABLE_MASK)

    @property
    def is_image(self) -> bool:
        return self.type == MEM_IMAGE

    def contains(self, addr: int) -> bool:
        return self.base <= addr < self.end


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    base: int
    size: int

    @property
    def end(self) -> int:
        return self.base + self.size

    def contains(self, addr: int) -> bool:
        return self.base <= addr < self.end


def find_process(name_part: str = "diablo") -> list[tuple[int, str]]:
    """Return [(pid, exe_name)] whose image name contains name_part."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        raise MemError("CreateToolhelp32Snapshot failed", ctypes.get_last_error())
    found: list[tuple[int, str]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile
            if name_part.lower() in name.lower():
                found.append((int(entry.th32ProcessID), name))
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return found


def foreground_pid() -> int:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


class Process:
    """A handle to the target process, opened read-only."""

    def __init__(self, pid: int, handle: int, name: str = "") -> None:
        self.pid = pid
        self.handle = handle
        self.name = name
        self._regions: list[Region] | None = None
        self._modules: list[ModuleInfo] | None = None

    # -- construction -------------------------------------------------
    @classmethod
    def open(cls, pid: int, name: str = "", access: int | None = None) -> "Process":
        if access is None:
            access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
        handle = k32.OpenProcess(access, False, pid)
        if not handle and access != (PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION):
            # Retry with the weakest query right that still permits reads.
            access = PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION
            handle = k32.OpenProcess(access, False, pid)
        if not handle:
            code = ctypes.get_last_error()
            err = AccessDenied if code == ACC_DENIED else MemError
            raise err(
                f"OpenProcess(pid={pid}) failed ({code}): "
                + {5: "access denied (anti-cheat stripped handle or need elevation)",
                   87: "invalid pid"}.get(code, "see Win32 error"),
                code,
            )
        return cls(pid, int(handle), name)

    @classmethod
    def attach(cls, name_part: str = "diablo") -> "Process":
        matches = find_process(name_part)
        if not matches:
            raise MemError(f"no process matching {name_part!r} is running")
        if len(matches) > 1:
            raise MemError(
                "multiple matches: " + ", ".join(f"{n} (pid {p})" for p, n in matches)
            )
        pid, name = matches[0]
        return cls.open(pid, name)

    def close(self) -> None:
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = 0

    def __enter__(self) -> "Process":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- raw reads ----------------------------------------------------
    def read(self, addr: int, size: int) -> bytes:
        addr = int(addr)
        size = int(size)
        if size <= 0:
            return b""
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)
        )
        if not ok or got.value != size:
            code = ctypes.get_last_error()
            raise MemError(f"ReadProcessMemory({addr:#x}, {size}) failed ({code})", code)
        return buf.raw

    def try_read(self, addr: int, size: int) -> bytes | None:
        try:
            return self.read(addr, size)
        except MemError:
            return None

    def read_u32(self, addr: int) -> int:
        return struct.unpack("<I", self.read(addr, 4))[0]

    def read_i32(self, addr: int) -> int:
        return struct.unpack("<i", self.read(addr, 4))[0]

    def read_u64(self, addr: int) -> int:
        return struct.unpack("<Q", self.read(addr, 8))[0]

    def read_f32(self, addr: int) -> float:
        return struct.unpack("<f", self.read(addr, 4))[0]

    def read_f64(self, addr: int) -> float:
        return struct.unpack("<d", self.read(addr, 8))[0]

    # -- memory map ---------------------------------------------------
    def regions(self, refresh: bool = False) -> list[Region]:
        if self._regions is not None and not refresh:
            return self._regions
        out: list[Region] = []
        addr = 0
        mbi = MEMORY_BASIC_INFORMATION64()
        while True:
            rc = k32.VirtualQueryEx(
                self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
            )
            if rc == 0:
                break
            base = int(mbi.BaseAddress)
            size = int(mbi.RegionSize)
            if size == 0:
                break
            out.append(Region(base, size, int(mbi.Protect), int(mbi.State), int(mbi.Type)))
            nxt = base + size
            if nxt <= addr:
                break
            addr = nxt
        self._regions = out
        return out

    def readable_regions(self, min_size: int = 0x1000, refresh: bool = False) -> list[Region]:
        return [r for r in self.regions(refresh) if r.readable and r.size >= min_size]

    def region_containing(self, addr: int) -> Region | None:
        for r in self.regions():
            if r.contains(addr):
                return r
        return None

    # -- modules ------------------------------------------------------
    def modules(self, refresh: bool = False) -> list[ModuleInfo]:
        if self._modules is not None and not refresh:
            return self._modules
        out: list[ModuleInfo] = []
        try:
            hmods = (wintypes.HMODULE * 1024)()
            needed = wintypes.DWORD(0)
            if psapi.EnumProcessModulesEx(
                self.handle,
                hmods,
                ctypes.sizeof(hmods),
                ctypes.byref(needed),
                LIST_MODULES_ALL,
            ):
                count = needed.value // ctypes.sizeof(wintypes.HMODULE)
                for i in range(count):
                    mi = MODULEINFO()
                    if psapi.GetModuleInformation(
                        self.handle, hmods[i], ctypes.byref(mi), ctypes.sizeof(mi)
                    ):
                        name_buf = ctypes.create_unicode_buffer(260)
                        psapi.GetModuleBaseNameW(self.handle, hmods[i], name_buf, 260)
                        out.append(
                            ModuleInfo(name_buf.value, int(mi.lpBaseOfDll or 0), int(mi.SizeOfImage))
                        )
        except OSError:
            out = []
        if not out:
            out = self._modules_from_regions()
        self._modules = out
        return out

    def _modules_from_regions(self) -> list[ModuleInfo]:
        """Fallback: group contiguous MEM_IMAGE regions into modules."""
        images = sorted((r for r in self.regions() if r.is_image), key=lambda r: r.base)
        groups: list[list[Region]] = []
        for r in images:
            if groups and groups[-1][-1].end == r.base:
                groups[-1].append(r)
            else:
                groups.append([r])
        return [
            ModuleInfo("", g[0].base, g[-1].end - g[0].base) for g in groups
        ]

    def main_module(self, name_hint: str = "diablo") -> ModuleInfo:
        mods = self.modules()
        if not mods:
            raise MemError("no modules could be enumerated")
        for m in mods:
            if name_hint.lower() in m.name.lower():
                return m
        return mods[0]

    def is_alive(self) -> bool:
        return bool(self.handle)


def sleep_precise(seconds: float) -> None:
    time.sleep(seconds)
