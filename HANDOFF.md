# HANDOFF — carrying this project to another machine / chat

The chat history does not travel, but everything needed does. This file is the
compressed state of the build session. Read it, then `BUILD_BOOK.md`.

---

## FOR THE ASSISTANT — if the user says "read the README and HANDOFF and tell me exactly what I need to do right now"

Do this, in order, before answering:

1. Confirm the working directory contains `d4bot\` and `tools\` (if not, ask
   where the project was extracted).
2. Check Python is 64-bit and dependencies exist:
   `.\.venv\Scripts\python.exe --version` (fall back to `python --version`),
   and if `.venv` is missing, create it and run `pip install -r requirements.txt`.
3. Run the test suite: `python -m unittest discover -s tests -t . -v`
   Expect `OK` (70 tests). If it fails, fix that **first** and say so.
4. Run `python tools\doctor.py`.
5. Check whether Diablo IV is running (`Get-Process "*Diablo*"`).

Then reply with **at most 5 numbered commands** for the very next action —
not a summary of the whole project, not options. The expected answer when the
game is running and tests pass is:

1. Launch Diablo IV and log in (if not already).
2. `python tools\probe_attach.py`
3. Paste its output here.

If Diablo IV is not installed or not running, say that first and give the one
command that checks it. Never invent offsets; never suggest bypassing
anti-cheat; if the probe reports `BLOCKED`, stop and explain the fallback.

---

## Where the project stands

- Code is **complete and tested** for everything that does not need the game:
  read-only memory layer, value scanner, pointer-chain finder, reader with
  sanity guards, entity decoding, bot loop (nav/combat/chests/retreat/panic/
  focus-loss pause), tools, and docs. `python -m unittest discover -s tests -t . -v`
  → **70 tests, OK** (verified against a synthetic process; no game needed).
- **No real game offsets exist yet.** `config/offsets.json` has empty `fields`.
  That is expected: offsets are properties of the installed game build and can
  only be discovered with Diablo IV running.

## At the D4 PC — exact sequence

```powershell
# get the project (ZIP from GitHub, or:)
git clone https://github.com/hiwaywu/d4bhelltide.git
cd d4bhelltide

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v   # expect OK (70)
.\.venv\Scripts\python.exe tools\doctor.py                          # game may say skip

# with Diablo IV running and logged in:
.\.venv\Scripts\python.exe tools\probe_attach.py
```

PASS  -> continue with BUILD_BOOK.md, Phase 2A (cinder hunt).
NO GAME -> the game isn't running / exe name differs.
BLOCKED -> the anti-cheat refused read access; per project rules we stop the
memory path there (no bypass), and switch to the vision approach instead.

## Starting a new chat with any assistant

Paste this (adjust the phase):

> I'm continuing the `d4bhelltide` project in this folder. Read `README.md`,
> `BUILD_BOOK.md` and `OFFSETS-HUNTING.md` first. Run the unit tests
> (`python -m unittest discover -s tests -t . -v`) and `python tools\doctor.py`.
> Then help me with **Phase 0 / Phase 2A**: run `tools\probe_attach.py` with
> Diablo IV open, and walk me through the cinder value hunt one step at a time,
> asking me for in-game observations. Never invent offsets — only accept values
> validated by scanning and a game restart.

If the assistant cannot run files, just follow `BUILD_BOOK.md` manually and
paste command output into any chat (phone is fine) for interpretation.

## No game at that machine? Two options

1. Move the project to the D4 PC (USB/cloud) and run there.
2. Keep this machine running and reach it remotely (RDP / Tailscale / Chrome
   Remote Desktop) to continue the *same* chat session.

## Cautions

- This repo is private; never commit tokens or credentials.
- Do not run "free D4 bot" downloads from the internet — malware vector.
- Automation violates Blizzard's ToS; the risk is the user's.
