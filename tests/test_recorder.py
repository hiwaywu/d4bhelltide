"""Recorder logic tests: waypoints, chests, undo, save/merge round-trip."""
import json
import os
import unittest
from pathlib import Path

from d4bot.config import load_bot
from d4bot.recorder import Recorder, RecorderError

TMP = Path(__file__).resolve().parents[1] / ".tmp"


def workdir(name: str) -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    path = TMP / f"{name}-{os.getpid()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class RecorderTests(unittest.TestCase):
    def test_add_waypoint_rounds_and_labels(self):
        rec = Recorder(axes=(0, 1))
        wp = rec.add_waypoint((12.3456, -7.891, 3.0))
        self.assertEqual(wp["label"], "wp-1")
        self.assertEqual(wp["x"], 12.35)
        self.assertEqual(wp["y"], -7.89)
        self.assertEqual(wp["kind"], "walk")

    def test_custom_axes(self):
        rec = Recorder(axes=(0, 2))
        wp = rec.add_waypoint((1.0, 99.0, 2.0))
        self.assertEqual((wp["x"], wp["y"]), (1.0, 2.0))

    def test_axis_out_of_range(self):
        rec = Recorder(axes=(0, 2))
        with self.assertRaises(RecorderError):
            rec.add_waypoint((1.0, 2.0))

    def test_no_position(self):
        with self.assertRaises(RecorderError):
            Recorder().add_waypoint(None)

    def test_undo_order_is_lifo(self):
        rec = Recorder()
        rec.add_waypoint((0.0, 0.0))   # wp-1
        rec.add_chest((5.0, 5.0))      # chest-1
        rec.add_waypoint((9.0, 9.0))   # wp-2 (last in)
        self.assertIn("waypoint", rec.undo().lower())  # wp-2 goes first
        self.assertIn("chest", rec.undo().lower())
        self.assertIn("waypoint", rec.undo().lower())  # wp-1
        with self.assertRaises(RecorderError):
            rec.undo()

    def test_mount_waypoint_kind(self):
        rec = Recorder()
        wp = rec.add_waypoint((1.0, 2.0), kind="mount")
        self.assertEqual(wp["kind"], "mount")

    def test_save_merges_existing_config(self):
        d = workdir("recorder")
        bot_path = d / "bot.json"
        bot_path.write_text(
            json.dumps({"thresholds": {"retreat_hp": 0.5}, "panic_vk": 123}),
            encoding="utf-8",
        )
        rec = Recorder()
        rec.add_waypoint((1.0, 2.0))
        rec.add_chest((3.0, 4.0))
        rec.save(bot_path)

        doc = json.loads(bot_path.read_text(encoding="utf-8"))
        self.assertEqual(doc["thresholds"]["retreat_hp"], 0.5, "existing keys preserved")
        self.assertEqual(len(doc["route"]), 1)
        self.assertEqual(len(doc["chest_spots"]), 1)

        cfg = load_bot(bot_path)
        self.assertEqual(cfg["route"][0]["x"], 1.0)
        self.assertEqual(cfg["chest_spots"][0]["y"], 4.0)

    def test_save_creates_file(self):
        d = workdir("recorder-new")
        path = d / "bot.json"
        Recorder().save(path)
        self.assertTrue(path.exists())
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["route"], [])


if __name__ == "__main__":
    unittest.main()
