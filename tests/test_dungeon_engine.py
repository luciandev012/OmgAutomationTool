import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import dungeon_engine as dungeon
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
        return cv2.imencode(".png", np.full((90, 160, 3), self.current, np.uint8))[1].tobytes()

    def tap(self, x, y, frame_size):
        self.actions.append(("tap", x, y))

    def swipe(self, *args):
        self.actions.append(("swipe",))


class Detector:
    results_ready = True
    SCREENS = {
        1: {"time_machine", "dungeon_entry"},  # Ordinary dungeon must not be opened here.
        2: {"event_home", "dungeon_entry"},
        3: {"chapter_screen", "chapter_frontier"},
        4: {"stage_screen", "stage_frontier"},
        5: {"stage_dialog", "fight"},
        6: {"victory", "next_stage"},
        7: {"defeat", "result_exit"},
        8: {"victory", "result_exit"},
        9: {"stage_screen", "map_back"},
        10: {"victory", "defeat", "next_stage"},
        11: {"victory"},
        12: {"battle_screen", "battle_skip"},
        13: {"event_intro", "intro_dismiss"},
    }

    @staticmethod
    def decode(png):
        return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)

    def find(self, frame, name, threshold=.87):
        if name not in self.SCREENS.get(int(frame[0, 0, 0]), set()):
            return None
        # Each action has a unique x coordinate for checking actual routing.
        names = list(dungeon.DungeonDetector.REGIONS)
        return Match(name, 10 + names.index(name) * 5, 20, 4, 4, 1)


class DungeonTests(unittest.TestCase):
    def run_engine(self, screens, detector=None, **options):
        clock, device = Clock(), Device(screens)
        engine = dungeon.DungeonEngine(device, detector=detector or Detector(), clock=clock.now,
                                       sleeper=clock.sleep, navigation_timeout=8, battle_timeout=12)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run(**options)
        return result, device

    def test_navigate_win_continue_then_defeat_stops_without_more_input(self):
        result, device = self.run_engine([1, 2, 3, 4, 5, 0, 6, 6, 6, 0, 5, 0, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 1))
        names = ["time_machine", "dungeon_entry", "chapter_frontier", "stage_frontier", "fight", "next_stage", "fight"]
        indexes = list(dungeon.DungeonDetector.REGIONS)
        expected_x = [round((12 + indexes.index(name) * 5) * 1920 / 160) for name in names]
        self.assertEqual([a[1] for a in device.actions], expected_x)

    def test_repeated_win_screen_is_counted_once_and_continue_clicked_once(self):
        result, device = self.run_engine([5, 6, 6] + [6] * 30)
        self.assertEqual((result.status, result.wins), ("timeout", 1))
        self.assertEqual(len(device.actions), 2)

    def test_fight_button_is_not_retried_while_waiting_for_result(self):
        result, device = self.run_engine([5] * 40)
        self.assertEqual((result.status, result.wins), ("timeout", 0))
        self.assertEqual(len(device.actions), 1)

    def test_losing_first_battle_stops_with_zero_wins(self):
        result, device = self.run_engine([5, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 0))
        self.assertEqual(len(device.actions), 1)

    def test_max_wins_stops_before_next_stage_is_clicked(self):
        result, device = self.run_engine([5, 6, 6], max_wins=1)
        self.assertEqual((result.status, result.wins), ("limit", 1))
        self.assertEqual(len(device.actions), 1)

    def test_old_result_is_never_counted_or_dismissed(self):
        result, device = self.run_engine([6, 6])
        self.assertEqual((result.status, result.wins), ("existing_result", 0))
        self.assertEqual(device.actions, [])

    def test_unknown_screen_produces_no_input(self):
        result, device = self.run_engine([0] * 30)
        self.assertEqual(result.status, "timeout")
        self.assertEqual(device.actions, [])

    def test_ambiguous_result_never_continues(self):
        result, device = self.run_engine([5, 10])
        self.assertEqual(result.status, "unknown")
        self.assertEqual(len(device.actions), 1)

    def test_win_without_recognized_button_stops(self):
        result, device = self.run_engine([5, 11, 11])
        self.assertEqual((result.status, result.wins), ("unknown", 1))
        self.assertEqual(len(device.actions), 1)

    def test_reward_animation_can_delay_dismiss_hint_without_recounting_win(self):
        result, device = self.run_engine([5, 11, 11, 11, 8, 0, 4, 5, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 1))
        self.assertEqual(len(device.actions), 4)

    def test_game_can_return_to_map_before_result_hint_is_observed(self):
        result, device = self.run_engine([5, 11, 11, 0, 4, 5, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 1))
        self.assertEqual(len(device.actions), 3)

    def test_combat_can_start_directly_after_selecting_stage(self):
        result, device = self.run_engine([4, 12, 12, 6, 6], max_wins=1)
        self.assertEqual((result.status, result.wins), ("limit", 1))
        self.assertEqual(len(device.actions), 2)  # Select the stage, then skip animation.

    def test_game_skip_button_is_pressed_only_once_per_battle(self):
        result, device = self.run_engine([5, 12, 12, 12, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 0))
        self.assertEqual(len(device.actions), 2)

    def test_event_intro_is_dismissed_before_opening_event_dungeon(self):
        result, device = self.run_engine([1, 13, 2, 3, 4, 5, 7, 7])
        self.assertEqual(result.status, "defeat")
        self.assertEqual(len(device.actions), 6)

    def test_return_to_stage_map_after_win_starts_next_battle(self):
        result, device = self.run_engine([5, 8, 8, 0, 4, 5, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 1))
        self.assertEqual(len(device.actions), 4)

    def test_missing_result_templates_prevents_starting_combat(self):
        detector = Detector()
        detector.results_ready = False
        result, device = self.run_engine([5], detector=detector)
        self.assertEqual(result.status, "needs_samples")
        self.assertEqual(device.actions, [])

    def test_stop_between_observation_and_input_prevents_tap(self):
        stop = threading.Event()
        device = Device([5])
        engine = dungeon.DungeonEngine(device, detector=Detector(), stop=stop,
                                       preview=lambda png: stop.set())
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run()
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(device.actions, [])

    def test_bounded_map_scan_without_marker_does_not_click_a_random_stage(self):
        result, device = self.run_engine([9] * 50)
        self.assertEqual(result.status, "no_frontier")
        self.assertEqual(device.actions, [("swipe",)] * 3)

    def test_decoder_preserves_ui_shape_on_phone_and_emulator(self):
        for width, height in ((1280, 597), (1920, 1080)):
            raw = cv2.imencode(".png", np.zeros((height, width, 3), np.uint8))[1].tobytes()
            frame = dungeon.DungeonDetector.decode(raw)
            self.assertEqual(frame.shape[:2], (597, round(width * 597 / height)))

    def test_visible_template_is_detected_but_dimmed_background_is_rejected(self):
        detector = dungeon.DungeonDetector()
        template = detector.templates["fight"]
        frame = np.zeros((597, 1280, 3), np.uint8)
        h, w = template.shape
        frame[455:455+h, 803:803+w] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
        self.assertIsNotNone(detector.find(frame, "fight"))
        self.assertIsNone(detector.find((frame * .4).astype(np.uint8), "fight"))

    def test_actual_result_banner_templates_do_not_match_opposite_outcome(self):
        detector = dungeon.DungeonDetector()
        self.assertTrue(detector.results_ready)
        for name, other in (("victory", "defeat"), ("defeat", "victory")):
            frame = np.zeros((597, 1061, 3), np.uint8)
            template = detector.templates[name]
            h, w = template.shape
            frame[40:40+h, 430:430+w] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
            self.assertIsNotNone(detector.find(frame, name))
            self.assertIsNone(detector.find(frame, other))

    def test_marker_variants_keep_the_same_tap_anchor_height(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder)
            template = np.random.default_rng(4).integers(0, 255, (63, 63), dtype=np.uint8)
            (path / "stage_frontier__example.png").write_bytes(cv2.imencode(".png", template)[1].tobytes())
            detector = dungeon.DungeonDetector(path)
            frame = np.zeros((597, 1280, 3), np.uint8)
            frame[120:183, 300:363] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
            match = detector.find(frame, "stage_frontier")
            self.assertEqual(match.height, 44)
            self.assertLessEqual(abs(match.center[1] - 151), 1)


if __name__ == "__main__":
    unittest.main()
