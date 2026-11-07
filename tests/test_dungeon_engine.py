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
        self.swipes = []

    def capture(self):
        self.current = next(self.screens, self.current)
        return cv2.imencode(".png", np.full((90, 160, 3), self.current, np.uint8))[1].tobytes()

    def tap(self, x, y, frame_size):
        self.actions.append(("tap", x, y))

    def swipe(self, *args):
        self.actions.append(("swipe",))
        self.swipes.append(args)


class Detector:
    results_ready = True
    controls_ready = True
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
        12: {"battle_screen", "battle_skip", "battle_auto_on"},
        13: {"event_intro", "intro_dismiss"},
        14: {"battle_screen", "battle_skip", "battle_auto_off"},
        15: {"battle_screen", "battle_skip"},
        16: {"battle_screen", "battle_auto_on"},
        17: {"victory", "next_stage", "battle_screen", "battle_auto_off", "battle_skip"},
        18: {"defeat", "battle_screen", "battle_auto_off", "battle_skip"},
        19: {"battle_screen", "battle_skip", "battle_auto_on", "battle_auto_off"},
        20: {"stage_screen", "next_chapter"},
        21: {"stage_screen", "next_chapter", "stage_frontier"},
        22: {"victory", "stage_screen", "next_chapter"},
        23: {"next_chapter"},
        24: {"stage_screen"},
        25: {"stage_screen", "stage_frontier"},
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

    def stage_identity(self, frame):
        return np.full((24, 256), 255, dtype=np.uint8)

    same_stage = staticmethod(dungeon.DungeonDetector.same_stage)
    viewport_motion = staticmethod(lambda before, after: 0.0)

    def map_identity(self, frame):
        mask = np.zeros((32, 256), np.uint8)
        mask[:, :128] = 255
        if int(frame[0, 0, 0]) in {20, 21, 25}:
            mask[:, 128:] = 255
        return mask


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
        result, device = self.run_engine([1, 2, 3, 4, 4, 5, 0, 6, 6, 6, 0, 5, 0, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 1))
        names = ["time_machine", "dungeon_entry", "chapter_frontier", "stage_frontier", "fight", "next_stage", "fight"]
        indexes = list(dungeon.DungeonDetector.REGIONS)
        expected_x = [round((12 + indexes.index(name) * 5) * 1920 / 160) for name in names]
        self.assertEqual([a[1] for a in device.actions], expected_x)

    def test_tenth_win_next_chapter_then_first_stage_of_new_map(self):
        for spam in (False, True):
            screens = [5]
            for _ in range(9):
                screens += [8, 8, 0, 4, 4, 5]
            screens += [8, 8, 0, 20, 20, 0, 4, 4, 4, 4, 5, 12, 12, 7, 7]
            # End immediately at the first loss to avoid spending a retry budget.
            if spam:
                screens += [0, 4, 4, 5, 7, 7]
            result, device = self.run_engine(screens, spam=spam, spam_limit=1)
            self.assertEqual(result.status, "spam_limit" if spam else "defeat")
            self.assertEqual((result.wins, result.retries, result.battle_skips), (10, int(spam), 1))
            clicks = [a[1] for a in device.actions]
            self.assertEqual(clicks.count(self.action_x("next_chapter")), 1)
            self.assertEqual(clicks.count(self.action_x("fight")), 11 + int(spam))
            self.assertFalse(any(a[0] == "swipe" for a in device.actions))

    def test_start_on_completed_map_goes_to_next_chapter_without_counting_old_wins(self):
        result, device = self.run_engine([20, 20, 4, 4, 4, 4, 5, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 0))
        self.assertEqual([a[1] for a in device.actions], [self.action_x(n) for n in
                         ("next_chapter", "stage_frontier", "fight")])

    def test_next_chapter_can_return_to_the_chapter_list(self):
        result, device = self.run_engine([20, 20, 3, 3, 4, 4, 5, 7, 7])
        self.assertEqual(result.status, "defeat")
        self.assertEqual([a[1] for a in device.actions], [self.action_x(n) for n in
                         ("next_chapter", "chapter_frontier", "stage_frontier", "fight")])

    def test_next_chapter_button_prioritized_and_never_reclicked_on_old_map(self):
        result, device = self.run_engine([21]*40)
        self.assertEqual(result.status, "timeout")
        self.assertEqual([a[1] for a in device.actions], [self.action_x("next_chapter")])

    def test_old_map_is_not_selected_when_button_disappears_before_new_title(self):
        result, device = self.run_engine([20, 20]+[25]*40)
        self.assertEqual(result.status, "timeout")
        self.assertEqual([a[1] for a in device.actions], [self.action_x("next_chapter")])

    def test_next_chapter_without_stage_context_is_never_clicked(self):
        result, device = self.run_engine([23]*40)
        self.assertEqual(result.status, "timeout")
        self.assertFalse(device.actions)

    def test_result_overlay_does_not_receive_a_background_next_chapter_click(self):
        result, device = self.run_engine([5, 22, 22])
        self.assertEqual((result.status, result.wins), ("unknown", 1))
        self.assertEqual([a[1] for a in device.actions], [self.action_x("fight")])

    def test_win_limit_stops_before_next_chapter(self):
        result, device = self.run_engine([5, 22, 22], max_wins=1)
        self.assertEqual((result.status, result.wins), ("limit", 1))
        self.assertEqual([a[1] for a in device.actions], [self.action_x("fight")])

    def test_spam_loss_never_changes_chapter(self):
        result, device = self.run_engine([5, 7, 7, 0]+[20]*40, spam=True)
        self.assertEqual((result.status, result.retries), ("retry_unverified", 0))
        self.assertNotIn(self.action_x("next_chapter"), [a[1] for a in device.actions if a[0] == "tap"])

    def test_real_chapter_button_detects_on_emulator_and_phone_without_dimmed_background(self):
        detector = dungeon.DungeonDetector()
        png = (Path(__file__).parent/"fixtures/dungeon/next_chapter.png").read_bytes()
        frame = detector.decode(png)
        self.assertIsNotNone(detector.find(frame, "next_chapter"))
        self.assertIsNotNone(detector.map_identity(frame))
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8), "next_chapter"))
        phone = np.zeros((597, 1280, 3), np.uint8)
        phone[:, -frame.shape[1]:] = frame
        self.assertIsNotNone(detector.find(phone, "next_chapter"))

    def test_first_stage_dark_stars_below_map_title_keep_a_safe_npc_anchor(self):
        detector = dungeon.DungeonDetector()
        frame = detector.decode((Path(__file__).parent/"fixtures/dungeon/first_stage_marker.png").read_bytes())
        self.assertIsNotNone(detector.find(frame, "stage_screen"))
        marker = detector.find(frame, "stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.height, 44)
        x, y = marker.center
        target_y = y + marker.height * (145/44)
        self.assertTrue(145 <= x <= 205)
        self.assertTrue(200 <= target_y <= 285)
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8), "stage_frontier"))

    def test_next_chapter_lettering_matches_over_bright_statue_background(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/next_chapter_bright_background.png").read_bytes())
        button=detector.find(frame,"next_chapter")
        self.assertIsNotNone(button)
        self.assertTrue(900 < button.center[0] < 960)
        self.assertTrue(360 < button.center[1] < 405)
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8),"next_chapter"))
        self.assertIsNone(detector.find(frame,"stage_frontier"))

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

    def test_spam_retries_exactly_the_configured_number_and_stops_on_loss(self):
        result, device = self.run_engine(
            [5, 7, 7, 0, 4, 4, 5, 7, 7, 0, 4, 4, 5, 7, 7], spam=True, spam_limit=2)
        self.assertEqual((result.status, result.retries, result.stage_retries), ("spam_limit", 2, 2))
        self.assertEqual([a[1] for a in device.actions], [self.action_x(n) for n in
            ("fight", "result_exit", "stage_frontier", "fight", "result_exit", "stage_frontier", "fight")])

    def test_spam_default_stops_after_100_retries_not_101(self):
        screens = [5, 7, 7] + [s for _ in range(100) for s in (0, 4, 4, 5, 7, 7)]
        result, device = self.run_engine(screens, spam=True)
        self.assertEqual((result.status, result.retries, result.stage_retries), ("spam_limit", 100, 100))
        fights = [a for a in device.actions if a[1] == self.action_x("fight")]
        self.assertEqual(len(fights), 101)  # Initial attempt plus 100 additional fights.

    def test_spam_win_continues_and_resets_budget_for_next_stage(self):
        result, device = self.run_engine(
            [5, 7, 7, 0, 4, 4, 5, 6, 6, 0, 0, 5, 7, 7, 0, 4, 4, 5, 7, 7],
            spam=True, spam_limit=1)
        self.assertEqual((result.status, result.wins, result.retries, result.stage_retries),
                         ("spam_limit", 1, 2, 1))

    def test_spam_does_not_recount_or_reclick_a_persistent_defeat(self):
        result, device = self.run_engine([5, 7, 7] + [7]*30, spam=True, spam_limit=2)
        self.assertEqual((result.status, result.retries), ("timeout", 0))
        self.assertEqual([a[1] for a in device.actions],
                         [self.action_x("fight"), self.action_x("result_exit")])

    def test_explicit_new_spam_turn_can_start_from_a_previous_defeat(self):
        result, device = self.run_engine([7, 7, 0, 4, 4, 5, 7, 7], spam=True, spam_limit=1)
        self.assertEqual((result.status, result.retries), ("spam_limit", 1))
        self.assertEqual([a[1] for a in device.actions], [self.action_x(n) for n in
                         ("result_exit", "stage_frontier", "fight")])

    def test_retry_checks_auto_and_skips_for_each_new_battle(self):
        result, device = self.run_engine([5, 12, 12, 7, 7, 0, 4, 4, 5, 14, 14, 12, 12, 7, 7],
                                         spam=True, spam_limit=1)
        self.assertEqual((result.status, result.retries, result.auto_activations, result.battle_skips),
                         ("spam_limit", 1, 1, 2))

    def test_retry_native_quick_combat_can_bypass_the_fight_dialog(self):
        result, device = self.run_engine([4, 4, 12, 12, 7, 7, 0, 4, 4, 12, 12, 12, 7, 7],
                                         spam=True, spam_limit=1)
        self.assertEqual((result.status, result.retries, result.battle_skips), ("spam_limit", 1, 2))
        self.assertEqual([a[1] for a in device.actions], [self.action_x(n) for n in
                         ("stage_frontier", "battle_skip", "result_exit", "stage_frontier", "battle_skip")])

    def test_retry_instant_result_after_selecting_frontier_counts_once(self):
        result, device = self.run_engine([4, 4, 7, 7, 0, 4, 4, 7, 7], spam=True, spam_limit=1)
        self.assertEqual((result.status, result.retries), ("spam_limit", 1))

    def test_retry_rejected_fight_is_not_counted_without_combat_or_result(self):
        result, device = self.run_engine([5, 7, 7, 0, 4, 4] + [5]*30, spam=True)
        self.assertEqual((result.status, result.retries), ("timeout", 0))
        self.assertEqual(len(device.actions), 4)

    def test_retry_changed_frontier_does_not_start_another_battle(self):
        detector = Detector()
        original_find = detector.find
        seen = [False]
        def shifted_find(frame, name, threshold=.87):
            match = original_find(frame, name, threshold)
            if int(frame[0, 0, 0]) == 7:
                seen[0] = True
            if match and name == "stage_frontier" and seen[0]:
                return Match(name, match.x+25, match.y, match.width, match.height, 1)
            return match
        detector.find = shifted_find
        result, device = self.run_engine([4, 4, 12, 12, 7, 7, 0, 4, 4], detector=detector, spam=True)
        self.assertEqual((result.status, result.retries), ("retry_unverified", 0))
        self.assertEqual(len(device.actions), 3)

    def test_retry_does_not_navigate_to_another_chapter_or_home(self):
        for screen in (2, 3, 12):
            result, device = self.run_engine([5, 7, 7, 0, screen], spam=True)
            self.assertEqual((result.status, result.retries), ("retry_unverified", 0))
            self.assertEqual(len(device.actions), 2)

    def test_retry_missing_frontier_sweeps_both_edges_and_never_switches_map(self):
        result, device = self.run_engine([5, 6, 6, 0, 0, 5, 7, 7, 0, 9], spam=True)
        self.assertEqual((result.status, result.wins, result.retries), ("retry_unverified", 1, 0))
        self.assertEqual(len(device.swipes), 9)
        self.assertTrue(all(s[0] > s[2] for s in device.swipes[:3]))
        self.assertTrue(all(s[0] < s[2] for s in device.swipes[3:6]))
        self.assertTrue(all(s[0] > s[2] for s in device.swipes[6:]))
        self.assertNotIn(self.action_x("map_back"), [a[1] for a in device.actions if a[0] == "tap"])

    def test_retry_missing_title_or_changed_stage_stops_before_fight(self):
        for changed in (None, np.zeros((24, 256), dtype=np.uint8)):
            detector = Detector()
            identities = iter((np.full((24, 256), 255, dtype=np.uint8), changed))
            detector.stage_identity = lambda frame: next(identities)
            result, device = self.run_engine([5, 7, 7, 0, 4, 4, 5], detector=detector, spam=True)
            self.assertEqual((result.status, result.retries), ("retry_unverified", 0))
            self.assertEqual(len(device.actions), 3)

    def test_loss_hint_can_appear_late_without_using_a_retry(self):
        result, device = self.run_engine([5, 18, 18, 18, 7, 0, 4, 4, 5, 7, 7], spam=True, spam_limit=1)
        self.assertEqual((result.status, result.retries), ("spam_limit", 1))
        self.assertEqual(len(device.actions), 4)

    def test_retry_can_use_a_dialog_after_result_auto_dismissal(self):
        result, device = self.run_engine([5, 18, 18, 0, 5, 7, 7], spam=True, spam_limit=1)
        self.assertEqual((result.status, result.retries), ("spam_limit", 1))
        self.assertEqual(len(device.actions), 2)

    def test_spam_invalid_options_produce_no_game_input(self):
        for options in ({"spam": "yes"}, *({"spam_limit": v} for v in (0, -1, True, 1.5, "100"))):
            result, device = self.run_engine([5], **options)
            self.assertEqual(result.status, "error")
            self.assertFalse(device.actions)

    def test_stop_during_retry_navigation_prevents_the_next_fight(self):
        stop, clock, device = threading.Event(), Clock(), Device([5, 7, 7, 0, 4, 4, 5])
        dialogs = [0]
        def preview(png):
            if device.current == 5:
                dialogs[0] += 1
                if dialogs[0] == 2:
                    stop.set()
        engine = dungeon.DungeonEngine(device, detector=Detector(), stop=stop,
            clock=clock.now, sleeper=clock.sleep, preview=preview)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run(spam=True)
        self.assertEqual((result.status, result.retries), ("cancelled", 0))
        self.assertEqual(len(device.actions), 3)

    def test_retry_win_respects_the_normal_win_limit(self):
        result, device = self.run_engine([5, 7, 7, 0, 4, 4, 5, 6, 6],
                                         spam=True, spam_limit=1, max_wins=1)
        self.assertEqual((result.status, result.wins, result.retries, result.stage_retries),
                         ("limit", 1, 1, 0))
        self.assertNotIn(self.action_x("next_stage"), [a[1] for a in device.actions])

    def test_title_identity_rejects_a_different_stage_number(self):
        detector = dungeon.DungeonDetector()
        def title(number):
            frame = np.zeros((597, 1061, 3), np.uint8)
            cv2.putText(frame, f"Ma Quan {number}", (410, 162), cv2.FONT_HERSHEY_SIMPLEX,
                        .8, (0, 220, 255), 2, cv2.LINE_AA)
            return frame
        first, second = detector.stage_identity(title(1)), detector.stage_identity(title(7))
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertFalse(detector.same_stage(first, second))
        animated = title(1)
        animated[250:400, 200:400] = (100, 255, 255)
        self.assertTrue(detector.same_stage(first, detector.stage_identity(animated)))
        self.assertIsNone(detector.stage_identity(np.zeros_like(animated)))

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
        result, device = self.run_engine([5, 11, 11, 11, 8, 0, 4, 4, 5, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 1))
        self.assertEqual(len(device.actions), 4)

    def test_game_can_return_to_map_before_result_hint_is_observed(self):
        result, device = self.run_engine([5, 11, 11, 0, 4, 4, 5, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 1))
        self.assertEqual(len(device.actions), 3)

    def test_combat_can_start_directly_after_selecting_stage(self):
        result, device = self.run_engine([4, 4, 12, 12, 6, 6], max_wins=1)
        self.assertEqual((result.status, result.wins), ("limit", 1))
        self.assertEqual(len(device.actions), 2)  # Select the stage, then skip animation.

    def test_game_skip_button_is_pressed_only_once_per_battle(self):
        result, device = self.run_engine([5, 12, 12, 12, 7, 7])
        self.assertEqual((result.status, result.wins), ("defeat", 0))
        self.assertEqual(len(device.actions), 2)

    def action_x(self, name):
        return round((12 + list(dungeon.DungeonDetector.REGIONS).index(name)*5)*1920/160)

    def test_enable_auto_and_confirm_before_skip(self):
        result, device = self.run_engine([5,14,14,14,12,12,7,7])
        self.assertEqual((result.status,result.auto_activations,result.battle_skips),("defeat",1,1))
        self.assertEqual([a[1] for a in device.actions],
                         [self.action_x(n) for n in ("fight","battle_auto_off","battle_skip")])

    def test_auto_already_on_is_never_toggled(self):
        result, device = self.run_engine([5,12,12,12,12,7,7])
        self.assertEqual((result.auto_activations,result.battle_skips),(0,1))
        self.assertEqual([a[1] for a in device.actions],[self.action_x("fight"),self.action_x("battle_skip")])

    def test_stale_off_frames_do_not_repeat_toggle_or_skip_before_confirmation(self):
        result, device = self.run_engine([5,14,14]+[14]*4+[12,12,7,7])
        self.assertEqual((result.status,result.auto_activations,result.battle_skips),("defeat",1,1))
        self.assertEqual(len(device.actions),3)

    def test_unconfirmed_toggle_stops_without_skip_or_repeated_input(self):
        result, device = self.run_engine([5]+[14]*30)
        self.assertEqual((result.status,result.auto_activations,result.battle_skips),("auto_unverified",1,0))
        self.assertEqual(len(device.actions),2)

    def test_unknown_or_ambiguous_auto_never_guesses_or_skips(self):
        for screen in (15,19):
            result,device=self.run_engine([5]+[screen]*30)
            self.assertEqual((result.status,result.auto_activations,result.battle_skips),("auto_unverified",0,0))
            self.assertEqual(len(device.actions),1)

    def test_single_off_flash_does_not_toggle_auto(self):
        result,device=self.run_engine([5,14,12,12,7,7])
        self.assertEqual((result.auto_activations,result.battle_skips),(0,1))
        self.assertEqual(len(device.actions),2)

    def test_skip_can_appear_late_after_auto_confirmation(self):
        result,device=self.run_engine([5,16,16,16,12,12,7,7])
        self.assertEqual((result.auto_activations,result.battle_skips),(0,1))
        self.assertEqual(len(device.actions),2)

    def test_auto_is_checked_again_and_skip_resets_for_next_battle(self):
        result,device=self.run_engine([5,12,12,6,6,0,0,14,14,12,12,7,7])
        self.assertEqual((result.status,result.wins,result.auto_activations,result.battle_skips),("defeat",1,1,2))
        self.assertEqual([a[1] for a in device.actions],[self.action_x(n) for n in
                         ("fight","battle_skip","next_stage","battle_auto_off","battle_skip")])

    def test_auto_can_be_reenabled_if_disabled_during_same_battle_without_second_skip(self):
        result,device=self.run_engine([5,12,12,14,14,12,12,7,7])
        self.assertEqual((result.auto_activations,result.battle_skips),(1,1))
        self.assertEqual(len(device.actions),3)

    def test_result_overlay_controls_never_receive_auto_or_skip_input(self):
        for screen,outcome in ((17,"limit"),(18,"defeat")):
            result,device=self.run_engine([5,screen,screen],max_wins=1)
            self.assertEqual((result.status,result.auto_activations,result.battle_skips),(outcome,0,0))
            self.assertEqual(len(device.actions),1)

    def test_missing_control_templates_prevents_fight(self):
        detector=Detector();detector.controls_ready=False
        result,device=self.run_engine([5],detector=detector)
        self.assertEqual(result.status,"needs_samples")
        self.assertFalse(device.actions)

    def test_auto_or_skip_without_battle_context_is_never_clicked(self):
        detector=Detector()
        detector.SCREENS={20:{"battle_auto_off","battle_skip"}}
        result,device=self.run_engine([20]*30,detector=detector)
        self.assertEqual(result.status,"timeout")
        self.assertFalse(device.actions)

    def test_real_button_colors_distinguish_auto_on_and_off(self):
        detector=dungeon.DungeonDetector()
        self.assertTrue(detector.controls_ready)
        for state,opposite in (("on","off"),("off","on")):
            png=(Path(__file__).parent/"fixtures/dungeon"/("auto_"+state+".png")).read_bytes()
            frame=detector.decode(png)
            self.assertTrue(detector.find(frame,"battle_auto_"+state))
            self.assertIsNone(detector.find(frame,"battle_auto_"+opposite))
            self.assertTrue(detector.find(frame,"battle_skip"))
            self.assertTrue(detector.find(frame,"battle_screen"))

    def test_dimmed_control_templates_do_not_justify_a_toggle(self):
        detector=dungeon.DungeonDetector()
        png=(Path(__file__).parent/"fixtures/dungeon/auto_off.png").read_bytes()
        frame=(detector.decode(png)*.4).astype(np.uint8)
        self.assertIsNone(detector.find(frame,"battle_auto_off"))

    def test_event_intro_is_dismissed_before_opening_event_dungeon(self):
        result, device = self.run_engine([1, 13, 2, 3, 4, 4, 5, 7, 7])
        self.assertEqual(result.status, "defeat")
        self.assertEqual(len(device.actions), 6)

    def test_return_to_stage_map_after_win_starts_next_battle(self):
        result, device = self.run_engine([5, 8, 8, 0, 4, 4, 5, 7, 7])
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
        self.assertEqual(device.actions, [("swipe",)] * 9)
        self.assertTrue(all(s[0] > s[2] for s in device.swipes[:3]))
        self.assertTrue(all(s[0] < s[2] for s in device.swipes[3:6]))
        self.assertTrue(all(s[0] > s[2] for s in device.swipes[6:]))

    def test_sweep_keeps_moving_past_old_three_swipe_limit_until_frontier_is_visible(self):
        class LongMapDetector(Detector):
            viewport_motion = staticmethod(lambda before, after: -120.0)
        class LongMapDevice(Device):
            def swipe(self, *args):
                super().swipe(*args)
                if len(self.swipes) == 11:
                    self.screens = iter([4, 4, 4, 4, 5, 7, 7])
        clock, device = Clock(), LongMapDevice([9])
        engine = dungeon.DungeonEngine(device, detector=LongMapDetector(), clock=clock.now,
            sleeper=clock.sleep, navigation_timeout=8)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run()
        self.assertEqual(result.status, "defeat")
        self.assertEqual(len(device.swipes), 11)
        self.assertTrue(all(s[0] > s[2] for s in device.swipes))

    def test_unknown_motion_never_counts_as_a_verified_map_edge(self):
        class NoMotionEvidence(Detector):
            viewport_motion = staticmethod(lambda before, after: None)
        with patch.object(dungeon, "MAX_SCAN_PANS", 8):
            result, device = self.run_engine([9], detector=NoMotionEvidence())
        self.assertEqual(result.status, "scan_unverified")
        self.assertEqual(len(device.swipes), 8)
        self.assertTrue(all(s[0] > s[2] for s in device.swipes))

    def test_sweep_confirms_each_edge_on_three_different_drag_lanes(self):
        sweep = dungeon.MapSweep()
        frame = np.zeros((90,160,3),np.uint8)
        for _ in range(12):
            sweep.sent(frame);sweep.observe(frame, lambda a,b:-90.0)
            self.assertFalse(sweep.complete)
            self.assertFalse(sweep.edges)
        used=[]
        for _ in range(3):
            used.append(sweep.lane);sweep.sent(frame);sweep.observe(frame,lambda a,b:0.0)
        self.assertEqual(used,list(dungeon.PAN_LANES))
        self.assertEqual((sweep.direction,sweep.edges),("earlier",{"later"}))
        for _ in range(10):
            sweep.sent(frame);sweep.observe(frame,lambda a,b:90.0)
            self.assertFalse(sweep.complete)
        for _ in range(3):
            sweep.sent(frame);sweep.observe(frame,lambda a,b:0.0)
        self.assertFalse(sweep.complete)
        self.assertEqual(sweep.direction,"later")
        self.assertTrue(sweep.final_return)
        for _ in range(3):
            sweep.sent(frame);sweep.observe(frame,lambda a,b:-90.0)
        for _ in range(3):
            sweep.sent(frame);sweep.observe(frame,lambda a,b:0.0)
        self.assertTrue(sweep.complete)

    def test_viewport_motion_measures_map_translation_and_rejects_featureless_frames(self):
        detector = dungeon.DungeonDetector()
        image = np.random.default_rng(11).integers(0,256,(597,1061,3),np.uint8)
        moved = cv2.warpAffine(image,np.float32([[1,0,-140],[0,1,0]]),(1061,597))
        self.assertAlmostEqual(detector.viewport_motion(image,moved),-140,delta=3)
        self.assertAlmostEqual(detector.viewport_motion(image,image.copy()),0,delta=1)
        blank = np.zeros_like(image)
        self.assertIsNone(detector.viewport_motion(blank,blank))

    def test_dark_stars_recognize_final_boss_against_different_scenery(self):
        detector = dungeon.DungeonDetector()
        frame = detector.decode((Path(__file__).parent/"fixtures/dungeon/final_boss_new_background.png").read_bytes())
        marker = detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertGreaterEqual(marker.score,.94)
        self.assertTrue(790 < marker.center[0] < 860)
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8),"stage_frontier"))

    def test_unplayed_stars_still_find_npc_when_swords_are_outside_screen(self):
        detector = dungeon.DungeonDetector()
        frame = detector.decode((Path(__file__).parent/"fixtures/dungeon/mostly_clipped_swords.png").read_bytes())
        marker = detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_unplayed_stars")
        x,y=marker.center
        self.assertTrue(790 < x < 860)
        self.assertTrue(95 < y+marker.height*(145/44) < 155)
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8),"stage_frontier"))
        ambiguous=frame.copy()
        ambiguous[100:162,350:429]=frame[3:65,783:862]
        self.assertIsNone(detector.find(ambiguous,"stage_frontier"))
        completed=frame.copy()
        crop=completed[3:31,783:809]
        dark=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)[:,:,2] < 100
        crop[dark]=(0,220,255)
        self.assertIsNone(detector.find(completed,"stage_frontier"))

    def test_empty_stars_select_the_same_npc_after_swords_are_erased(self):
        detector=dungeon.DungeonDetector()
        folder=Path(__file__).parent/"fixtures/dungeon"
        for name,box in (("first_stage_marker",(128,40,215,108)),
                         ("final_boss_new_background",(783,130,865,199)),
                         ("stage10_top_clipped",(730,0,811,26))):
            with self.subTest(screen=name):
                frame=detector.decode((folder/(name+".png")).read_bytes())
                original=detector.find(frame,"stage_frontier")
                self.assertIsNotNone(original)
                x1,y1,x2,y2=box
                frame[y1:y2,x1:x2]=0
                marker=detector.find(frame,"stage_frontier")
                self.assertIsNotNone(marker)
                self.assertEqual(marker.name,"stage_unplayed_stars")
                self.assertLessEqual(abs(marker.center[0]-original.center[0]),3)
                self.assertLessEqual(abs(marker.center[1]-original.center[1]),3)

    def test_hoang_cai_three_empty_stars_match_without_green_background_template(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/hoang_cai_green_stars.png").read_bytes())
        marker=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_unplayed_stars")
        self.assertTrue(725 < marker.center[0] < 765)
        self.assertTrue(235 < marker.center[1]+marker.height*(145/44) < 275)
        # The stage's sword animation can be absent without moving the target.
        frame[70:134,700:790]=0
        without_swords=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(without_swords)
        self.assertLessEqual(abs(marker.center[0]-without_swords.center[0]),3)
        self.assertLessEqual(abs(marker.center[1]-without_swords.center[1]),3)
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8),"stage_frontier"))

    def test_geometry_still_rejects_a_gold_star_and_multiple_empty_rows(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/hoang_cai_green_stars.png").read_bytes())
        completed=frame.copy()
        first=completed[134:162,705:732]
        first[cv2.cvtColor(first,cv2.COLOR_BGR2GRAY)<55]=(0,220,255)
        self.assertIsNone(detector._unplayed_frontier(completed))
        frame[200:260,350:429]=frame[134:194,705:784]
        self.assertIsNone(detector._unplayed_frontier(frame))

    def test_geometry_handles_brown_background_on_next_hoang_cai_stage(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/hoang_cai_4_stars.png").read_bytes())
        marker=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_unplayed_stars")
        self.assertTrue(800 < marker.center[0] < 845)
        self.assertTrue(200 < marker.center[1]+marker.height*(145/44) < 245)

    def test_textured_character_colors_cannot_replace_empty_star_fill(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/hoang_cai_green_stars.png").read_bytes())
        texture=np.indices((9,10)).sum(axis=0)%2*100
        for x in (713,739,765):
            frame[144:153,x:x+10]=np.repeat(texture[:,:,None],3,axis=2)
        self.assertIsNone(detector._unplayed_frontier(frame))

    def test_translucent_star_over_a_statue_is_not_rejected_as_character_art(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/hoang_cai_6_stars.png").read_bytes())
        marker=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_unplayed_stars")
        self.assertTrue(800 < marker.center[0] < 845)
        self.assertTrue(345 < marker.center[1]+marker.height*(145/44) < 385)

    def test_dark_fence_above_stars_does_not_invalidate_empty_fill(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/chu_thai_mixed_background.png").read_bytes())
        marker=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_unplayed_stars")
        self.assertTrue(800 < marker.center[0] < 845)
        self.assertTrue(310 < marker.center[1]+marker.height*(145/44) < 350)

    def test_glowing_swords_recover_stage_when_empty_stars_are_unclear(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/revealed_glow.png").read_bytes())
        self.assertIsNotNone(detector.find(frame,"stage_screen"))
        self.assertIsNone(detector._unplayed_frontier(frame))
        marker=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_swords")
        self.assertTrue(790 < marker.center[0] < 860)
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8),"stage_frontier"))

    def test_star_fallback_waits_for_second_observation_before_input(self):
        class StarsDetector(Detector):
            SCREENS={**Detector.SCREENS,29:{"stage_screen","stage_frontier"}}
            def find(self,frame,name,threshold=.87):
                match=super().find(frame,name,threshold)
                if match and name=="stage_frontier" and int(frame[0,0,0])==29:
                    return Match("stage_unplayed_stars",match.x,match.y,match.width,match.height,match.score)
                return match
        result,device=self.run_engine([29]+[0]*30,detector=StarsDetector())
        self.assertEqual(result.status,"timeout")
        self.assertFalse(device.actions)
        result,device=self.run_engine([29,29,5,7,7],detector=StarsDetector())
        self.assertEqual(result.status,"defeat")
        self.assertEqual(len(device.actions),2)

    def test_sword_fallback_requires_two_frames_and_also_works_for_spam(self):
        class SwordDetector(Detector):
            SCREENS={**Detector.SCREENS,29:{"stage_screen","stage_frontier"}}
            def find(self,frame,name,threshold=.87):
                marker=super().find(frame,name,threshold)
                if marker and name=="stage_frontier":
                    return Match("stage_swords",marker.x,marker.y,marker.width,marker.height,.99)
                return marker
        result,device=self.run_engine([29]+[0]*30,detector=SwordDetector())
        self.assertEqual(result.status,"timeout")
        self.assertFalse(device.actions)
        result,device=self.run_engine([29,29,5,7,7,0,29,29,5,7,7],
            detector=SwordDetector(),spam=True,spam_limit=1)
        self.assertEqual((result.status,result.retries),("spam_limit",1))
        self.assertEqual(len(device.actions),5)

    def test_disagreeing_stars_and_swords_wait_for_a_clear_target(self):
        detector=dungeon.DungeonDetector()
        frame=np.zeros((597,1061,3),np.uint8)
        screen=Match("stage_screen",980,530,50,50,1)
        stars=Match("stage_unplayed_stars",150,100,79,44,.99)
        swords=Match("stage_swords",650,100,58,44,.99)
        with patch.object(detector,"_find_template",return_value=screen), \
             patch.object(detector,"_unplayed_frontier",return_value=stars), \
             patch.object(detector,"_sword_frontier",return_value=swords):
            self.assertIsNone(detector.find(frame,"stage_frontier"))
        swords=Match("stage_swords",160,105,58,44,.99)
        with patch.object(detector,"_find_template",return_value=screen), \
             patch.object(detector,"_unplayed_frontier",return_value=stars), \
             patch.object(detector,"_sword_frontier",return_value=swords):
            self.assertEqual(detector.find(frame,"stage_frontier"),stars)

    def test_empty_stars_remain_detectable_when_fire_brightens_their_fill(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/empty_stars_fire_glow.png").read_bytes())
        marker=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_unplayed_stars")
        self.assertGreater(marker.score,.95)
        self.assertTrue(790 < marker.center[0] < 860)

    def test_top_clipped_empty_stars_find_final_boss_without_swords(self):
        detector=dungeon.DungeonDetector()
        frame=detector.decode((Path(__file__).parent/"fixtures/dungeon/top_clipped_empty_stars.png").read_bytes())
        marker=detector.find(frame,"stage_frontier")
        self.assertIsNotNone(marker)
        self.assertEqual(marker.name,"stage_unplayed_stars")
        self.assertTrue(710 < marker.center[0] < 760)
        self.assertTrue(90 < marker.center[1]+marker.height*(145/44) < 130)
        # A row with one earned star must never be treated as the frontier.
        completed=frame.copy()
        crop=completed[:16,696:722]
        dark=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)[:,:,2] < 100
        crop[dark]=(0,220,255)
        self.assertIsNone(detector._unplayed_frontier(completed))

    def test_left_pan_reveals_frontier_and_requires_two_fresh_observations(self):
        class RevealDevice(Device):
            def swipe(self, *args):
                super().swipe(*args)
                self.screens = iter([4, 4, 4, 4, 5, 12, 12, 7, 7])
        clock, device = Clock(), RevealDevice([9])
        engine = dungeon.DungeonEngine(device, detector=Detector(), clock=clock.now,
            sleeper=clock.sleep, navigation_timeout=8, battle_timeout=12)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run()
        self.assertEqual((result.status, result.battle_skips), ("defeat", 1))
        self.assertEqual(len(device.swipes), 1)
        self.assertGreater(device.swipes[0][0], device.swipes[0][2])
        self.assertEqual(device.actions[0], ("swipe",))
        self.assertEqual([a[1] for a in device.actions if a[0] == "tap"],
                         [self.action_x(n) for n in ("stage_frontier", "fight", "battle_skip")])

    def test_spam_pan_accepts_relocated_frontier_in_same_map_only(self):
        class ShiftedDetector(Detector):
            SCREENS = {**Detector.SCREENS, 28: {"stage_screen", "stage_frontier"}}
            def find(self, frame, name, threshold=.87):
                match = super().find(frame, name, threshold)
                if match and name == "stage_frontier" and int(frame[0,0,0]) == 28:
                    return Match(name, match.x+25, match.y, match.width, match.height, match.score)
                return match
        for changed_map in (False, True):
            class RevealDevice(Device):
                def swipe(self, *args):
                    super().swipe(*args)
                    self.screens = iter([25] if changed_map else [28, 28, 5, 12, 12, 7, 7])
            clock, device = Clock(), RevealDevice([4, 4, 5, 7, 7, 0, 9])
            engine = dungeon.DungeonEngine(device, detector=ShiftedDetector(), clock=clock.now,
                sleeper=clock.sleep, navigation_timeout=8, battle_timeout=12)
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
                with patch.object(dungeon, "ROOT", Path(folder)):
                    result = engine.run(spam=True, spam_limit=1)
            self.assertEqual(len(device.swipes), 1)
            self.assertEqual((result.status, result.retries),
                             ("retry_unverified", 0) if changed_map else ("spam_limit", 1))
            taps = [a[1] for a in device.actions if a[0] == "tap"]
            self.assertEqual(taps.count(self.action_x("fight")), 1 if changed_map else 2)

    def test_one_frame_marker_after_pan_does_not_trigger_a_stage_click(self):
        class FlashDevice(Device):
            def swipe(self, *args):
                super().swipe(*args)
                self.screens = iter([4, 0]*30)
        clock, device = Clock(), FlashDevice([9])
        engine = dungeon.DungeonEngine(device, detector=Detector(), clock=clock.now,
            sleeper=clock.sleep, navigation_timeout=8)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run()
        self.assertEqual(result.status, "timeout")
        self.assertEqual(device.actions, [("swipe",)])

    def test_stop_in_pan_progress_callback_prevents_swipe(self):
        stop, clock, device = threading.Event(), Clock(), Device([9])
        def progress(message):
            if "kéo map sang trái" in message:
                stop.set()
        engine = dungeon.DungeonEngine(device, detector=Detector(), stop=stop,
            clock=clock.now, sleeper=clock.sleep, progress=progress)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run()
        self.assertEqual(result.status, "cancelled")
        self.assertFalse(device.actions)

    def test_real_occlusion_left_pan_and_both_animation_phases(self):
        detector = dungeon.DungeonDetector()
        folder = Path(__file__).parent/"fixtures/dungeon"
        before = detector.decode((folder/"occluded_before_pan.png").read_bytes())
        self.assertIsNotNone(detector.find(before, "stage_screen"))
        self.assertIsNone(detector.find(before, "stage_frontier"))
        identities = [detector.map_identity(before)]
        markers = []
        for name in ("revealed_cross", "revealed_split"):
            frame = detector.decode((folder/f"{name}.png").read_bytes())
            marker = detector.find(frame, "stage_frontier")
            self.assertIsNotNone(marker)
            self.assertEqual(marker.height, 44)
            self.assertIsNone(detector.find((frame*.4).astype(np.uint8), "stage_frontier"))
            markers.append(marker)
            identities.append(detector.map_identity(frame))
        self.assertLessEqual(abs(markers[0].center[0]-markers[1].center[0]), 2)
        self.assertLessEqual(abs(markers[0].center[1]-markers[1].center[1]), 8)
        self.assertTrue(all(i is not None for i in identities))
        self.assertTrue(all(detector.same_stage(identities[0], i) for i in identities[1:]))

    def test_missing_marker_after_win_never_leaves_unfinished_map(self):
        result, device = self.run_engine([5, 8, 8, 0]+[9]*70)
        self.assertEqual((result.status, result.wins), ("no_frontier", 1))
        taps = [a[1] for a in device.actions if a[0] == "tap"]
        self.assertEqual(taps, [self.action_x("fight"), self.action_x("result_exit")])
        self.assertEqual(len(device.swipes), 9)

    def test_reverse_scan_can_recover_a_marker_missed_in_the_other_direction(self):
        class ReversedDevice(Device):
            def swipe(self, *args):
                super().swipe(*args)
                if args[0] < args[2]:
                    self.screens = iter([4, 4, 4, 4, 5, 7, 7])
        clock, device = Clock(), ReversedDevice([9])
        engine = dungeon.DungeonEngine(device, detector=Detector(), clock=clock.now,
            sleeper=clock.sleep, navigation_timeout=8, battle_timeout=12)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with patch.object(dungeon, "ROOT", Path(folder)):
                result = engine.run()
                snapshots = list((Path(folder)/"runtime/dungeon_scan").glob("*.png"))
        self.assertEqual(result.status, "defeat")
        self.assertEqual(len(device.swipes), 4)
        self.assertEqual(len(snapshots), 4)

    def test_recovered_clipped_marker_requires_two_consistent_observations(self):
        class ClippedDetector(Detector):
            SCREENS = {**Detector.SCREENS, 26: {"stage_screen", "stage_frontier"},
                       27: {"stage_screen", "stage_frontier"}}
            def find(self, frame, name, threshold=.87):
                value = int(frame[0, 0, 0])
                if name == "stage_frontier" and value in (26, 27):
                    return Match(name, 80 if value == 26 else 30, -4, 8, 12, .98)
                return super().find(frame, name, threshold)
        result, device = self.run_engine([26, 26, 5, 7, 7], detector=ClippedDetector())
        self.assertEqual(result.status, "defeat")
        self.assertEqual(len(device.actions), 2)
        result, device = self.run_engine([26, 26, 5, 7, 7, 0, 26, 26, 5, 7, 7],
                                         detector=ClippedDetector(), spam=True, spam_limit=1)
        self.assertEqual((result.status, result.retries), ("spam_limit", 1))
        self.assertEqual(len(device.actions), 5)
        for frames in ([26]+[0]*30, [26, 0, 26]+[0]*30, [26, 27]*30):
            result, device = self.run_engine(frames, detector=ClippedDetector())
            self.assertEqual(result.status, "timeout")
            self.assertFalse(device.actions)

    def test_real_stage10_dark_stars_restore_correct_npc_target(self):
        detector = dungeon.DungeonDetector()
        frame = detector.decode((Path(__file__).parent/"fixtures/dungeon/stage10_top_clipped.png").read_bytes())
        self.assertIsNotNone(detector.find(frame, "stage_screen"))
        marker = detector.find(frame, "stage_frontier")
        self.assertIsNotNone(marker)
        self.assertLess(marker.y, 0)
        self.assertGreater(marker.score, .94)
        x, y = marker.center
        self.assertTrue(735 < x < 805)
        self.assertTrue(120 < y+marker.height*(145/44) < 200)
        self.assertIsNone(detector.find((frame*.4).astype(np.uint8), "stage_frontier"))

    def test_partial_marker_noise_is_not_a_frontier(self):
        detector = dungeon.DungeonDetector()
        frame = detector.decode((Path(__file__).parent/"fixtures/dungeon/stage10_top_clipped.png").read_bytes())
        frame[:65, 700:840] = 0
        self.assertIsNone(detector.find(frame, "stage_frontier"))

    def test_swords_can_find_stage_when_all_stars_are_unreadable(self):
        detector=dungeon.DungeonDetector()
        base=detector.decode((Path(__file__).parent/"fixtures/dungeon/final_boss_new_background.png").read_bytes())
        template=cv2.imdecode(np.frombuffer((dungeon.ROOT/"assets/dungeon/stage_frontier.png").read_bytes(),np.uint8),0)
        th,tw=template.shape
        for cut in (0,10,18,24):
            frame=np.zeros_like(base)
            frame[520:,950:]=base[520:,950:]  # Map context, but no empty stars.
            frame[:th-cut,500:500+tw]=cv2.cvtColor(template[cut:],cv2.COLOR_GRAY2BGR)
            self.assertIsNotNone(detector.find(frame,"stage_screen"))
            marker=detector.find(frame,"stage_frontier")
            self.assertIsNotNone(marker)
            self.assertEqual(marker.name,"stage_swords")
            self.assertLessEqual(abs(marker.center[1]-(th/2-cut)),2)
            self.assertIsNone(detector.find((frame*.4).astype(np.uint8),"stage_frontier"))

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

    def test_sword_templates_load_but_never_select_without_map_context(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path=Path(folder)
            template=np.random.default_rng(4).integers(0,255,(63,63),dtype=np.uint8)
            for name in ("stage_frontier", "stage_frontier__example", "stage_frontier_tip"):
                (path/(name+".png")).write_bytes(cv2.imencode(".png",template)[1].tobytes())
            detector=dungeon.DungeonDetector(path)
            self.assertIn("stage_frontier",detector.templates)
            self.assertIn("stage_frontier_tip",detector.templates)
            self.assertEqual(len(detector.scaled["stage_frontier"]),14)
            frame=np.zeros((597,1061,3),np.uint8)
            frame[120:183,300:363]=cv2.cvtColor(template,cv2.COLOR_GRAY2BGR)
            self.assertIsNone(detector.find(frame,"stage_frontier"))



if __name__ == "__main__":
    unittest.main()
