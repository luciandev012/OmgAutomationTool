import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from dungeon_engine import DungeonResult


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

    def dungeon_app(self, spam=True, spam_limit="100"):
        app = Mock(spec=tool.App)
        app.busy = False
        for name, value in (("dungeon_limit", "0"), ("dungeon_spam", spam),
                            ("dungeon_spam_limit", spam_limit),
                            ("serial", "127.0.0.1:16384"), ("package", "com.gs2.omg")):
            variable = Mock()
            variable.get.return_value = value
            setattr(app, name, variable)
        app.adb = "adb"
        app.stop_event, app.events, app.status, app.root = Mock(), Mock(), Mock(), Mock()
        return app

    def test_dungeon_gui_passes_spam_budget_to_worker(self):
        app = self.dungeon_app(spam_limit="23")
        with patch.object(tool, "DungeonDetector"), patch.object(tool, "connect"), \
                patch.object(tool, "foreground_package", return_value="com.gs2.omg"), \
                patch.object(tool, "AdbDevice"), patch.object(tool, "DungeonEngine") as engine:
            tool.App.run_dungeon(app)
            work = app._worker.call_args.args[0]
            work()
        engine.return_value.run.assert_called_once_with(max_wins=0, spam=True, spam_limit=23)

    def test_invalid_spam_budget_does_not_start_worker(self):
        for value in ("0", "-1", "", "one", "1.5"):
            app = self.dungeon_app(spam_limit=value)
            with patch.object(tool, "DungeonDetector"), patch.object(tool.messagebox, "showinfo") as notice:
                tool.App.run_dungeon(app)
            app._worker.assert_not_called()
            notice.assert_called_once()

    def test_disabled_spam_ignores_an_unused_invalid_budget(self):
        app = self.dungeon_app(spam=False, spam_limit="invalid")
        with patch.object(tool, "DungeonDetector"), patch.object(tool, "connect"), \
                patch.object(tool, "foreground_package", return_value="com.gs2.omg"), \
                patch.object(tool, "AdbDevice"), patch.object(tool, "DungeonEngine") as engine:
            tool.App.run_dungeon(app)
            app._worker.call_args.args[0]()
        engine.return_value.run.assert_called_once_with(max_wins=0, spam=False, spam_limit=100)

    def test_spam_exhaustion_notifies_and_only_restarts_after_yes(self):
        for answer in (False, True):
            app = self.dungeon_app()
            result = DungeonResult("spam_limit", "Đã hết 100 lần spam.", retries=100, stage_retries=100)
            with patch.object(tool.messagebox, "askyesno", return_value=answer) as question:
                tool.App._dungeon_complete(app, result)
            question.assert_called_once()
            app.run_dungeon.assert_not_called()
            self.assertEqual(app.last_dungeon_result, result)
            if answer:
                app.root.after_idle.assert_called_once_with(app.run_dungeon)
            else:
                app.root.after_idle.assert_not_called()

    def test_normal_defeat_does_not_offer_a_spam_turn(self):
        app = self.dungeon_app(spam=False)
        with patch.object(tool.messagebox, "askyesno") as question:
            tool.App._dungeon_complete(app, DungeonResult("defeat", "Đã thua."))
        question.assert_not_called()
        app.root.after_idle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
