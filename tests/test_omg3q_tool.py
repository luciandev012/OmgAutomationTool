import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch


SOURCE = pathlib.Path(__file__).resolve().parents[1] / "omg3q_tool.py"
spec = importlib.util.spec_from_file_location("omg3q_tool", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class ToolTests(unittest.TestCase):
    def test_password_is_sent_on_stdin_not_process_arguments(self):
        calls = []

        def fake_run(adb, *args, **kwargs):
            calls.append((args, kwargs))
            return b""

        with patch.object(tool, "run_adb", fake_run):
            tool.input_text("adb", "127.0.0.1:16384", "p@ss word!'42")
        args, kwargs = calls[0]
        self.assertEqual(args, ("-s", "127.0.0.1:16384", "shell"))
        self.assertNotIn(b"p@ss", " ".join(args).encode())
        self.assertIn(b"input text", kwargs["data"])
        self.assertIn(b"%s", kwargs["data"])

    def test_configuration_never_contains_credentials(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent) as folder:
            path = pathlib.Path(folder) / "settings.json"
            with patch.object(tool, "CONFIG_FILE", path):
                tool.save_config("127.0.0.1:16384", "com.example.game",
                                 [{"action": "username"}, {"action": "password"}])
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(len(data["steps"]), 2)
                self.assertNotIn("username", data)
                self.assertNotIn("password", data)

    def test_connect_parses_device_size(self):
        outputs = [b"connected to 127.0.0.1:16384", b"device\n", b"Physical size: 1920x1080\n"]
        with patch.object(tool, "run_adb", side_effect=outputs):
            self.assertEqual(tool.connect("adb", "127.0.0.1:16384"), (1920, 1080))

    def test_foreground_game_package_is_detected(self):
        focus = b'mCurrentFocus=Window{abc123 u0 com.example.omg3q/com.example.StartActivity}\n'
        with patch.object(tool, "run_adb", return_value=focus):
            self.assertEqual(tool.foreground_package("adb", "127.0.0.1:16384"),
                             "com.example.omg3q")


if __name__ == "__main__":
    unittest.main()
