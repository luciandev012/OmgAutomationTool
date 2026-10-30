import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from account_excel import AccountWorkbook
from excel_scripts import ScriptBatch, ExcelCycle
from excel_login_test import ExcelLoginTest
from login_engine import LoginEngine, InvalidCredentialsError, Detector
from task_sessions import InstanceSession, SessionRegistry
from emulator_instances import Instance
from test_account_excel import create_book
from test_login_engine import FakeDevice, FakeDetector, FakeClock


class ErrorDetector(FakeDetector):
    SCREENS = {**FakeDetector.SCREENS,
               13: {'invalid_credentials_8011', 'ok_button'},
               14: {'invalid_credentials_8011'},
               15: {'ok_button'}}


class ErrorDevice(FakeDevice):
    def clear_text(self):
        self.actions.append(('clear',))


class InvalidCredentialTests(unittest.TestCase):
    def engine(self, states, callback=None):
        device, clock = ErrorDevice(states), FakeClock()
        engine = LoginEngine(device, detector=ErrorDetector(), timeout=12,
                             clock=clock.now, sleeper=clock.sleep)
        result = engine.run('user', 'secret', on_invalid_credentials=(
            callback if callback else lambda: device.actions.append(('ERR',))))
        return result, device

    def test_8011_dismisses_ok_saves_err_then_clears_both_fields(self):
        result, device = self.engine([1, 2, 2, 2, 2, 13, 2, 2])
        self.assertEqual(result.status, 'invalid_credentials')
        actions = device.actions
        self.assertEqual(actions.count(('ERR',)), 1)
        self.assertEqual(actions.count(('clear',)), 2)
        self.assertLess(actions.index(('ERR',)), actions.index(('clear',)))
        self.assertEqual(len([a for a in actions if a[0] == 'text']), 2)

    def test_error_without_same_frame_ok_does_not_mark_or_clear(self):
        result, device = self.engine([1, 2, 2, 2, 2, 14] + [14] * 30)
        self.assertEqual(result.status, 'timeout')
        self.assertNotIn(('ERR',), device.actions)
        self.assertNotIn(('clear',), device.actions)
        self.assertEqual(len([a for a in device.actions if a[0] == 'tap']), 4)

    def test_ok_without_error_text_is_not_an_invalid_login(self):
        result, device = self.engine([1, 2, 2, 2, 2, 15] + [15] * 30)
        self.assertNotEqual(result.status, 'invalid_credentials')
        self.assertNotIn(('ERR',), device.actions)

    def test_failed_err_save_stops_before_clearing_or_switching(self):
        def failed_save():
            raise PermissionError('Workbook locked')
        result, device = self.engine([1, 2, 2, 2, 2, 13, 2, 2], failed_save)
        self.assertEqual(result.status, 'error')
        self.assertNotIn(('clear',), device.actions)

    def test_actual_templates_match_only_their_pixels(self):
        detector = Detector()
        frame = np.zeros((1080, 1920, 3), np.uint8)
        for name, x, y in [('invalid_credentials_8011', 700, 450), ('ok_button', 950, 600)]:
            template = detector.templates[name]
            h, w = template.shape
            frame[y:y+h, x:x+w] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
            self.assertIsNotNone(detector.find(frame, name, .99))
        self.assertIsNone(detector.find(np.zeros_like(frame), 'invalid_credentials_8011', .99))

    def test_batch_skips_invalid_account_preserves_err_after_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'account.xlsx'
            create_book(path, [0, 0, 0])
            book = AccountWorkbook(path)
            session = InstanceSession('A')
            session.connection = ('adb', 'A')
            session.begin()
            calls=[]
            class Cycle:
                def run(self, account):
                    calls.append(account.row)
                    if account.row == 2:
                        self.on_invalid_credentials(account)
                        raise InvalidCredentialsError('8011')
                    book._read()
                    assert book._value('D2') == 'ERR'
            result = ScriptBatch(book, 'A', [session], lambda _: Cycle(), Mock(), Mock()).run()
            self.assertEqual(calls, [2, 3, 4])
            self.assertEqual(result[0]['completed'], 2)
            self.assertEqual(result[0]['error'], '')
            book._read()
            self.assertEqual(book._value('D2'), 'ERR')
            self.assertEqual(book._value('E2'), '')
            self.assertEqual(book._value('E5'), '2')
            self.assertIsNone(AccountWorkbook(path).claim('A', object()))

    def test_test_mode_retries_next_row_without_consuming_successful_round(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'account.xlsx'
            create_book(path, [0, 0, 0])
            registry = SessionRegistry()
            provider = Mock(kind='mumu', label='MuMu', console=Path('manager'), adb=Path('adb'))
            provider.instances.return_value = [Instance('0', 'A', True)]
            provider.serial.return_value = 'emulator-5554'
            test = ExcelLoginTest(registry, provider, path, Mock(), Mock(), Mock(), Mock(),
                rounds=1, instance_name='A', target_stt=1, reuse_existing=True,
                log_path=Path(directory)/'audit.jsonl')
            attempts=[]
            def login(*args, **kwargs):
                attempts.append(args[0])
                if len(attempts) == 1:
                    kwargs['on_invalid_credentials']()
                    return Mock(status='invalid_credentials')
                return Mock(status='success')
            with patch.object(test, 'prepare'), patch('excel_login_test.LoginEngine') as engine, patch('excel_login_test.AdbDevice') as device:
                engine.return_value.run.side_effect = login
                device.return_value.run.return_value = b''
                result = test.run()
            self.assertEqual(attempts, ['user2', 'user3'])
            self.assertEqual(result[0]['completed'], 1)
            test.book._read()
            self.assertEqual(test.book._value('D2'), 'ERR')
            self.assertEqual(test.book._value('D3'), 'V')
            self.assertEqual(test.book._value('E2'), '')
            self.assertEqual(test.book._value('E3'), '1')

    def test_mark_error_checks_ownership_and_leaves_days_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'account.xlsx'
            create_book(path, [2])
            book = AccountWorkbook(path)
            owner=object()
            account=book.claim('B', owner)
            with self.assertRaises(ValueError):
                book.mark_error(account, object())
            book.mark_error(account, owner)
            book.mark_error(account, owner)  # The post-result path can confirm an existing ERR.
            book._read()
            self.assertEqual(book._value('D2'), 'ERR')
            self.assertEqual(book._value('G2'), '')
            self.assertEqual(book._value('T2'), '2')
            book.release_after_shutdown(owner)
            book._read()
            self.assertEqual(book._value('D2'), 'ERR')

    def test_native_variants_keep_original_template_and_match_high_confidence(self):
        detector=Detector()
        frame=np.zeros((1080,1920,3),np.uint8)
        for name,x,y in [('invalid_credentials_8011',707,503),('ok_button',930,579)]:
            self.assertIn(name,detector.templates)
            template=detector.templates[name+'__1920']
            h,w=template.shape
            frame[y:y+h,x:x+w]=cv2.cvtColor(template,cv2.COLOR_GRAY2BGR)
            match=detector.find(frame,name,.99)
            self.assertIsNotNone(match)
            self.assertEqual(match.name,name)
            self.assertEqual((match.x,match.y),(x,y))
