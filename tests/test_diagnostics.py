"""Diagnostics tests: environment and config checks."""
import json
import os
import unittest
from pathlib import Path

from d4bot.diagnostics import (
    config_checks,
    environment_checks,
    game_check,
    run_all,
    worst_status,
)

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".tmp"


def workdir(name: str) -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    path = TMP / f"{name}-{os.getpid()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class DiagnosticsTests(unittest.TestCase):
    def test_environment_checks_are_ok_on_this_host(self):
        checks = environment_checks()
        names = {c.name: c for c in checks}
        self.assertEqual(names["python-bitness"].status, "ok", names["python-bitness"].detail)
        self.assertEqual(names["numpy"].status, "ok", names["numpy"].detail)

    def test_repo_configs_parse(self):
        checks = config_checks(ROOT / "config/offsets.json", ROOT / "config/bot.json")
        statuses = {c.name: c.status for c in checks}
        self.assertIn(statuses["offsets"], ("ok", "warn"))
        self.assertEqual(statuses["bot-config"], "ok")

    def test_missing_configs_fail(self):
        checks = config_checks("does/not/exist.json", "does/not/exist-bot.json")
        statuses = {c.name: c.status for c in checks}
        self.assertEqual(statuses["offsets"], "fail")
        self.assertEqual(statuses["bot-config"], "fail")

    def test_bad_offsets_json_fails(self):
        d = workdir("diag-bad")
        path = d / "offsets.json"
        path.write_text("{not json", encoding="utf-8")
        checks = config_checks(path, ROOT / "config/bot.json")
        self.assertEqual({c.name: c.status for c in checks}["offsets"], "fail")

    def test_bad_bot_json_fails(self):
        d = workdir("diag-bad-bot")
        path = d / "bot.json"
        path.write_text("[1,2,3]", encoding="utf-8")
        checks = config_checks(ROOT / "config/offsets.json", path)
        self.assertEqual({c.name: c.status for c in checks}["bot-config"], "fail")

    def test_required_field_missing_fails(self):
        d = workdir("diag-missing-field")
        offsets = d / "offsets.json"
        offsets.write_text(
            json.dumps(
                {
                    "fields": {"cinders": {"static_off": "0x1", "offsets": ["0x0"], "type": "int32"}},
                    "required_fields": ["hp"],
                }
            ),
            encoding="utf-8",
        )
        checks = config_checks(offsets, ROOT / "config/bot.json")
        self.assertEqual({c.name: c.status for c in checks}["offsets"], "fail")

    def test_game_check_returns_skip_or_ok(self):
        checks = game_check()
        self.assertEqual(len(checks), 1)
        self.assertIn(checks[0].status, ("ok", "skip", "warn"))

    def test_worst_status(self):
        checks = config_checks(ROOT / "config/offsets.json", ROOT / "config/bot.json")
        self.assertIn(worst_status(checks), ("ok", "warn"))


if __name__ == "__main__":
    unittest.main()
