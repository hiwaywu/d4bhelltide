"""d4bot — external read-only memory reader + Helltide farming assistant.

Hard constraints (see README.md):
  * OPEN_PROCESS is read-only (PROCESS_VM_READ). We never write game memory,
    never inject code, never call WriteProcessMemory.
  * No anti-cheat evasion. If the game denies read access, we stop.
"""

__version__ = "0.1.0"
