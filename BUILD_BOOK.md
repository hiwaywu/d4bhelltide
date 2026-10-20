# BUILD BOOK — the at-home runbook

This book makes the project self-contained: **any** AI assistant (or you,
manually) can continue from it without this chat's context. Read
`README.md` first, then work through the phases in order.

If an assistant is helping you at home, give it this instruction:

> Read `README.md`, `BUILD_BOOK.md`, and `OFFSETS-HUNTING.md`. Run
> `python -m unittest discover -s tests -t . -v` first. Then continue this
> project at the phase described below. Ask me for the in-game observations you
> need, one step at a time.

---

## 0. Prerequisites checklist

- [ ] Windows 10/11, x64
- [ ] Diablo IV PC client installed and **logged in** (needed from Phase 0 on)
- [ ] Python 3.12 **x64** (`python -c "import struct; print(struct.calcsize('P'))"` must print `8`)
- [ ] A Helltide-eligible character (WT3+) for Phase 2
- [ ] `F12` panic key reachable at all times during live runs

## 1. Install and health check

```bat
git clone https://github.com/hiwaywu/d4bhelltide.git
cd d4bhelltide
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
```

Health check passes if the final line is `OK` (42 tests). This runs against a
synthetic target process — **the game is not needed** for this step. If it
fails, stop and fix the environment before touching the game.

## 2. Phase 0 — attach gate (2 minutes)

Start Diablo IV, log in, then:

```bat
python tools\probe_attach.py
```

Expected on success:

```
found: pid=12345 name=Diablo IV.exe
module   : Diablo IV.exe
base     : 0x7ff6...
MZ header: b'MZ'
PASS - read-only memory access works. Proceed to Phase 2A (cinder hunt).
```

- **`NO GAME`** → the process name check failed; make sure the game is running.
- **`BLOCKED: OpenProcess ... access denied`** → the anti-cheat refused a read
  handle. Per project rules we stop here and switch to the vision approach; we
  do **not** try to bypass the protection.

Record the output — it goes in your session report.

## 3. Phase 2A — cinders (the first real chain)

You need a Helltide where you can gain cinders. Have the cinder counter
visible (top-right).

1. Note the current value, e.g. `812`.
2. Start the scanner:

   ```bat
   python tools\hunt_value.py --type int32 --value 812
   ```

3. Play: kill demons / complete the event until the counter changes, e.g. `843`.
4. In the scan prompt:

   ```
   scan> s 843
   ```

5. Repeat step 3–4 until **1–8 candidates** remain. Tips:
   - If candidates stop shrinking with equal values, use `c` (keep changed) /
     `u` (keep unchanged) around a known change.
   - If zero candidates survive, the counter may be `int64`, or the HUD shows a
     derived value. Retry with `--type int64`, and try values 1 higher/lower.
6. Inspect the final candidates:

   ```
   scan> l
   scan> a 0x<one address>
   ```

7. Find a chain for a promising address:

   ```bat
   python tools\hunt_chain.py --addr 0x<address>
   ```

   If it finds nothing, try `--depth 6 --max-off 0x8000`.

8. **Restart validation (mandatory).** Quit to desktop, relaunch the game, load
   in, then run:

   ```bat
   python tools\watch.py
   ```

   Put the chain into `config/offsets.json` first (step 9), then confirm
   `cinders=` matches the HUD on the new session and changes when you collect.
   A chain that fails this test is a heap address, not a stable chain.

9. Write the field into `config/offsets.json` (keep `required_fields` minimal
   for now):

   ```json
   {
     "patch": "S15",
     "module": "Diablo IV.exe",
     "required_fields": ["cinders"],
     "fields": {
       "cinders": {
         "static_off": "0x1234567",
         "offsets": ["0x2E8"],
         "type": "int32",
         "min": 0,
         "max": 1000000
       }
     }
   }
   ```

10. Validate:

    ```bat
    python -m d4bot validate
    ```

    `cinders=812` matching the HUD = Phase 2A complete.

## 4. Phase 2B — HP and resource

Same loop, but values are `float` and usually **not** the displayed percentage:

```bat
python tools\hunt_value.py --type float --value 61.7 --approx 0.5
```

If the HUD shows `61.7 %`, try scanning for `61.7`, `0.617`, `617`. Use the
`c`/`u` filters: HP changes when you take damage (so it is a good candidate to
track). Add to `offsets.json` as `"type": "float"` with `min`/`max` sanity
bounds; add `"hp"` to `required_fields` once it tracks.

## 5. Phase 2C — position + WASD calibration

Position is three consecutive floats that change as you walk. The fastest path
is from the object behind your cinder chain:

1. `python tools\dump.py --addr <player object+0x0> --size 0x400` (module-
   relative; use `--absolute` if you have the raw address) — look for float
   triples near small values.
2. Walk 10 m forward; dump again; the triple that changed by ~10 units in a
   consistent direction is position.
3. Try each plausible triple with:

   ```json
   "position": {"static_off": "...", "offsets": ["..."], "type": "f32x3", "axes": [0, 1]}
   ```

4. `python tools\watch.py --interval 0.2` and walk — `pos=(...)` must track
   movement smoothly and in the right directions.
5. Calibrate the WASD basis:

   ```bat
   python -m d4bot calibrate --live --write
   ```

   It holds each key for ~1.2 s and records the measured direction into
   `config/bot.json`.

If axes are wrong (position jumps on the wrong coordinate), try `"axes": [0, 2]`
or `[1, 2]`.

## 6. Phase 2D — entities (the hard phase)

Goal: a list of nearby monsters with position, HP, team. This is exploration;
work slowly and keep notes.

Suggested attack:

1. Stand where a known number of monsters are nearby (e.g., 5). Scan `int32`
   for `5`; kill one; filter to `4`; repeat. A small int that tracks the count
   of nearby enemies is a strong lead.
2. `hunt_chain --addr` that count; you now have a manager object.
3. Dump around the manager (`tools\dump.py`) and look for arrays of pointers
   (values that look like valid addresses) and for `count` right next to a
   pointer.
4. Guess the entity address and dump it: look for three floats that behave like
   position (change when the monster moves) and a float in `[0, max_hp]` for HP.
5. Fill in `config/offsets.json`:

   ```json
   "entity_manager": {
     "static_off": "0x...", "offsets": ["0x..."],
     "count_off": "0x...", "array_off": "0x...",
     "mode": "pointer_array", "stride": 8, "max_count": 256
   },
   "entity": {
     "pos_off": "0x...", "hp_off": "0x...", "team_off": "0x...", "type_off": "0x..."
   }
   ```

   `mode` can be `"pointer_array"` (array of pointers) or `"inline"` (array of
   structs, `stride` bytes apart).
6. Verify with `watch.py`: `entities=N` should roughly match what is on screen,
   and `nearest=` should drop as you walk toward a monster.

If this stalls for more than a week, cut it: use minimap-based enemy detection
later and keep the memory reader for cinders/position/HP.

## 7. Phase 3 — configure and dry-run the bot

`config/bot.json`:

- `keys`: set your real bindings (verify potion/mount/interact in-game).
- `combat.skills`: your skills with `range`/`cooldown`; **v1 assumes
  self-centred/AoE skills**, aimed skills need Phase 3.5 mouse work.
- `route`: waypoints recorded with `watch.py` (`x`,`y` from `pos=`), e.g.
  `[{"x": 123.0, "y": -45.0, "label": "north-loop"}]`.
- `chest_spots`: candidate Mystery Chest coordinates in the zone you farm.
- thresholds: `retreat_hp`, `chest_cost` (75), rad. `retreat_hp` is measured
  against the **highest HP seen this session**, so it works whether the game
  stores HP as a fraction (1.0) or an absolute pool (e.g. 5312.0).

Dry run (no input sent — verify the decisions in the log):

```bat
python -m d4bot run
```

Live run (F12 panic key ready, game focused):

```bat
python -m d4bot run --live
```

## 8. Phase 4 — live tuning checklist

- [ ] walks the route without wedging on terrain (tune waypoints / radii)
- [ ] fights only when enemies are within `engage_radius`
- [ ] retreats at `retreat_hp` and returns at `resume_hp`
- [ ] stops cleanly on F12 and on death (hp <= 0)
- [ ] opens a Mystery Chest when cinders >= cost (check the interact key)
- [ ] one full loop: fill cinders → 2 chests → no ban, no death
- [ ] telemetry CSV in `logs/` reviewed

## 9. Per-patch routine (Phase 5)

1. Patch lands → `python -m d4bot validate` (expect failures; that is normal).
2. Re-run the hunt for the broken fields only (usually 1–2 fields).
3. Update `config/offsets.json`, restart-test, validate.
4. `python tools\watch.py` sanity pass, then dry run, then live.
Target: 30 min – 2 h per patch.

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `probe` says BLOCKED | anti-cheat denied read handle. Stop; do not bypass. |
| scanner finds 0 | wrong type (try int64), wrong assumed value, or HUD value is derived — try ±1 and related variants. |
| too many candidates after several filters | unrelated copies (UI caches). Keep filtering with `c`/`u` around real changes; also try alignment 8 for int64. |
| chain finder finds nothing | static root may live outside the main module, or field offset > max_off. Try `--depth 6 --max-off 0x8000`; otherwise the value may be in a struct owned by another module (unsupported). |
| `validate` fails after restart | heap-stable chain, not a real chain. Re-hunt; prefer chains with fewer hops. |
| `watch.py` shows plausible but wrong values | wrong chain (silent garbage). Check min/max bounds; verify by changing the value in-game. |
| bot walks wrong direction | run `calibrate --live --write`; check `movement.axes`. |
| bot never attacks | `entity_manager` missing/broken → combat has no targets. Fix Phase 2D. |
| chest never opens | interact keybind or radius; some chests may need a click (Phase 4). |
| reader watchdog stops | stale offsets after a patch — re-anchor (§9). |

## 11. Session report template (paste this back for help)

```
Phase: 2A
Build: <game version / date>, WT3/4
probe: PASS pid=... module base=0x...
cinders: 812 -> 843 -> 901 (HUD)
candidates left: 2
chain: static_off=0x... offsets=[0x...,0x...]
chain finder: found <n>, depth <d>
restart test: PASS/FAIL
watch output: cinders=... hp=... pos=(...)
notes: <anything odd>
```

## 12. Continuing with any assistant

Paste: "Read README/BUILD_BOOK/OFFSETS-HUNTING, run the test suite, then help me
at Phase X. Ask me for observations one step at a time; never invent offsets."

The golden rule: **only the game can tell you the offsets — no assistant can
guess them.** Expect to iterate.
