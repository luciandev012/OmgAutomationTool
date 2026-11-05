import json
import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

from daily_tasks_skill import DailyTasksDetector, DailyTasksSkill
from login_engine import Match


class FakeDevice:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.current = 0
        self.actions = []
        self.time = 0

    def capture(self):
        self.current = next(self.frames, self.current)
        return cv2.imencode('.png', np.full((90,160,3),self.current,np.uint8))[1].tobytes()

    def tap(self, x, y, frame_size):
        self.actions.append((x,y,frame_size))

    def sleep(self, seconds):
        self.time += seconds


class FakeDetector:
    ready = True
    SCREENS = {0:set(),1:{'mission_entry'},2:{'mission_title','daily_tab','daily_active'},
               3:{'achievement_title','daily_tab'},4:set(),5:{'mission_entry'}}
    decode = staticmethod(lambda png:cv2.imdecode(np.frombuffer(png,np.uint8),1))

    def find(self, frame, name, *args):
        value = int(frame[0,0,0])
        if name not in self.SCREENS[value]:
            return None
        x,y = (130,15) if name=='mission_entry' else (30,75)
        return Match(name,x,y,10,10,.99)

    def main_lobby(self, frame):
        return int(frame[0,0,0]) == 1


class DailyTasksTests(unittest.TestCase):
    def run_skill(self, frames, detector=None, stop=None, preview=None, progress=None):
        device = FakeDevice(frames)
        with tempfile.TemporaryDirectory() as folder:
            skill = DailyTasksSkill(device,detector=detector or FakeDetector(),stop=stop,
                clock=lambda:device.time,sleeper=device.sleep,timeout=5,
                evidence_root=Path(folder),preview=preview,progress=progress)
            result = skill.run()
            record = json.loads((Path(result.evidence_dir)/'result.json').read_text(encoding='utf-8'))
        return result,device,record

    def test_opens_scroll_once_and_stops_on_daily_page(self):
        result,device,record = self.run_skill([1,1,4,2,2])
        self.assertEqual(result.status,'opened')
        self.assertEqual(result.actions,('open_missions',))
        self.assertEqual(device.actions,[(1620,240,(160,90))])
        self.assertEqual(record['actions'],['open_missions'])

    def test_already_daily_has_no_input(self):
        result,device,_ = self.run_skill([2,2])
        self.assertEqual(result.status,'opened')
        self.assertFalse(device.actions)

    def test_achievement_switches_only_to_daily_tab(self):
        result,device,_ = self.run_skill([3,3,2,2])
        self.assertEqual((result.status,result.actions),('opened',('select_daily_tab',)))
        self.assertEqual(len(device.actions),1)

    def test_scroll_remembers_achievement_tab(self):
        result,device,_ = self.run_skill([1,1,3,3,2,2])
        self.assertEqual(result.actions,('open_missions','select_daily_tab'))
        self.assertEqual(len(device.actions),2)

    def test_time_machine_or_unknown_never_receives_input(self):
        for frame in (0,5):
            with self.subTest(frame=frame):
                result,device,_ = self.run_skill([frame]*10)
                self.assertEqual(result.status,'blocked')
                self.assertFalse(device.actions)

    def test_single_lobby_flash_is_not_clicked(self):
        result,device,_ = self.run_skill([1,0,0])
        self.assertEqual(result.status,'blocked')
        self.assertFalse(device.actions)

    def test_unchanged_lobby_never_repeats_the_scroll_click(self):
        result,device,_ = self.run_skill([1]*20)
        self.assertEqual(result.status,'blocked')
        self.assertEqual(len(device.actions),1)

    def test_unknown_overlay_after_click_stops_without_more_input(self):
        result,device,_ = self.run_skill([1,1]+[0]*20)
        self.assertEqual(result.status,'blocked')
        self.assertEqual(result.actions,('open_missions',))

    def test_missing_samples_sends_no_input(self):
        detector = FakeDetector();detector.ready=False
        result,device,_ = self.run_skill([1],detector=detector)
        self.assertEqual(result.status,'needs_samples')
        self.assertFalse(device.actions)

    def test_stop_before_run_or_during_preview_prevents_input(self):
        stop = threading.Event();stop.set()
        result,device,_ = self.run_skill([1],stop=stop)
        self.assertEqual(result.status,'cancelled')
        self.assertFalse(device.actions)
        stop.clear()
        result,device,_ = self.run_skill([1],stop=stop,preview=lambda png:stop.set())
        self.assertEqual(result.status,'cancelled')
        self.assertFalse(device.actions)

    def test_stop_in_navigation_progress_prevents_the_click(self):
        stop = threading.Event()
        result,device,_ = self.run_skill([1,1],stop=stop,progress=lambda text:stop.set())
        self.assertEqual(result.status,'cancelled')
        self.assertFalse(device.actions)

    def test_real_screens_main_daily_achievement_and_dimmed_overlay(self):
        detector = DailyTasksDetector()
        self.assertTrue(detector.ready)
        folder=Path(__file__).parent/'fixtures/daily'
        lobby=detector.decode((folder/'main_lobby.png').read_bytes())
        self.assertTrue(detector.main_lobby(lobby))
        self.assertIsNotNone(detector.find(lobby,'mission_entry',.94))
        self.assertFalse(detector.main_lobby((lobby*.4).astype(np.uint8)))
        self.assertIsNone(detector.find((lobby*.4).astype(np.uint8),'mission_entry',.94))
        daily=detector.decode((folder/'daily_page.png').read_bytes())
        achievement=detector.decode((folder/'achievement_page.png').read_bytes())
        self.assertIsNotNone(detector.find(daily,'mission_title',.94))
        self.assertIsNotNone(detector.find(daily,'daily_active',.94))
        self.assertIsNone(detector.find(achievement,'daily_active',.94))
        self.assertIsNotNone(detector.find(achievement,'achievement_title',.94))
        self.assertIsNotNone(detector.find(achievement,'daily_tab',.94))
        self.assertFalse(detector.main_lobby(daily))

    def test_wide_screen_preserves_left_lobby_and_right_scroll_anchors(self):
        detector = DailyTasksDetector()
        frame=detector.decode((Path(__file__).parent/'fixtures/daily/main_lobby.png').read_bytes())
        wide=np.zeros((597,1280,3),np.uint8)
        wide[:,:500]=frame[:,:500]
        wide[:,-180:]=frame[:,-180:]
        self.assertTrue(detector.main_lobby(wide))
        scroll=detector.find(wide,'mission_entry',.94)
        self.assertIsNotNone(scroll)
        self.assertTrue(scroll.center[0]>1150)


if __name__=='__main__':
    unittest.main()
