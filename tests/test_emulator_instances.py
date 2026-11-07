import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from emulator_instances import (Emulator, Instance, LaunchControl, LaunchCancelled,
                                detect_emulators, open_instance)


class InstanceTests(unittest.TestCase):
    def test_mumu_bootstraps_main_and_waits_for_rpc_before_launching_vm(self):
        p = Emulator('mumu', Path('manager'), Path('adb'))
        local = '{"0":{"index":"0","info_source":"local"}}'
        rpc = '{"0":{"index":"0","info_source":"rpc"}}'
        with patch.object(Emulator, 'command', side_effect=[local, '{}', rpc, '{}']) as command:
            p.launch('0')
        self.assertEqual([call.args for call in command.call_args_list],
            [('info','-v','all'),('main','launch'),('info','-v','all'),('control','-v','0','launch')])

    def test_cached_info_and_successful_main_launch_do_not_prove_readiness(self):
        p = Emulator('mumu', Path('manager'), Path('adb'))
        with patch.object(Emulator,'command',return_value='{"0":{"index":"0","info_source":"local"}}') as command:
            with self.assertRaisesRegex(Exception, 'RPC'):
                p.ensure_main_ready(timeout=0)
        self.assertFalse(any(c.args[0]=='control' for c in command.call_args_list))

    def test_mumu_only_installed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manager = root / 'MuMuManager.exe'
            manager.touch(); (root / 'adb.exe').touch()
            with patch.dict('os.environ', {'OMG_MUMU_MANAGER': ''}):
                providers = detect_emulators(manager, None)
            self.assertEqual([p.kind for p in providers], ['mumu'])

    def test_ld_only_installed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manager = root / 'dnmultiplayer.exe'
            manager.touch(); (root / 'adb.exe').touch(); (root / 'ldconsole.exe').touch()
            with patch.dict('os.environ', {'OMG_MUMU_MANAGER': ''}):
                providers = detect_emulators(root / 'missing.exe', manager)
            self.assertEqual([p.kind for p in providers], ['ld'])

    def test_mumu_list_includes_stopped_instances_and_real_adb_port(self):
        p = Emulator('mumu', Path('manager'), Path('adb'))
        with patch.object(Emulator, 'command', return_value='{"1":{"index":"1","name":"Clone","is_process_started":true,"adb_port":16416},"4":{"index":"4","name":"Off"}}'):
            rows = p.instances()
        self.assertEqual(rows[0].serial, '127.0.0.1:16416')
        self.assertFalse(rows[1].running)

    def test_ld_list_and_serial_use_selected_index(self):
        p = Emulator('ld', Path('console'), Path('adb'))
        with patch.object(Emulator, 'command', return_value='2,Clone,0,0,1,200,300,1920,1080,280'):
            self.assertEqual(p.instances(), [Instance('2', 'Clone', True)])
        with patch.object(Emulator, 'command', return_value='emulator-5558\n') as command:
            self.assertEqual(p.serial('2'), 'emulator-5558')
            self.assertIn('2', command.call_args.args)

    def test_both_provider_flows_launch_only_selected_instance_and_game(self):
        for kind, serial in [('mumu', '127.0.0.1:16416'), ('ld', 'emulator-5558')]:
            with self.subTest(kind=kind):
                p = Mock(adb=Path('adb'))
                p.serial.return_value = serial
                adb = Mock(side_effect=lambda *a, **k: b'mResumedActivity: ActivityRecord{ com.gs2.omg/.Main }' if 'dumpsys' in a else b'1')
                launch_game = Mock()
                result = open_instance(p, Instance('2', 'Clone'), 'com.gs2.omg', adb, launch_game, LaunchControl(), Mock())
                p.launch.assert_called_once_with('2')
                p.serial.assert_called_once_with('2')
                launch_game.assert_called_once_with('adb', serial, 'com.gs2.omg')
                self.assertEqual(result, ('adb', serial))
                for call in adb.call_args_list:
                    if '-s' in call.args:
                        self.assertEqual(call.args[call.args.index('-s') + 1], serial)

    def test_cancel_before_launch_does_not_start_vm(self):
        control = LaunchControl(); control.cancelled.set()
        p = Mock()
        with self.assertRaises(LaunchCancelled):
            open_instance(p, Instance('3','test'), 'com.gs2.omg', Mock(), Mock(), control, Mock())
        p.launch.assert_not_called()

    def test_cancel_while_paused_releases_worker(self):
        control = LaunchControl(); control.paused.set()
        thread = threading.Thread(target=lambda: (time.sleep(.05), control.cancelled.set()))
        thread.start()
        with self.assertRaises(LaunchCancelled):
            control.checkpoint()
        thread.join()

    def test_running_instance_not_relaunched(self):
        p = Mock(adb=Path('adb')); p.serial.return_value = 'emulator-5554'
        adb = Mock(side_effect=[b'', b'1', b'topResumedActivity: com.gs2.omg/.Main'])
        open_instance(p, Instance('0','test',True), 'com.gs2.omg', adb, Mock(), LaunchControl(), Mock())
        p.launch.assert_not_called()

    def test_timeout_does_not_open_game(self):
        game = Mock()
        with self.assertRaisesRegex(Exception, 'Hết thời gian'):
            open_instance(Mock(), Instance('0','test'), 'com.gs2.omg', Mock(), game, LaunchControl(), Mock(), timeout=0)
        game.assert_not_called()
