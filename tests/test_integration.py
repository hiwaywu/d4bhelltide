"""End-to-end integration tests: CLI -> foreign process -> reader, and the bot loop."""
import contextlib
import io
import json
import os
import unittest
from pathlib import Path

from d4bot import cli
from d4bot.bot.loop import BotLoop
from d4bot.config import DEFAULT_BOT, deep_merge
from d4bot.reader import Snapshot
from d4bot.win.memory import Process

from tests.fake_target import FakeTarget

TMP = Path(__file__).resolve().parents[1] / ".tmp"


def fresh_dir(name: str) -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    path = TMP / f"{name}-{os.getpid()}-{id(name) & 0xFFFF}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class FakeReader:
    """Returns snapshots in sequence, repeating the last one."""

    def __init__(self, snaps):
        self.snaps = snaps
        self.i = 0

    def poll(self):
        snap = self.snaps[min(self.i, len(self.snaps) - 1)]
        self.i += 1
        return snap


class CliValidateIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = FakeTarget()

    @classmethod
    def tearDownClass(cls):
        cls.target.close()

    def _offsets_doc(self, root: int, module_base: int) -> dict:
        return {
            "patch": "synthetic",
            "module": "",
            "required_fields": ["cinders"],
            "fields": {
                "cinders": {
                    "static_off": hex(root - module_base),
                    "offsets": ["0x10", "0x8"],
                    "type": "int32",
                    "min": 0,
                    "max": 10**9,
                }
            },
        }

    def test_validate_reads_live_foreign_process(self):
        info = self.target.info
        proc = Process.open(info["pid"])
        try:
            module = proc.main_module()
            doc = self._offsets_doc(info["root"], module.base)
            cfg = fresh_dir("itest-ok") / "offsets.json"
            cfg.write_text(json.dumps(doc), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["validate", "--pid", str(info["pid"]), "--offsets", str(cfg)])
            text = out.getvalue()
            self.assertEqual(code, 0, text)
            self.assertIn("cinders=424242", text)
        finally:
            proc.close()

    def test_validate_rejects_wrong_chain(self):
        info = self.target.info
        proc = Process.open(info["pid"])
        try:
            module = proc.main_module()
            doc = self._offsets_doc(info["root"] + 4, module.base)  # shift -> garbage
            cfg = fresh_dir("itest-bad") / "offsets.json"
            cfg.write_text(json.dumps(doc), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["validate", "--pid", str(info["pid"]), "--offsets", str(cfg)])
            self.assertEqual(code, 1)
            self.assertIn("INVALID", out.getvalue())
        finally:
            proc.close()


class LoopIntegrationTest(unittest.TestCase):
    def _cfg(self, **overrides):
        cfg = deep_merge(DEFAULT_BOT, {"panic_vk": 0x7B, "require_foreground": False})
        cfg = deep_merge(cfg, overrides)
        return cfg

    def test_opens_chest_then_idles(self):
        snaps = [
            Snapshot(t=0.0, cinders=80, hp=100.0, pos=(0.0, 0.0, 0.0)),
            Snapshot(t=0.1, cinders=5, hp=100.0, pos=(0.0, 0.0, 0.0)),
            Snapshot(t=0.2, cinders=5, hp=100.0, pos=(0.0, 0.0, 0.0)),
        ]
        cfg = self._cfg(
            chest_spots=[{"x": 1.0, "y": 0.0, "label": "A"}],
            loop={"tick_s": 0.02, "max_runtime_s": 1.2},
        )
        log_dir = fresh_dir("itest-chest")
        loop = BotLoop(None, None, cfg, live=False, log_dir=log_dir, reader=FakeReader(snaps))
        with contextlib.redirect_stdout(io.StringIO()):
            loop.run()
        csvs = list(log_dir.glob("run-*.csv"))
        self.assertEqual(len(csvs), 1)
        text = csvs[0].read_text(encoding="utf-8")
        self.assertIn("opened A", text)
        self.assertIn("idle", text)

    def test_death_stops_the_loop(self):
        snaps = [Snapshot(t=0.0, cinders=10, hp=0.0, pos=(0.0, 0.0, 0.0))]
        cfg = self._cfg(loop={"tick_s": 0.01, "max_runtime_s": 5.0})
        log_dir = fresh_dir("itest-death")
        loop = BotLoop(None, None, cfg, live=False, log_dir=log_dir, reader=FakeReader(snaps))
        with contextlib.redirect_stdout(io.StringIO()):
            loop.run()
        self.assertIn("death", loop.safety.stop_reason.lower())

    def test_retreat_move_away_from_enemy(self):
        from d4bot.reader import Entity

        enemy = Entity(addr=0x1000, pos=(10.0, 0.0, 0.0), hp=100.0, team=1, dist=10.0)
        snaps = [
            Snapshot(t=0.0, cinders=10, hp=100.0, pos=(0.0, 0.0, 0.0), entities=[enemy]),
            Snapshot(t=0.1, cinders=10, hp=10.0, pos=(0.0, 0.0, 0.0), entities=[enemy]),
        ]
        cfg = self._cfg(loop={"tick_s": 0.01, "max_runtime_s": 0.4})
        log_dir = fresh_dir("itest-retreat")
        loop = BotLoop(None, None, cfg, live=False, log_dir=log_dir, reader=FakeReader(snaps))
        with contextlib.redirect_stdout(io.StringIO()):
            loop.run()
        text = list(log_dir.glob("run-*.csv"))[0].read_text(encoding="utf-8")
        self.assertIn("retreat", text)


if __name__ == "__main__":
    unittest.main()
