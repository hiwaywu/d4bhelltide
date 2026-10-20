"""Safety gate behavior: panic key, foreground requirement, forced key release."""
import unittest
from unittest import mock

from d4bot.config import vk_for
from d4bot.win.input import Input, InputBlocked, Safety


class SafetyTests(unittest.TestCase):
    def test_panic_blocks_input(self):
        with mock.patch("d4bot.win.input._get_async_key_state", return_value=0x8000):
            safety = Safety(panic_vk=0x7B, require_foreground=False, dry_run=True)
            inp = Input(safety, dry_run=True)
            with self.assertRaises(InputBlocked):
                inp.key_down(vk_for("W"))
            self.assertEqual(safety.stop_reason, "panic key held")

    def test_forced_release_works_after_panic(self):
        with mock.patch("d4bot.win.input._get_async_key_state", return_value=0x8000):
            safety = Safety(panic_vk=0x7B, require_foreground=False, dry_run=True)
            inp = Input(safety, dry_run=True)
            inp._held.add(vk_for("W"))
            inp.key_up(vk_for("W"))  # must not raise
            self.assertNotIn(vk_for("W"), inp._held)

    def test_foreground_gate_blocks_when_not_focused(self):
        with mock.patch("d4bot.win.input._get_async_key_state", return_value=0), mock.patch(
            "d4bot.win.memory.foreground_pid", return_value=1234
        ):
            safety = Safety(panic_vk=0x7B, require_foreground=True, target_pid=999, dry_run=True)
            with self.assertRaises(InputBlocked):
                safety.ensure()

    def test_foreground_gate_allows_focused_game(self):
        with mock.patch("d4bot.win.input._get_async_key_state", return_value=0), mock.patch(
            "d4bot.win.memory.foreground_pid", return_value=999
        ):
            safety = Safety(panic_vk=0x7B, require_foreground=True, target_pid=999, dry_run=True)
            safety.ensure()  # no raise

    def test_pid_zero_disables_foreground_gate(self):
        with mock.patch("d4bot.win.input._get_async_key_state", return_value=0), mock.patch(
            "d4bot.win.memory.foreground_pid", return_value=1
        ):
            safety = Safety(panic_vk=0x7B, require_foreground=True, target_pid=0, dry_run=True)
            safety.ensure()

    def test_stop_is_sticky(self):
        safety = Safety(panic_vk=0x7B, require_foreground=False, dry_run=True)
        safety.stop("test")
        with self.assertRaises(InputBlocked):
            safety.ensure()


if __name__ == "__main__":
    unittest.main()
