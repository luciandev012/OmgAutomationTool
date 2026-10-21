import queue
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from emulator_instances import Emulator, Instance, LaunchCancelled
from instance_dialog import InstanceDialog
from task_sessions import SessionRegistry, active_session, guard_command


class Var:
    def __init__(self, value=False): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


def dialog_fixture():
    dialog = InstanceDialog.__new__(InstanceDialog)
    dialog.provider = Emulator('mumu', Path('manager.exe'), Path('adb.exe'))
    dialog.instances = [Instance('1','A'), Instance('2','B')]
    dialog.checks = [Var(), Var()]
    dialog.scanning = False
    dialog.app = Mock()
    dialog.app.sessions = SessionRegistry()
    dialog.app.events = queue.Queue()
    dialog.app.package.get.return_value = 'com.gs2.omg'
    dialog.selection_count = Mock()
    dialog.message = Mock()
    dialog.start, dialog.pause, dialog.resume, dialog.stop = (Mock() for _ in range(4))
    return dialog


class SessionTests(unittest.TestCase):
    def test_launches_two_selected_instances_concurrently_and_clears_checks(self):
        dialog = dialog_fixture()
        dialog.set_checks(True)
        entered = [threading.Event(), threading.Event()]
        release = threading.Event()
        exited = [threading.Event(), threading.Event()]
        def fake_open(provider, instance, *args, **kwargs):
            n = int(instance.index)-1
            entered[n].set()
            try:
                if not release.wait(3): raise RuntimeError('test timed out')
                serial = f'127.0.0.1:{16000+n}'
                kwargs['on_device']('adb.exe', serial)
                return 'adb.exe', serial
            finally:
                exited[n].set()
        with patch('instance_dialog.open_instance', side_effect=fake_open):
            try:
                dialog.run()
                self.assertFalse(any(v.get() for v in dialog.checks))
                self.assertTrue(entered[0].wait(1), 'A did not start')
                self.assertTrue(entered[1].wait(1), 'B waited for A to finish')
                self.assertFalse(exited[0].is_set())
                self.assertFalse(exited[1].is_set())
            finally:
                release.set()
                for event in exited: event.wait(2)

    def test_pause_resume_stop_each_clear_selection_and_only_affect_a(self):
        dialog = dialog_fixture()
        a = dialog.app.sessions.instance(dialog.provider, dialog.instances[0])
        b = dialog.app.sessions.instance(dialog.provider, dialog.instances[1])
        # Opening the game has finished; controls must remain usable.
        a.finish('Đã mở OMG 3Q'); b.finish('Đã mở OMG 3Q')
        dialog.checks[0].set(True)
        dialog.control_selected('pause')
        self.assertTrue(a.control.paused.is_set())
        self.assertFalse(b.control.paused.is_set())
        self.assertFalse(any(v.get() for v in dialog.checks))
        dialog.checks[0].set(True)
        dialog.control_selected('resume')
        self.assertFalse(a.control.paused.is_set())
        self.assertFalse(any(v.get() for v in dialog.checks))
        dialog.checks[0].set(True)
        dialog.control_selected('stop')
        self.assertTrue(a.control.cancelled.is_set())
        self.assertFalse(b.control.cancelled.is_set())
        self.assertFalse(any(v.get() for v in dialog.checks))

    def test_checkbox_reset_does_not_cancel_submitted_work(self):
        dialog = dialog_fixture()
        dialog.set_checks(True)
        selected = dialog.take_selection()
        self.assertEqual([i.name for i in selected], ['A','B'])
        self.assertFalse(any(v.get() for v in dialog.checks))
        for instance in selected:
            self.assertFalse(dialog.app.sessions.instance(dialog.provider, instance).control.cancelled.is_set())

    def test_pause_blocks_a_adb_commands_while_b_can_continue(self):
        registry = SessionRegistry()
        a, b = registry.device('adb','A'), registry.device('adb','B')
        a.control.paused.set()
        started, blocked_done = threading.Event(), threading.Event()
        cancelled = []
        def run_a():
            with active_session(a):
                started.set()
                try:
                    guard_command('adb', ('-s','A','shell','input','tap','1','2'))
                except LaunchCancelled:
                    cancelled.append(True)
                finally:
                    blocked_done.set()
        thread = threading.Thread(target=run_a)
        thread.start()
        try:
            self.assertTrue(started.wait(1))
            with active_session(b):
                guard_command('adb', ('-s','B','shell','input','tap','1','2'))
            self.assertFalse(blocked_done.wait(.05))
            a.control.cancelled.set()
            self.assertTrue(blocked_done.wait(1))
            self.assertEqual(cancelled, [True])
            with active_session(b):
                guard_command('adb', ('-s','B','shell','input','tap','3','4'))
        finally:
            a.control.cancelled.set()
            thread.join(2)

    def test_resume_unblocks_only_selected_device(self):
        registry = SessionRegistry()
        a, b = registry.device('adb','A'), registry.device('adb','B')
        for session in (a,b): session.control.paused.set()
        passed = threading.Event()
        def work():
            with active_session(a):
                guard_command('adb', ('-s','A','shell','echo','hello'))
                passed.set()
        thread = threading.Thread(target=work)
        thread.start()
        try:
            a.control.paused.clear()
            self.assertTrue(passed.wait(1))
            self.assertTrue(b.control.paused.is_set())
        finally:
            a.control.cancelled.set()
            thread.join(2)

    def test_device_commands_cannot_cross_instance_after_target_switch(self):
        registry = SessionRegistry()
        a = registry.device('adb','A')
        with active_session(a):
            with self.assertRaisesRegex(RuntimeError, 'nhầm instance'):
                guard_command('adb', ('-s','B','shell','input','tap','1','2'))

    def test_reopen_dialog_keeps_control_of_same_instance(self):
        registry = SessionRegistry()
        p = Emulator('ld', Path('console.exe'), Path('adb.exe'))
        a = registry.instance(p, Instance('2','A'))
        a.control.paused.set()
        registry.bind(a, 'adb.exe', 'emulator-5558')
        self.assertIs(registry.instance(p, Instance('2','Renamed')), a)
        self.assertIs(registry.device('adb.exe','emulator-5558'), a)
        self.assertTrue(a.control.paused.is_set())

    def test_one_active_task_per_device_but_other_device_is_independent(self):
        registry = SessionRegistry()
        a, b = registry.device('adb','A'), registry.device('adb','B')
        self.assertTrue(a.begin())
        self.assertFalse(a.begin())
        self.assertTrue(b.begin())
        a.control.cancelled.set()
        self.assertFalse(b.control.cancelled.is_set())

    def test_idle_pause_is_retained_for_next_automation(self):
        registry = SessionRegistry()
        a = registry.device('adb','A')
        a.control.paused.set()
        self.assertTrue(a.begin())
        self.assertTrue(a.control.paused.is_set())
        a.control.cancelled.set()
        a.finish('stopped')
        self.assertTrue(a.begin())
        self.assertFalse(a.control.cancelled.is_set())
        self.assertFalse(a.control.paused.is_set())

class AppRoutingTests(unittest.TestCase):
    def test_app_workers_for_a_and_b_can_run_at_the_same_time(self):
        from omg3q_tool import App
        app = App.__new__(App)
        app.sessions = SessionRegistry()
        app.adb = 'adb'
        app.serial = Var('A')
        app.events = queue.Queue()
        app.status = Mock()
        app._refresh_busy = Mock()
        a_entered, b_entered, release = threading.Event(), threading.Event(), threading.Event()
        def task_a():
            guard_command('adb', ('-s','A','shell','echo','A'))
            a_entered.set()
            release.wait(2)
        def task_b():
            guard_command('adb', ('-s','B','shell','echo','B'))
            b_entered.set()
            release.wait(2)
        try:
            app._worker(task_a)
            self.assertTrue(a_entered.wait(1))
            app.serial.set('B')
            app._worker(task_b)
            self.assertTrue(b_entered.wait(1))
            self.assertTrue(app.sessions.device('adb','A').active)
            self.assertTrue(app.sessions.device('adb','B').active)
        finally:
            release.set()
            for _ in range(2): app.events.get(timeout=3)

    def test_paused_task_cannot_dispatch_adb_but_other_task_can(self):
        import omg3q_tool as tool
        registry = SessionRegistry()
        a, b = registry.device('adb','A'), registry.device('adb','B')
        a.control.paused.set()
        attempted, done = threading.Event(), threading.Event()
        def task_a():
            with active_session(a):
                attempted.set()
                try:
                    tool.run_adb('adb', '-s','A','shell','input','tap','1','2')
                except LaunchCancelled:
                    pass
                finally:
                    done.set()
        process_result = Mock(returncode=0, stdout=b'ok', stderr=b'')
        with patch.object(tool.subprocess, 'run', return_value=process_result) as dispatch:
            thread = threading.Thread(target=task_a)
            thread.start()
            try:
                self.assertTrue(attempted.wait(1))
                with active_session(b):
                    self.assertEqual(tool.run_adb('adb','-s','B','shell','echo','B'), b'ok')
                self.assertEqual(dispatch.call_count, 1)
                self.assertIn('B', dispatch.call_args.args[0])
                a.control.cancelled.set()
                self.assertTrue(done.wait(1))
                self.assertEqual(dispatch.call_count, 1)
            finally:
                a.control.cancelled.set()
                thread.join(2)
