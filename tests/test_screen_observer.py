import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from login_engine import AdbDevice
from screen_observer import _hint_template, capture_screen


def frame(with_hint=False):
    image = np.zeros((1080, 1920, 3), np.uint8)
    if with_hint:
        template = _hint_template()
        h, w = template.shape
        image[1020:1020+h, 700:700+w] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
    return cv2.imencode('.png', image)[1].tobytes()


class ScreenObserverTests(unittest.TestCase):
    def test_all_device_observers_dismiss_repeated_popups_and_return_fresh_screen(self):
        popup, clear = frame(True), frame()
        runner = Mock(side_effect=[popup, b'', popup, b'', clear])
        result = capture_screen('adb', 'device-A', runner, sleeper=lambda _: None)
        self.assertEqual(result, clear)
        taps = [c.args for c in runner.call_args_list if 'tap' in c.args]
        self.assertEqual(taps, [('adb', '-s', 'device-A', 'shell', 'input', 'tap', '960', '540')] * 2)

    def test_unknown_screen_is_returned_without_tapping(self):
        clear = frame()
        runner = Mock(return_value=clear)
        self.assertEqual(AdbDevice('adb', 'B', runner, None).capture(), clear)
        self.assertEqual(runner.call_count, 1)

    def test_persistent_hint_stops_instead_of_returning_stale_frame(self):
        runner = Mock(return_value=frame(True))
        with self.assertRaisesRegex(ValueError, 'chưa đóng'):
            capture_screen('adb', 'B', runner, sleeper=lambda _: None, max_dismissals=1)
        self.assertEqual(sum('tap' in c.args for c in runner.call_args_list), 1)

