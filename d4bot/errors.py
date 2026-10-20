"""Typed exceptions used across d4bot."""


class D4BotError(Exception):
    """Base class for bot failures."""


class MemError(D4BotError):
    """A Win32 memory operation failed."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class AccessDenied(MemError):
    """OpenProcess/ReadProcessMemory refused access (anti-cheat or privilege)."""


class SnapshotError(D4BotError):
    """Game state could not be read coherently (stale offsets, patch, etc.)."""


class ConfigError(D4BotError):
    """offsets.json / bot.json is invalid or incomplete."""


ACC_DENIED = 5
