# Build plan (kept in-repo so it survives context loss)

## Constraints

1. Read-only: `OpenProcess(PROCESS_VM_READ)` + `ReadProcessMemory` only.
2. No anti-cheat evasion. If access is denied in Phase 0, the memory path ends.
3. Panic key (F12) and foreground gate on every injection.
4. Offsets live in `config/offsets.json`, never in code.
5. Everything written from scratch; no copied bot code.

## Architecture

```
BOT  (loop / nav / combat / helltide / safety)
  ▲ Snapshot (typed values)
READER (chain -> typed snapshot, sanity guards)
  ▲ validated chains + offsets
RE LAB (value scanner, chain finder, struct probes)
  ▲ read-only bytes
WIN PLATFORM (process / memory / modules / input)
```

## Phases

| Phase | Deliverable | Gate | Effort |
|---|---|---|---|
| 0 | `tools/probe_attach.py` | one successful read from module memory | 10 min |
| 1 | win layer, scanner, chain finder, fake-target tests | suite green without the game | 1–2 days (done) |
| 2A | cinders chain | survives game restart; `watch.py` tracks it | 1–2 days |
| 2B | HP / resource | sane live values | 1–2 days |
| 2C | position xyz + WASD calibration | walking moves pos along expected axes | 1–2 days |
| 2D | entity manager (count, array, per-entity hp/pos/team) | nearest distance matches reality | 3–10 days ⚠️ |
| 3 | bot v1: input, nav, combat, chest policy, safety | dry-run on fake target + live dry run | 2–5 days |
| 4 | live tuning | one full loop: fill cinders → open 2 chests | 1–2 weeks |
| 5 | per-patch recovery | re-anchor in 30 min–2 h | ongoing |

Total ≈ 60–100 h. Entity decoding is the wildcard; if it drags, cut it with
minimap-based enemy detection (hybrid) instead of grinding.

## Milestones

- M0 probe result (PASS/FAIL)
- M1 suite green + synthetic chain found
- M2 live cinders chain validated across restart
- M3 `watch.py` shows cinders/hp/pos live
- M4 dry run of route + combat logic
- M5 first real Helltide loop with panic key
- M6 30-min unattended run
- M7 patch recovery drill

## Failure modes to respect

- Access denied → stop (no evasion).
- Stale offsets after patch → `validate` fails loudly; reader watchdog halts input.
- Wrong chain that "resolves" but reads garbage → min/max sanity guards catch it.
