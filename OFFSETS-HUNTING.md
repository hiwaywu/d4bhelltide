# OFFSETS HUNTING — reference and runbook

Everything here is read-only observation. If a step requires writing game
memory, it is out of scope — the bot never writes, and neither should you.

---

## 1. The data model in one paragraph

A game value (e.g. cinders) lives at some address in the game's address space.
That address changes every launch, but it is always reachable by a *chain*:
a stable pointer inside the game's main module (which relocates with ASLR but
whose internal offsets stay fixed for a given build) leads to an object; the
object has fields at fixed byte offsets; one of those fields is the value — or
another pointer, and so on.

A chain in this project:

```
base + static_off  --deref-->  p0
p0 + offsets[0]    --deref-->  p1
p1 + offsets[1]    --deref-->  p2
...
pN + offsets[-1]              = address of the value
```

Equivalently, in `config/offsets.json`:

```json
"cinders": {"static_off": "0x2A3B4C0", "offsets": ["0x48", "0x2E8"], "type": "int32"}
```

```python
p = read_u64(module_base + 0x2A3B4C0)   # static pointer
p = read_u64(p + 0x48)                  # hop 1
value = read_i32(p + 0x2E8)             # final field
```

`hunt_chain.py` emits exactly this format (deepest hop first). `offsets` may be
a single element — the common "static → object → field" case.

**Validation:** a chain is only real if it survives (a) a game restart, and
(b) a value check against the HUD. `validate`/`watch` enforce (b); you enforce (a).

---

## 2. Value hunting procedure (generic)

```bat
python tools\hunt_value.py --type int32 --value <current HUD value>
```

Loop: change the thing in game → `s <new value>` → repeat. Commands:

| cmd | meaning |
|---|---|
| `s <v>` | filter candidates to those equal to `<v>` |
| `c` | keep candidates whose bytes changed since last scan |
| `u` | keep candidates whose bytes did not change |
| `l` | list (up to 200) |
| `a <addr>` | qword annotation + hexdump around an address |
| `q` | quit |

Value-type guidance:

| HUD shows | Try |
|---|---|
| integer (cinders, gold, materials) | `int32` first, then `int64` |
| percentage (HP 61.7 %) | `float` with `--approx 0.5`, trying 61.7 / 0.617 / 617 |
| a number that drifts smoothly | `float` with tolerance; `double` as fallback |

Common traps:

- **Derived displays.** Some HUD numbers are computed (e.g. HP as a ratio),
  and the raw value may be an absolute HP or a fraction. Try related magnitudes.
- **Copies.** UI caches and tooltips hold duplicates; they usually change *with*
  the value. Prefer candidates whose bytes stop changing when you stop playing.
- **Shared ranges.** Ammo-like counters (potions, elixirs) look identical; the
  `c`/`u` filter around a specific change separates them.

---

## 3. Chain hunting procedure

```bat
python tools\hunt_chain.py --addr 0x<absolute field address>
```

Options: `--depth` (default 4), `--max-off` (default 0x2000), `--max-chains`.

How it works: for a field address `A`, it finds every qword `V` with
`0 <= A - V <= max_off` (V is the enclosing object, `A - V` the field offset);
if the qword holding `V` is inside the main module image, that is a static root.
Otherwise it grows a level: find qwords pointing at the current location, etc.

Interpretation:

- **Depth 1** = static globals hold a direct pointer to the object; most stable.
- **Depth 2–3** = typical (static singleton → manager → array entry → struct).
- **Depth 4+** = fragile; re-hunt after patches.
- **`NOTE: static base != module base`** → the root lives in another image
  (DLL). Supported by the finder only when you pass explicit static ranges;
  the CLI uses the main module. Prefer chains rooted in the main module.

---

## 4. Per-value playbooks

### 4.1 Cinders (int32)

1. Helltide active, note counter `812`.
2. Scan, collect a few demons, filter to `843`, then `901`.
3. 1–8 candidates → `hunt_chain` → restart test → write into
   `fields.cinders`, `required_fields: ["cinders"]`.
4. `python -m d4bot validate` must print the live number.

Cross-check: opening a Tortured Gift removes exactly its cost (often 75).

### 4.2 HP / resource (float)

- Scan the displayed number with tolerance; verify by taking damage.
- Sanity bounds matter: `"min": 0, "max": 1000000` catches garbage after patches.
- If multiple float candidates survive, hit `c`/`u`: HP changes on damage,
  resource on cast, and both should stop changing when you stand still out of combat.

### 4.3 Position (f32x3)

Best approach: reuse the object from the cinder chain.

1. Dump around the object base (`tools\dump.py --addr ...`) and look for float
   triples with world-like magnitudes.
2. Walk ~10 m in one direction; dump again; a triple that changed coherently is
   position. Verify magnitude: units ≈ metres per second × seconds.
3. Add as `"type": "f32x3"`, `"axes": [0,1]` (or `[0,2]` / `[1,2]` if the layout
   differs), then `watch.py` while walking (smooth tracking, correct directions).
4. `python -m d4bot calibrate --live --write` records the WASD→world basis into
   `config/bot.json`. Calibration matters: route following assumes it.

### 4.4 Entities (the hard one)

Goal config:

```json
"entity_manager": {
  "static_off": "0x...", "offsets": ["0x..."],
  "count_off": "0x...", "array_off": "0x...",
  "mode": "pointer_array", "stride": 8, "max_count": 256
},
"entity": {"pos_off": "0x...", "hp_off": "0x...", "team_off": "0x...", "type_off": "0x..."}
```

Working method:

1. **Find the count.** Stand amid a known number of monsters; scan int32 for it;
   kill one; filter to `n-1`. A small int tracking nearby enemy count is the
   manager's count field. Mob wandering makes this fiddly — use dense camps and
   short loops.
2. **Chain the count** (manager object) with `hunt_chain`.
3. **Find the array.** Dump around the manager: look for a qword that is a valid
   address, plus a small int nearby. Read that address: an array of qwords that
   each point to plausible objects (or a packed struct array — then use
   `"mode": "inline"` with the right `stride`).
4. **Decode one entity.** Dump an entity; find three floats that change when it
   moves (position) and a float in `[0, max_hp]`. Team is a small int (player vs
   monster); type is another small int/enum.
5. Verify with `watch.py`: `entities=` count ≈ on-screen count, `nearest=`
   decreases as you approach.

`max_count` guards runaway reads; start at 256.

---

## 5. Restart validation (mandatory)

1. Note HUD cinders, e.g. `812`.
2. Quit to desktop; relaunch; load in.
3. `python tools\watch.py` → `cinders=812`.
4. Change the value (kill something) → watch updates.

Only then is the chain trusted. Chains that pass `validate` but fail restart are
heap addresses that happened to resolve once — do not ship them.

## 6. Patch recovery

After a patch, expect `validate` to fail. Triage:

1. Which fields fail? Usually 1–2 (module base shifts, struct layout survives).
2. Re-hunt only those fields (repeat §4 for each).
3. If *everything* fails, the module base moved or the game recompiled heavily —
   re-hunt all fields; budget 1–2 evenings.
4. Save the previous `offsets.json` (rename to `config/offsets.<patch>.json`) so
   you can roll back and compare.

## 7. Pitfalls checklist

- [ ] 64-bit Python (`struct.calcsize('P') == 8`)
- [ ] Game and scanner running at the same privilege level
- [ ] HUD value actually equals memory value (derived displays exist)
- [ ] Alignment: int32 aligned 4, int64 aligned 8 (use `--align 8` for 64-bit)
- [ ] Restart test performed, not skipped
- [ ] Sanity `min`/`max` set on every field (catches post-patch garbage)
- [ ] One field at a time; keep notes/session template
