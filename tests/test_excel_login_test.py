import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from account_excel import AccountWorkbook
from excel_login_test import ExcelLoginTest
from emulator_instances import Emulator, Instance, LaunchControl, open_instance
from task_sessions import SessionRegistry
from test_account_excel import create_book
from test_login_engine import FakeDevice, FakeDetector, FakeClock
from login_engine import LoginEngine


class ExcelLoginTestTests(unittest.TestCase):
    def test_no_timeout_login_waits_past_old_switch_limit_then_succeeds(self):
        clock = FakeClock()
        device = FakeDevice([5] * 40 + [1, 2, 2, 2, 2, 3, 4, 5, 8, 8])
        engine = LoginEngine(device, detector=FakeDetector(), timeout=None,
                             clock=clock.now, sleeper=clock.sleep, startup_delay=0)
        result = engine.run('user', 'pass', accept_terms=True)
        self.assertEqual(result.status, 'success')
        self.assertGreater(clock.time, 25)

    def test_no_timeout_login_is_still_cancellable(self):
        import threading
        stop = threading.Event()
        clock = FakeClock()
        def wait(seconds):
            clock.sleep(seconds)
            if clock.time > 40:
                stop.set()
        engine = LoginEngine(FakeDevice([0] * 100), detector=FakeDetector(), timeout=None,
                             stop=stop, clock=clock.now, sleeper=wait)
        self.assertEqual(engine.run('user', 'pass').status, 'cancelled')

    def test_uppercase_reservation_and_completion_use_existing_workbook_logic(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'account.xlsx'
            create_book(path, [0, 0])
            book = AccountWorkbook(path, status_marks=('X', 'V'))
            owner = object()
            account = book.claim('A', owner)
            book._read()
            self.assertEqual(book._value('D2'), 'X')
            book.complete(account, owner)
            book._read()
            self.assertEqual(book._value('D2'), 'V')
            self.assertEqual(book._value('E2'), '1')
            self.assertEqual(book._value('D4'), '1')
            self.assertEqual(book.claim('A', object()).row, 3)

    def test_two_workers_complete_three_distinct_accounts_each_and_keep_v(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'account.xlsx'
            create_book(path, [0]*8)
            provider = Mock(kind='mumu', label='MuMu', console=Path('manager'), adb=Path('adb'))
            provider.instances.return_value = [Instance('0','A'), Instance('1','B')]
            registry=SessionRegistry()
            runner=Mock(return_value=b'')
            def opened(provider, instance, *args, on_device, **kwargs):
                on_device('adb', instance.index)
            with patch('excel_login_test.open_instance', side_effect=opened), patch('excel_login_test.AdbDevice') as device, patch('excel_login_test.LoginEngine') as engine, patch.object(ExcelLoginTest,'prepare'):
                device.return_value.run.return_value=b''
                engine.return_value.run.return_value=Mock(status='success')
                test=ExcelLoginTest(registry,provider,path,runner,Mock(),Mock(),Mock(),log_path=Path(folder)/'audit.jsonl')
                results=test.run()
                self.assertEqual([r['completed'] for r in results],[3,3])
                self.assertEqual(device.return_value.run.call_count,12)
                test.book._read()
                self.assertEqual([test.book._value(f'D{r}') for r in range(2,8)], ['V']*6)
                self.assertEqual(test.book._value('E10'),'6')
                self.assertEqual(test.book._value('D8'),'')
                log=(Path(folder)/'audit.jsonl').read_text(encoding='utf-8')
                self.assertEqual(log.count('excel_reserved'),6)
                self.assertEqual(log.count('excel_completed'),6)
                self.assertNotIn('password',log)

    def test_launch_without_timeout_accepts_ready_device(self):
        provider=Mock(adb=Path('adb'))
        provider.serial.return_value='emulator-5554'
        runner=Mock(side_effect=[b'', b'1', b'topResumedActivity: com.gs2.omg/.Main'])
        result=open_instance(provider,Instance('0','A',True),'com.gs2.omg',runner,Mock(),LaunchControl(),Mock(),timeout=None)
        self.assertEqual(result,('adb','emulator-5554'))

    def test_no_fixed_waits_does_not_sleep_but_default_is_unchanged(self):
        clock = FakeClock()
        engine = LoginEngine(FakeDevice([]), detector=FakeDetector(), fixed_waits=False,
                             clock=clock.now, sleeper=clock.sleep)
        engine._wait(1.1)
        self.assertEqual(clock.time, 0)
        normal = LoginEngine(FakeDevice([]), detector=FakeDetector(),
                             clock=clock.now, sleeper=clock.sleep)
        normal._wait(1.1)
        self.assertEqual(clock.time, 1.1)

    def test_target_stt_does_not_take_other_blank_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'account.xlsx'
            create_book(path, [0] * 10)
            book = AccountWorkbook(path, status_marks=('X', 'V'))
            account = book.claim('A', object(), stt=9)
            self.assertEqual(account.row, 10)
            book._read()
            self.assertEqual(book._value('D10'), 'X')
            self.assertEqual(book._value('D2'), '')
            self.assertIsNone(book.claim('A', object(), stt=9))

    def test_existing_game_is_not_relaunched_before_login(self):
        clock = FakeClock()
        device = FakeDevice([1, 2, 2, 2, 2, 3, 4, 5, 8, 8])
        engine = LoginEngine(device, detector=FakeDetector(), timeout=35,
                             clock=clock.now, sleeper=clock.sleep)
        result = engine.run('user', 'pass', accept_terms=True, launch_on_start=False)
        self.assertEqual(result.status, 'success')
        self.assertFalse(any(action[0] == 'launch' for action in device.actions))
