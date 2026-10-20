# d4bot — read-only Diablo 4 Helltide assistant

External, **read-only** memory reader plus a farming loop for personal Helltide
runs on Windows. Built from scratch (no copied bot code). Pure Python 3.12 +
numpy; no DLL injection, no drivers, no memory writes.

> **Read this first.** Automation violates Blizzard's EULA and bans are real
> and account-wide. That risk is yours. This project deliberately does **not**
> include anti-cheat evasion: if the game denies read access, the memory path
> stops there (that is a feature, not a bug). Never run random "free D4 bots"
> from the internet — that is how accounts and credentials get stolen.

## Status

| Part | State |
|---|---|
| Win32 read-only memory layer (process, regions, modules) | ✅ done, tested |
| Value scanner (int/float, diff filters, batched reads) | ✅ done, tested |
| Pointer-chain finder (validated chains, restart-test workflow) | ✅ done, tested |
| Reader (chains → typed snapshot, sanity guards) | ✅ done, tested |
| Bot loop (nav, combat rotation, chest policy, retreat, panic key) | ✅ built + integration-tested (synthetic loop) |
| **Actual game offsets (cinders/HP/pos/entities)** | ❌ **requires the game — Phase 2** |

Everything above is verified against a synthetic target process
(`tests/fake_target.py`) and synthetic snapshots: **70 tests** cover the memory
layer, scanner, chain finder, reader (including entity-list decoding), CLI
wiring against a foreign process, the bot loop (chest open, retreat, death
stop, focus-loss pause, missing-position guard), the input safety gate, route
recording, diagnostics, and the position triple finder. You can run the whole
suite at home without Diablo 4 to confirm your install is healthy.

## Requirements

- Windows 10/11 x64
- Python **3.12 x64** (64-bit Python is mandatory: the game is 64-bit)
- numpy (`pip install -r requirements.txt`)
- Diablo IV PC client (needed only for Phase 0 and Phase 2 onwards)

## Quick start

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

REM 1) health check without the game (should say OK)
python -m unittest discover -s tests -t . -v

REM 2) Phase 0: with the game running and logged in
python tools\probe_attach.py
```

If the probe prints `PASS`, continue with `BUILD_BOOK.md` → Phase 2.

## Command reference

| Command | What it does |
|---|---|
| `python tools\probe_attach.py` | attach test: can we read the game read-only? |
| `python tools\hunt_value.py --type int32 --value 812` | interactive value scan (Cheat-Engine-lite loop) |
| `python tools\hunt_chain.py --addr 0x...` | find static pointer chains; prints paste-ready JSON |
| `python tools\hunt_pos.py` | find the position f32x3: snapshots a window around cinders before/after a walk |
| `python tools\watch.py` | live snapshot: cinders, hp, position, entities |
| `python tools\record_route.py` | walk your loop; Enter drops waypoints, `c` drops chest spots, saves to bot.json |
| `python tools\doctor.py` | one-command setup check: bitness, numpy, configs, game presence |
| `python tools\dump.py --addr 0x...` | hexdump / qword inspector |
| `python -m d4bot validate` | check `config/offsets.json` field by field against the live game |
| `python -m d4bot calibrate --live --write` | measure WASD→world basis, save to `config/bot.json` |
| `python -m d4bot run` | bot loop, **dry-run** (logs intentions, sends no input) |
| `python -m d4bot run --live` | bot loop with real input (requires game foreground) |

Every command also accepts `--pid N` to attach by process id (used by the
integration tests; handy if the executable name differs).

## Safety design

- **Read-only by construction**: `OpenProcess(PROCESS_VM_READ)` and
  `ReadProcessMemory` only. `WriteProcessMemory` is not present anywhere.
- **Panic key `F12`**: checked before every input injection and every loop tick.
- **Foreground gate**: input is refused unless the game window is focused.
- **Reader watchdog**: 3 consecutive unreadable snapshots → stop. The bot never
  acts on garbage state (stale offsets after a patch fail loudly instead).
- **Dry-run default**: `run` sends nothing unless you pass `--live`.

## Layout

```
d4bot/
  win/memory.py      process discovery, regions, modules, read-only RPM
  win/input.py       SendInput keyboard/mouse + Safety gate
  re/scanner.py      value scanning / diff filters
  re/pointer_scan.py pointer-chain finder (validated)
  re/probe.py        hexdumps, qword annotations
  reader.py          chain -> typed snapshot + sanity checks
  bot/loop.py        orchestrator (travel/fight/chest/retreat)
  bot/nav.py         WASD world-space routing, stuck detection
  bot/combat.py      config-driven rotation (self-centred skills in v1)
  bot/helltide.py    cinder threshold, chest spots, retreat policy
  bot/telemetry.py   CSV run logs
tools/               standalone CLIs (probe, hunt_value, hunt_chain, watch, dump)
config/offsets.json  per-patch chains (empty until Phase 2)
config/bot.json      keybinds, thresholds, route, chest spots
tests/               fake-target harness + unit tests (no game needed)
```

## Known limitations (v1)

- **Self-centred/AoE skills only** for combat. Aimed/ranged skills need mouse
  aiming (world→screen projection), which is Phase 3.5 work.
- **Chest opening** = one interact-key press at the spot; some chests may need
  a click or a second press — tune in Phase 4.
- **No loot pickup**, no vendor/salvage loop, no boss events (by design).
- Entity decoding depends on the structures found on *your* build; the config
  supports pointer-array and inline modes but the layout must be discovered.

## Documentation

- `BUILD_BOOK.md` — the at-home runbook, phase by phase
- `OFFSETS-HUNTING.md` — the RE runbook and `offsets.json` semantics
- `PLAN.md` — architecture, phases, effort estimates

Personal use only. Not for distribution. Do not sell, publish, or farm
accounts with this.
