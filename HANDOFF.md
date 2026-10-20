# HANDOFF — carrying this project to another machine / chat

The chat history does not travel, but everything needed does. This file is the
compressed state of the build session. Read it, then `BUILD_BOOK.md`.

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
