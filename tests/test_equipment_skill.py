import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

from equipment_skill import EquipmentDetector, EquipmentSkill
from login_engine import Match


class Clock:
    def __init__(self):
        self.value = 0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Device:
    def __init__(self, screens):
        self.screens = iter(screens)
        self.current = 0
        self.actions = []

    def capture(self):
        self.current = next(self.screens, self.current)
        return cv2.imencode('.png', np.full((90, 160, 3), self.current, np.uint8))[1].tobytes()

    def tap(self, x, y, frame_size):
        self.actions.append((x, y))


class Detector:
    ready = True

    def decode(self, png):
        return cv2.imdecode(np.frombuffer(png, np.uint8), 1)

    def find(self, frame, name):
        scene = int(frame[0, 0, 0])
        names = {'formation_title': 10, 'equipment_menu': 20, 'quick_equip': 30, 'quick_enhance': 40}
        if scene == 7:
            prompts = {'achievement_title': 10, 'achievement_equipment': 20, 'achievement_dismiss': 60}
            if name in prompts:
                return Match(name, prompts[name], 10, 2, 2, 1.)
        if scene in (5, 6):
            prompts = {'enhance_prompt': 10, 'enhance_ok': 50}
            if scene == 5:
                prompts['enhance_silver'] = 20
            if name in prompts:
                return Match(name, prompts[name], 10, 2, 2, 1.)
        if scene in (1, 2, 3, 4) and name in names and (scene != 1 or name not in ('quick_equip', 'quick_enhance')):
            return Match(name, names[name], 10, 2, 2, 1.)
        return None

    def read_stats(self, frame):
        return {1: (100, 10, 5, 5), 2: (100, 10, 5, 5),
                3: (200, 20, 10, 10), 4: (300, 30, 15, 15)}.get(int(frame[0, 0, 0]))


class EquipmentTests(unittest.TestCase):
    def run_skill(self, screens, stop=None):
        clock, device = Clock(), Device(screens)
        with tempfile.TemporaryDirectory() as folder:
            skill = EquipmentSkill(device, detector=Detector(), navigation_detector=Detector(),
                                   clock=clock.now, sleeper=clock.sleep, timeout=8,
                                   evidence_root=Path(folder), stop=stop)
            result = skill.run()
            if result.screenshot:
                self.assertTrue(Path(result.screenshot).is_file())
        return result, device

    def test_equip_then_enhance_each_sent_once_with_verified_changes(self):
        result, device = self.run_skill([2] * 4 + [3, 3, 4, 4])
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.before_stats, (100, 10, 5, 5))
        self.assertEqual(result.after_stats, (300, 30, 15, 15))
        self.assertTrue(result.equip_changed and result.enhance_changed)
        self.assertEqual([x for x, y in device.actions], [372, 492])

    def test_unchanged_stats_stop_without_repeat_or_false_success(self):
        result, device = self.run_skill([2] * 20)
        self.assertEqual(result.status, 'no_action')
        self.assertEqual(len(device.actions), 2)

    def test_unknown_dialog_after_equip_stops_before_enhance(self):
        result, device = self.run_skill([2] * 4 + [0] * 20)
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(len(device.actions), 1)

    def test_unknown_initial_screen_never_taps(self):
        result, device = self.run_skill([0] * 20)
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(device.actions, [])

    def test_silver_confirmation_is_verified_then_accepted_once(self):
        result, device = self.run_skill([2] * 4 + [3, 3, 5, 5, 4, 4])
        self.assertEqual(result.status, 'success')
        self.assertTrue(result.enhance_changed)
        self.assertEqual([x for x, y in device.actions], [372, 492, 612])

    def test_stale_silver_prompt_never_repeats_confirmation(self):
        result, device = self.run_skill([2] * 4 + [3, 3] + [5] * 30)
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(len(device.actions), 3)

    def test_equipment_achievement_is_dismissed_before_verifying_stats(self):
        result, device = self.run_skill([2] * 4 + [3, 3, 5, 5, 7, 4, 4])
        self.assertEqual(result.status, 'success')
        self.assertTrue(result.enhance_changed)
        self.assertEqual([x for x, y in device.actions], [372, 492, 612, 732])

    def test_prompt_without_verified_silver_text_is_not_confirmed(self):
        result, device = self.run_skill([2] * 4 + [3, 3] + [6] * 30)
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(len(device.actions), 2)

    def test_cancel_before_first_observation(self):
        stop = threading.Event()
        stop.set()
        result, device = self.run_skill([2], stop)
        self.assertEqual(result.status, 'cancelled')
        self.assertEqual(device.actions, [])

    def test_unknown_numeric_glyph_is_rejected(self):
        detector = EquipmentDetector()
        frame = np.zeros((597, 1061, 3), np.uint8)
        frame[191:208, 930:940] = 255
        self.assertIsNone(detector.read_stats(frame))

    def test_real_stat_crops_including_touching_71_are_read_correctly(self):
        detector = EquipmentDetector()
        expected = {
            'formation_before': (43310, 5306, 1603, 1603),
            'observed_after_equip': (60828, 7263, 2248, 2248),
            'ton_sach_before': (294204, 42964, 21617, 19251),
            'ton_sach_after': (371378, 55328, 25991, 23488),
        }
        for name, values in expected.items():
            with self.subTest(screen=name):
                crop = cv2.imdecode(np.frombuffer((Path(__file__).parent / 'fixtures/equipment' / (name + '.png')).read_bytes(), np.uint8), 1)
                frame = np.zeros((597, 1061, 3), np.uint8)
                frame[189:314, 923:1000] = crop
                self.assertEqual(detector.read_stats(frame), values)


if __name__ == '__main__':
    unittest.main()
