import importlib.util
import pathlib
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from dungeon_engine import DungeonResult


SOURCE = pathlib.Path(__file__).resolve().parents[1] / "omg3q_tool.py"
spec = importlib.util.spec_from_file_location("omg3q_tool", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class ToolTests(unittest.TestCase):
    def test_gui_builds_excel_scripts_without_old_credentials_widgets(self):
        app=tool.App.__new__(tool.App)
        app.root=Mock();app.providers=[]
        for name in ('provider_name','serial','excel_path','dungeon_limit','status','dungeon_spam','dungeon_spam_limit','advance_scope','advance_mode','advance_target','level_scope','level_mode','level_target','treasure_scope','treasure_mode','treasure_target'):
            setattr(app,name,Mock())
        app.evolution = {kind: {key: Mock() for key in ("scope", "mode", "target", "lv")} for kind in tool.KINDS}
        app._scan_catalog=Mock()
        app.run_excel_script=Mock()
        with ExitStack() as stack:
            stack.enter_context(patch.object(tool,'ScrollableFrame'))
            buttons=stack.enter_context(patch.object(tool.ttk,'Button'))
            for name in ('Frame','Label','Combobox','Entry','LabelFrame','Spinbox','Checkbutton'):
                stack.enter_context(patch.object(tool.ttk,name))
            for name in ('StringVar','Canvas','Listbox'):
                stack.enter_context(patch.object(tool.tk,name))
            app._build()
            scripts=[c.kwargs for c in buttons.call_args_list if c.kwargs.get('text') in {'Script A','Script B','Script C'}]
            self.assertEqual([c['text'] for c in scripts],['Script A','Script B','Script C'])
            for config in scripts:config['command']()
            self.assertEqual([c.args[0] for c in app.run_excel_script.call_args_list],['A','B','C'])
        self.assertFalse(hasattr(app,'account_combo'))

    def test_missing_server_is_started_locally_then_original_command_retried(self):
        missing = Mock(returncode=1, stdout=b'', stderr=b'cannot connect to daemon at tcp:127.0.0.1:5049')
        ready = Mock(returncode=0, stdout=b'', stderr=b'')
        result = Mock(returncode=0, stdout=b'connected', stderr=b'')
        with patch.dict(tool.os.environ, {'OMG_ADB_SERVER_PORT': '5049'}), patch.object(
                tool.subprocess, 'run', side_effect=[missing, missing, ready, result]) as run:
            self.assertEqual(tool.run_adb('adb', 'connect', '127.0.0.1:16384'), b'connected')
        self.assertEqual(run.call_args_list[2].args[0], ['adb', '-L', 'tcp:5049', 'start-server'])
        self.assertEqual(run.call_args_list[0].args[0], run.call_args_list[3].args[0])

    def test_device_error_does_not_restart_shared_server(self):
        offline = Mock(returncode=1, stdout=b'', stderr=b'error: device offline')
        with patch.object(tool.subprocess, 'run', return_value=offline) as run:
            with self.assertRaisesRegex(tool.AdbError, 'device offline'):
                tool.run_adb('adb', '-s', 'emulator-5554', 'get-state')
        self.assertEqual(run.call_count, 1)

    def test_server_started_by_other_worker_is_reused(self):
        missing = Mock(returncode=1, stdout=b'', stderr=b'cannot connect to daemon at tcp:127.0.0.1:5037')
        ready = Mock(returncode=0, stdout=b'ok', stderr=b'')
        with patch.object(tool.subprocess, 'run', side_effect=[missing, ready, ready]) as run:
            self.assertEqual(tool.run_adb('adb', 'devices'), b'ok')
        self.assertFalse(any('-L' in c.args[0] for c in run.call_args_list))

    def test_server_start_failure_is_reported(self):
        missing = Mock(returncode=1, stdout=b'', stderr=b'cannot connect to daemon at tcp:127.0.0.1:5037')
        failed = Mock(returncode=1, stdout=b'', stderr=b'permission denied')
        with patch.object(tool.subprocess, 'run', side_effect=[missing, missing, failed]):
            with self.assertRaisesRegex(tool.AdbError, 'permission denied'):
                tool.run_adb('adb', 'devices')

    def test_open_instances_opens_selected_provider_dialog_without_launching(self):
        app = tool.App.__new__(tool.App)
        app.busy = False
        app.instance_dialog = None
        app.provider_combo = Mock()
        app.provider_name = Mock()
        app.provider_name.get.return_value = "LDPlayer"
        provider = Mock(label="LDPlayer")
        app.providers = [provider]
        with patch.object(tool, "InstanceDialog") as dialog:
            app.open_instances()
            dialog.assert_called_once_with(app, provider)
            provider.launch.assert_not_called()

    def test_instance_controls_can_open_while_a_device_task_is_active(self):
        app = tool.App.__new__(tool.App)
        app.busy = True
        app.instance_dialog = None
        app.provider_name = Mock()
        app.provider_name.get.return_value = "MuMu"
        provider = Mock(label="MuMu")
        app.providers = [provider]
        app.provider_combo = Mock()
        with patch.object(tool, "InstanceDialog") as dialog:
            app.open_instances()
            dialog.assert_called_once_with(app, provider)

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
        app.sessions = tool.SessionRegistry()
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
