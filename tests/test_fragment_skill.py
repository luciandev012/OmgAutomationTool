import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

from fragment_skill import FragmentDetector, FragmentSweepSkill
from login_engine import Match


class Replay:
    ready = True

    def __init__(self, *, screen="lobby", flags=(False, False, False), stall=None,
                 missing_target=False, selected=0):
        self.current = screen
        self.flags = list(flags)
        self.selected = selected
        self.target_checked = selected == 1
        self.stall = stall
        self.missing_target = missing_target
        self.running_ticks = 0

    def screen(self, frame):
        if self.current == "running":
            self.running_ticks += 1
            if self.running_ticks >= 5:
                self.current = "done"
        return self.current

    def selected_count(self, frame):
        return self.selected

    def target(self, frame):
        return None if self.missing_target else (self.target_checked, (50, 25))

    def options(self, frame):
        return tuple((value, (40, 10+i*10)) for i, value in enumerate(self.flags)) if self.current == "config" else None

    def find(self, frame, name, threshold=.9):
        return Match(name, 1, 1, 10, 10, 1.)

    def press(self, action):
        if action == self.stall:
            return
        transitions = {"cancel_unverified_config": "selection", "close_old_selection": "fragments",
                       "verify_main_lobby": "lobby", "open_hero_bag": "heroes",
                       "open_fragments_tab": "fragments", "open_many_fragments": "selection",
                       "open_quick_sweep": "config", "confirm_fragment_sweep": "selection",
                       "close_selection_after_sweep": "fragments"}
        if action in transitions:
            if action == "confirm_fragment_sweep":
                assert self.current == "done", "Never close a running batch"
            self.current = transitions[action]
        elif action == "select_dien_vi":
            self.target_checked, self.selected = True, 1
        elif action.startswith("enable_"):
            index = ("stamina", "war", "elite").index(action[7:])
            self.flags[index] = not self.flags[index]
        elif action == "start_fragment_sweep":
            assert self.selected == 1 and self.target_checked and all(self.flags)
            self.current = "running"


class FragmentTests(unittest.TestCase):
    def run_replay(self, replay, *, stop_on=None):
        instant = [0.]
        stop = threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            skill = FragmentSweepSkill(object(), detector=replay, stop=stop, evidence_root=Path(folder),
                                      clock=lambda: instant[0], sleeper=lambda seconds: instant.__setitem__(0, instant[0]+seconds))
            frame = np.zeros((60, 106, 3), np.uint8)

            def observe():
                skill._check()
                return frame

            def press(frame, point, action):
                skill._check()
                skill.actions.append(action)
                replay.press(action)
                if action == stop_on:
                    stop.set()

            skill._observe, skill._press = observe, press
            skill._save = lambda name: None
            skill._cancel_sweep = lambda: skill.actions.append("stop_game_fragment_sweep")
            skill.device = type("Device", (), {"swipe": lambda *args: None})()
            return skill.run_sweep()

    def test_selects_only_dien_vi_enables_three_options_runs_once_and_stops(self):
        replay = Replay()
        result = self.run_replay(replay)
        self.assertEqual(result.status, "completed", result.message)
        for action in ("select_dien_vi", "enable_stamina", "enable_war", "enable_elite",
                       "start_fragment_sweep", "confirm_fragment_sweep"):
            self.assertEqual(result.actions.count(action), 1, action)
        self.assertEqual(replay.current, "fragments")
        self.assertNotIn("log_stop", result.actions)

    def test_checked_options_are_preserved(self):
        result = self.run_replay(Replay(flags=(True, True, True)))
        self.assertEqual(result.status, "completed", result.message)
        self.assertFalse(any(action.startswith("enable_") for action in result.actions))

    def test_starting_on_config_rechecks_lobby_and_selection_before_ok(self):
        result = self.run_replay(Replay(screen="config"))
        self.assertEqual(result.status, "completed", result.message)
        self.assertEqual(result.actions[0], "cancel_unverified_config")
        self.assertLess(result.actions.index("verify_main_lobby"), result.actions.index("start_fragment_sweep"))

    def test_unknown_or_multiple_selected_heroes_never_sweep(self):
        for selected in (None, 2):
            with self.subTest(selected=selected):
                result = self.run_replay(Replay(selected=selected))
                self.assertEqual(result.status, "blocked")
                self.assertNotIn("start_fragment_sweep", result.actions)

    def test_missing_dien_vi_never_selects_another_hero_or_starts_sweep(self):
        result = self.run_replay(Replay(missing_target=True))
        self.assertEqual(result.status, "blocked")
        self.assertNotIn("select_dien_vi", result.actions)
        self.assertNotIn("open_quick_sweep", result.actions)
        self.assertNotIn("start_fragment_sweep", result.actions)

    def test_checkbox_stall_never_repeats_toggle_or_sends_ok(self):
        result = self.run_replay(Replay(stall="enable_war"))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.actions.count("enable_war"), 1)
        self.assertNotIn("start_fragment_sweep", result.actions)

    def test_ok_stall_never_sends_ok_twice_or_claims_completion(self):
        result = self.run_replay(Replay(stall="start_fragment_sweep"))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.actions.count("start_fragment_sweep"), 1)
        self.assertNotIn("confirm_fragment_sweep", result.actions)

    def test_resuming_finished_result_only_confirms_and_stops(self):
        result = self.run_replay(Replay(screen="done"))
        self.assertEqual(result.status, "completed", result.message)
        self.assertEqual(result.actions, ("confirm_fragment_sweep", "close_selection_after_sweep"))

    def test_stop_after_start_cancels_batch_and_starts_nothing_else(self):
        result = self.run_replay(Replay(), stop_on="start_fragment_sweep")
        self.assertEqual(result.status, "cancelled")
        self.assertIn("stop_game_fragment_sweep", result.actions)
        self.assertNotIn("confirm_fragment_sweep", result.actions)

    def test_real_selection_and_options_at_multiple_resolutions(self):
        detector = FragmentDetector()
        folder = Path(__file__).parent/"fixtures/fragment"
        cases = (("selection_entry", "selection", 0), ("selected_dien_vi", "selection", 1),
                 ("config_off", "config", None), ("config_1", "config", None),
                 ("config_2", "config", None), ("config_3", "config", None),
                 ("hero_menu", "heroes", None), ("fragments", "fragments", None),
                 ("running_check", "running", None), ("sweep_state", "done", None))
        for name, screen, selected in cases:
            raw = cv2.imread(str(folder/f"{name}.png"))
            for width in (1920, 1280, 960):
                with self.subTest(name=name, width=width):
                    resized = cv2.resize(raw, (width, round(raw.shape[0]*width/raw.shape[1])), interpolation=cv2.INTER_AREA)
                    _, png = cv2.imencode(".png", resized)
                    frame = detector.decode(png.tobytes())
                    self.assertEqual(detector.screen(frame), screen)
                    if selected is not None:
                        self.assertEqual(detector.selected_count(frame), selected)
                        self.assertEqual(detector.target(frame)[0], bool(selected))
                    if screen == "config":
                        flags = tuple(item[0] for item in detector.options(frame))
                        enabled = 0 if name == "config_off" else int(name[-1])
                        self.assertEqual(flags, tuple(i < enabled for i in range(3)))

    def test_stop_taps_only_a_running_fragment_batch_not_the_done_button(self):
        folder = Path(__file__).parent/"fixtures/fragment"
        for name, expected in (("running_check", 1), ("sweep_state", 0)):
            with self.subTest(name=name):
                calls = []
                png = (folder/f"{name}.png").read_bytes()
                device = type("Device", (), {"capture": lambda self: png,
                                               "tap": lambda self, *args: calls.append(args)})()
                skill = FragmentSweepSkill(device)
                skill._cancel_sweep()
                self.assertEqual(len(calls), expected)

    def test_a_log_without_fragment_selection_context_is_not_accepted(self):
        raw = cv2.imread(str(Path(__file__).parent/"fixtures/fragment/sweep_state.png"))
        h, w = raw.shape[:2]
        raw[round(h*.77):round(h*.86), round(w*.12):round(w*.27)] = 0
        _, png = cv2.imencode(".png", raw)
        detector = FragmentDetector()
        self.assertIsNone(detector.screen(detector.decode(png.tobytes())))


if __name__ == "__main__":
    unittest.main()
