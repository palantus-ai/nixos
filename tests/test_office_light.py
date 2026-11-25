import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).parents[1] / "hosts/nixos/desktop/office-light.py"
SPEC = importlib.util.spec_from_file_location("office_light", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
OFFICE_LIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OFFICE_LIGHT)


class ScreenLightStateTests(unittest.TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.runtime.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.runtime.cleanup)

    def test_screen_off_remembers_on_light_and_screen_on_restores_it(self):
        with patch.object(OFFICE_LIGHT, "request", side_effect=[{"state": "on"}, None, {"state": "off"}, None]) as request:
            OFFICE_LIGHT.screen_off("http://ha", "token")
            state_file = pathlib.Path(self.runtime.name) / "office-light-screen.json"
            self.assertTrue(state_file.exists())
            OFFICE_LIGHT.screen_on("http://ha", "token")

        self.assertFalse(state_file.exists())
        self.assertEqual(request.call_args_list[1].args[2], "/api/services/light/turn_off")
        self.assertEqual(request.call_args_list[3].args[2], "/api/services/light/turn_on")
        payload = request.call_args_list[3].args[3]
        self.assertIn(payload["brightness_pct"], (40, 75))

    def test_screen_off_preserves_a_light_that_was_already_off(self):
        with patch.object(OFFICE_LIGHT, "request", return_value={"state": "off"}) as request:
            OFFICE_LIGHT.screen_off("http://ha", "token")
            OFFICE_LIGHT.screen_on("http://ha", "token")

        self.assertEqual(request.call_count, 1)
        self.assertFalse((pathlib.Path(self.runtime.name) / "office-light-screen.json").exists())

    def test_screen_on_without_managed_off_does_not_change_light(self):
        with patch.object(OFFICE_LIGHT, "request") as request:
            OFFICE_LIGHT.screen_on("http://ha", "token")
        request.assert_not_called()

    def test_repeated_screen_off_does_not_replace_restore_state(self):
        with patch.object(OFFICE_LIGHT, "request", side_effect=[{"state": "on"}, None, {"state": "off"}]) as request:
            OFFICE_LIGHT.screen_off("http://ha", "token")
            OFFICE_LIGHT.screen_off("http://ha", "token")
        self.assertEqual(request.call_count, 2)

    def test_failed_turn_off_removes_restore_marker(self):
        with patch.object(OFFICE_LIGHT, "request", side_effect=[{"state": "on"}, OSError("HA down")]):
            with self.assertRaises(OSError):
                OFFICE_LIGHT.screen_off("http://ha", "token")
        self.assertFalse((pathlib.Path(self.runtime.name) / "office-light-screen.json").exists())


if __name__ == "__main__":
    unittest.main()
