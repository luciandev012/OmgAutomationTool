import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

from assistant_skill import AssistantDetector, AssistantRow, AssistantSkill, TARGETS
from login_engine import Match


class Replay:
    ready = True

    def __init__(self, *, configured=False, empty=False, stall=False, missing_result=False):
        self.tab = 0
        self.overlay = False
        self.result_ticks = 0
        self.closed_at = []
        self.executions = []
        self.counts = dict(beast=4, demon=5, nightmare=3, dungeon_hell=3,
                           arena=20, reset=1, hell=4, elite=3, slash=3, weapon=3)
        if configured:
            self.counts.update({k: v for targets in TARGETS for k, v in targets.items()})
        if empty:
            self.counts = dict.fromkeys(self.counts, 0)
        self.quick = {0: not empty, 1: not empty, 3: not empty}
        self.stall, self.missing_result = stall, missing_result
        self.scrolled = False

    def page(self, frame):
        return None if self.overlay else self.tab

    def main_lobby(self, frame):
        return False

    def find(self, frame, name, threshold=.9):
        return Match(name, 1, 1, 10, 10, 1.)

    def quick_enabled(self, frame):
        return self.quick.get(self.tab, False)

    def row(self, frame, name):
        if name == "elite" and not self.scrolled:
            return None
        return AssistantRow(self.counts[name], (40, 10), (20, 10),
                            (50, 10) if name == "arena" else None,
                            (10, 10) if name == "arena" else None)

    def result_visible(self, frame):
        return self.overlay

    def result_strip(self, frame):
        self.result_ticks += 1
        return np.full((4, 4, 3), min(self.result_ticks, 5)*10, np.uint8)

    def press(self, action, now):
        if action.startswith("open_tab_"):
            assert not self.overlay, "Must dismiss results before changing tabs"
            self.tab = int(action[-1])
            self.scrolled = False
        elif action.startswith("set_"):
            _, name, before, target = action.split("_")
            if not self.stall:
                step = 10 if name == "arena" and abs(int(target)-int(before)) >= 10 else 1
                self.counts[name] += step if int(target) > int(before) else -step
        elif action.startswith("execute_tab_"):
            self.executions.append((self.tab, dict(self.counts)))
            self.overlay = not self.missing_result
            self.result_ticks = 0
        elif action == "close_assistant_result":
            assert self.result_ticks >= 8, "Must wait for a stable result panel"
            self.closed_at.append(now)
            self.overlay = False
            for name in TARGETS[self.tab] or ("beast", "demon", "nightmare", "dungeon_hell"):
                self.counts[name] = 0
            self.quick[self.tab] = False


class AssistantTests(unittest.TestCase):
    def run_replay(self, replay, stop_on=None):
        instant = [0.]
        stop = threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            skill = AssistantSkill(object(), detector=replay, evidence_root=Path(folder), stop=stop,
                                   clock=lambda: instant[0], sleeper=lambda seconds: instant.__setitem__(0, instant[0]+seconds))
            frame = np.zeros((60, 106, 3), np.uint8)

            def observe():
                skill._check()
                return frame

            def press(frame, point, action):
                skill._check()
                skill.actions.append(action)
                replay.press(action, instant[0])
                if stop_on and action.startswith(stop_on):
                    stop.set()

            def scroll(up=False):
                skill._check()
                replay.scrolled = not up
                skill.actions.append("scroll_up" if up else "scroll_down")

            skill._observe, skill._press, skill._scroll = observe, press, scroll
            return skill.run_assistant()

    def test_configures_all_targets_executes_once_and_dismisses_before_next_tab(self):
        replay = Replay()
        result = self.run_replay(replay)
        self.assertEqual(result.status, "completed", result.message)
        self.assertEqual([tab for tab, _ in replay.executions], list(range(5)))
        for tab, counts in replay.executions:
            for name, target in TARGETS[tab].items():
                self.assertEqual(counts[name], target)
        self.assertEqual(result.actions.count("close_assistant_result"), 5)
        self.assertEqual(sum(a.startswith("set_arena_") for a in result.actions), 1)
        self.assertIn("scroll_down", result.actions)

    def test_already_configured_counts_are_not_added_again(self):
        result = self.run_replay(Replay(configured=True))
        self.assertEqual(result.status, "completed", result.message)
        self.assertFalse(any(a.startswith("set_") for a in result.actions))

    def test_exhausted_tabs_are_skipped_without_paid_topups(self):
        replay = Replay(empty=True)
        result = self.run_replay(replay)
        self.assertEqual(result.status, "completed", result.message)
        self.assertEqual(replay.executions, [])
        self.assertFalse(any(a.startswith("set_") for a in result.actions))

    def test_unclaimable_arena_gift_toggle_does_not_repeat_an_exhausted_tab(self):
        replay = Replay(empty=True)
        # The real game's gift toggle stays ON even after all 30 duels,
        # while reward milestones that are not yet eligible remain unclaimed.
        replay.quick[1] = True
        result = self.run_replay(replay)
        self.assertEqual(result.status, "completed", result.message)
        self.assertNotIn("execute_tab_1", result.actions)

    def test_unchanged_counter_never_repeats_plus_or_executes_that_tab(self):
        result = self.run_replay(Replay(stall=True))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(sum(a.startswith("set_arena_") for a in result.actions), 1)
        self.assertNotIn("execute_tab_1", result.actions)

    def test_missing_result_never_reexecutes_or_advances(self):
        result = self.run_replay(Replay(missing_result=True))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.actions.count("execute_tab_0"), 1)
        self.assertNotIn("open_tab_1", result.actions)

    def test_partial_sweep_does_not_report_complete_or_start_next_tab(self):
        replay = Replay()
        press = replay.press

        def partial(action, now):
            press(action, now)
            if action == "close_assistant_result":
                replay.counts["dungeon_hell"] = 1

        replay.press = partial
        result = self.run_replay(replay)
        self.assertEqual(result.status, "blocked")
        self.assertIn("vẫn còn 1 lượt", result.message)
        self.assertEqual(result.actions.count("execute_tab_0"), 1)
        self.assertNotIn("open_tab_1", result.actions)

    def test_stop_after_execute_starts_no_new_tab(self):
        result = self.run_replay(Replay(), stop_on="execute_tab_")
        self.assertEqual(result.status, "cancelled")
        self.assertNotIn("open_tab_1", result.actions)

    def test_real_tabs_rows_and_result_without_dismiss_hint_at_several_sizes(self):
        detector = AssistantDetector()
        folder = Path(__file__).parent/"fixtures/assistant"
        cases = (("tab_0", 0, {"beast": 4}), ("tab_1", 1, {"arena": 20}),
                 ("tab_1_target", 1, {"arena": 30}), ("tab_2", 2, {"reset": 1, "hell": 4}),
                 ("tab_2_bottom", 2, {"elite": 3}), ("tab_3", 3, {"slash": 3}),
                 ("tab_4", 4, {"weapon": 3}),
                 ("hell_6", 2, {"reset": 2, "hell": 6}),
                 ("hell_6_after_restart", 2, {"reset": 2, "hell": 6}),
                 ("hell_7", 2, {"reset": 2, "hell": 7}),
                 ("hell_8", 2, {"reset": 2, "hell": 8}),
                 ("tab_0_after", 0, {"beast": 0}),
                 ("tab_0_middle", 0, {"demon": 0, "nightmare": 0}),
                 ("tab_0_bottom", 0, {"dungeon_hell": 0}),
                 ("resume_check", 1, {"arena": 0}))
        for name, tab, counts in cases:
            raw = cv2.imread(str(folder/f"{name}.png"))
            for width in (1920, 1280, 960):
                with self.subTest(name=name, width=width):
                    resized = cv2.resize(raw, (width, round(raw.shape[0]*width/raw.shape[1])), interpolation=cv2.INTER_AREA)
                    _, png = cv2.imencode(".png", resized)
                    frame = detector.decode(png.tobytes())
                    self.assertEqual(detector.page(frame), tab)
                    for row, expected in counts.items():
                        value = detector.row(frame, row)
                        self.assertIsNotNone(value, row)
                        self.assertEqual(value.count, expected)
        frame = detector.decode((folder/"result_no_hint.png").read_bytes())
        self.assertTrue(detector.result_visible(frame))
        self.assertIsNone(detector.page(frame))


if __name__ == "__main__":
    unittest.main()
