import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import cv2
import numpy as np

from account_excel import AccountWorkbook
from emulator_instances import Instance, LaunchControl, restart_instance
from excel_login_test import ExcelLoginTest
from login_engine import LoginEngine
from screen_observer import capture_screen
from screen_watchdog import ScreenWatchdog, ScreenStalledError
from task_sessions import SessionRegistry
from test_account_excel import create_book
from test_screen_observer import frame
from test_login_engine import FakeClock, FakeDevice, FakeDetector


class WatchdogTests(unittest.TestCase):
    def test_unchanged_frame_restarts_at_120_seconds_and_ignores_pixel_noise(self):
        clock = FakeClock()
        monitor = ScreenWatchdog(clock=clock.now)
        image = np.zeros((90,160,3),np.uint8)
        encode = lambda a: cv2.imencode('.png',a)[1].tobytes()
        monitor.observe(encode(image))
        clock.time = 119
        image[10,10] = 255
        monitor.observe(encode(image))
        clock.time = 120
        with self.assertRaises(ScreenStalledError):
            monitor.observe(encode(image))

    def test_real_screen_change_resets_only_its_own_clock(self):
        clock=FakeClock()
        a,b=(ScreenWatchdog(clock=clock.now) for _ in range(2))
        a.observe(frame()); b.observe(frame())
        clock.time=100
        a.observe(cv2.imencode('.png',np.full((90,160,3),255,np.uint8))[1].tobytes())
        clock.time=120
        a.check()
        with self.assertRaises(ScreenStalledError): b.check()

    def test_popup_is_rechecked_beyond_old_five_attempt_limit_without_sleep(self):
        popup,clear=frame(True),frame()
        runner=Mock(side_effect=[value for _ in range(7) for value in (popup,b'')]+[clear])
        sleeper=Mock()
        self.assertEqual(capture_screen('adb','B',runner,sleeper=sleeper),clear)
        sleeper.assert_not_called()
        taps=[c.args for c in runner.call_args_list if 'tap' in c.args]
        self.assertEqual(len(taps),7)
        self.assertTrue(all(c[-2:]==('960','1052') and c[2]=='B' for c in taps))

    def test_adb_capture_failures_use_same_inactivity_deadline(self):
        clock=FakeClock(); monitor=ScreenWatchdog(clock=clock.now)
        def broken(*args,**kwargs):
            clock.time+=30
            raise TimeoutError('ADB capture stalled')
        with self.assertRaises(ScreenStalledError):
            capture_screen('adb','B',broken,watchdog=monitor)
        self.assertEqual(clock.time,120)

    def test_watchdog_is_not_swallowed_as_login_error_or_cancel(self):
        device=FakeDevice([])
        device.capture=Mock(side_effect=ScreenStalledError('120s'))
        with self.assertRaises(ScreenStalledError):
            LoginEngine(device,detector=FakeDetector()).run('user','secret')

    def test_control_step_callback_never_adds_sleep(self):
        control=LaunchControl()
        with patch.object(control.cancelled,'wait') as wait:
            control.sleep(30)
        wait.assert_not_called()

    def test_restart_targets_only_stalled_instance(self):
        provider=Mock()
        provider.instances.return_value=[Instance('0','A',True),Instance('1','B',False)]
        control=LaunchControl()
        with patch('emulator_instances.open_instance') as opened:
            restart_instance(provider,Instance('1','B',True),'com.gs2.omg',Mock(),Mock(),control,Mock(),Mock())
        provider.shutdown.assert_called_once_with('1')
        self.assertEqual(opened.call_args.args[1],Instance('1','B',False))

    def test_stalled_worker_resumes_same_x_row_without_claiming_another(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'account.xlsx'; create_book(path,[0]*4)
            provider=Mock(kind='mumu',label='MuMu',console=Path('manager'),adb=Path('adb'))
            provider.instances.return_value=[Instance('0','A',True),Instance('1','B',True)]
            provider.serial.side_effect=lambda index:'emulator-'+index
            registry=SessionRegistry()
            test=ExcelLoginTest(registry,provider,path,Mock(),Mock(),Mock(),Mock(),rounds=1,
                               reuse_existing=True,log_path=Path(directory)/'audit.jsonl')
            seen=[]
            def login(username,password,**kwargs):
                seen.append(username)
                if len(seen)==1:raise ScreenStalledError('120s')
                return Mock(status='success')
            with patch.object(test,'prepare'),patch.object(test,'restart_stalled') as restart,patch('excel_login_test.LoginEngine') as engine,patch('excel_login_test.AdbDevice') as device:
                engine.return_value.run.side_effect=login
                device.return_value.run.return_value=b''
                result=test.worker(provider.instances()[1])
            self.assertEqual(result['completed'],1)
            self.assertEqual(seen,['user2','user2'])
            self.assertEqual(restart.call_count,1)
            test.book._read()
            self.assertEqual([test.book._value('D2'),test.book._value('E2')],['V','1'])
            self.assertEqual(test.book._value('D3'),'')

    def test_resume_validates_owner_status_and_unchanged_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'account.xlsx';create_book(path,[0,0])
            book=AccountWorkbook(path);owner=object();account=book.claim('A',owner)
            self.assertIs(book.validate_reservation(account,owner),account)
            with self.assertRaises(ValueError):book.validate_reservation(account,object())
            book.mark_error(account,owner)
            self.assertIsNone(book.validate_reservation(account,owner))
