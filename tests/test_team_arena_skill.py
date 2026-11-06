import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from login_engine import Match
from team_arena_skill import TeamArenaDetector, TeamArenaSkill, VIETNAM, bonus_hours


class Screen:
    def __init__(self, names=(), remaining=None, purchase=None, ready=0, receipt=None, wait=False):
        self.names = set(names)
        self.remaining = remaining
        self.purchase_data = purchase
        self.ready = ready
        self.receipt = receipt
        self.wait = wait
        self.observations = 0


def lobby(remaining):
    return Screen(("title", "create", "auto", "buy_plus"), remaining)


def party(remaining, ready=4):
    return Screen(("title", "leave", "invite", "leader", "fight"), remaining, ready=ready)


def purchase(quantity, cost):
    return Screen(("purchase_prompt", "purchase_ok", "purchase_cancel"), purchase=(4, quantity, cost, (1, 1), (2, 2)))


class ArenaReplay:
    ready = True

    def __init__(self, screens):
        self.screens = screens
        self.index = 0
        _, png = cv2.imencode(".png", np.zeros((597, 1061, 3), np.uint8))
        self.png = png.tobytes()

    @property
    def current(self):
        return self.screens[self.index]

    def capture(self):
        if self.current.wait:
            self.current.observations += 1
            if self.current.observations >= 4:
                self.advance()
        return self.png

    def advance(self):
        self.index = min(self.index+1, len(self.screens)-1)

    @staticmethod
    def decode(png):
        return cv2.imdecode(np.frombuffer(png, np.uint8), 1)

    def find(self, frame, name, threshold=.9):
        return Match(name, 10, 10, 20, 20, 1.) if name in self.current.names else None

    def attempts(self, frame):
        return self.current.remaining

    def purchase(self, frame):
        return self.current.purchase_data

    def ready_count(self, frame):
        return self.current.ready

    def result_page(self, frame):
        if "summary" in self.current.names:
            return "summary"
        if "rewards" in self.current.names:
            return "rewards"
        return None

    def reward_attempts(self, frame):
        return self.current.receipt


class TeamArenaSkillTests(unittest.TestCase):
    def run_replay(self, screens, *, hour=18, freeze_buy=False, stop_after=None):
        replay = ArenaReplay(screens)
        now = [0.]
        stop = threading.Event()

        def sleep(seconds):
            now[0] += seconds

        with tempfile.TemporaryDirectory() as folder:
            skill = TeamArenaSkill(replay, detector=replay, stop=stop, clock=lambda: now[0],
                                   sleeper=sleep, now=lambda: datetime(2026, 11, 5, hour, tzinfo=VIETNAM),
                                   evidence_root=Path(folder))

            def tap(frame, point, action):
                skill._check()
                skill.actions.append(action)
                if not (freeze_buy and action == "buy_attempts"):
                    replay.advance()
                if action == stop_after:
                    stop.set()

            skill._tap_point = tap
            return skill.run_arena()

    def test_buys_four_once_then_waits_for_seven_matches(self):
        screens = [lobby(3), purchase(1, 100), purchase(2, 300),
                   purchase(3, 500), purchase(4, 800), lobby(7), party(7)]
        for remaining in range(7, 0, -1):
            screens.extend([
                Screen(("matching", "matching_cancel"), remaining, wait=True),
                Screen(wait=True), Screen(("summary",)),
                Screen(("rewards",), receipt=remaining-1), party(remaining-1),
            ])
        result = self.run_replay(screens)
        self.assertEqual(result.status, "completed", result.message)
        self.assertEqual(result.actions.count("buy_attempts"), 1)
        self.assertEqual(result.actions.count("increase_quantity"), 3)
        self.assertEqual(result.actions.count("auto_team"), 1)
        self.assertEqual(result.actions.count("fight"), 7)
        self.assertEqual(result.actions.count("close_result"), 14)
        self.assertNotIn("quick_invite", result.actions)

    def test_restarting_after_purchase_uses_existing_attempts(self):
        screens = [lobby(0), Screen(("buy_exhausted", "exhausted_cancel")), lobby(0)]
        result = self.run_replay(screens)
        self.assertEqual(result.status, "completed", result.message)
        self.assertEqual(result.actions, ("probe_purchase", "close_buy_exhausted"))

    def test_purchase_confirmation_is_not_repeated_when_server_stalls(self):
        result = self.run_replay([lobby(3), purchase(4, 800)], freeze_buy=True)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.actions.count("buy_attempts"), 1)

    def test_outside_bonus_hours_creates_and_invites_before_fighting(self):
        screens = [lobby(3), Screen(("buy_exhausted", "exhausted_cancel")), lobby(3),
                   party(3, ready=0), party(3)]
        result = self.run_replay(screens, hour=15, stop_after="fight")
        self.assertEqual(result.status, "cancelled", result.message)
        self.assertIn("create_team", result.actions)
        self.assertIn("quick_invite", result.actions)
        self.assertNotIn("auto_team", result.actions)
        self.assertLess(result.actions.index("quick_invite"), result.actions.index("fight"))

    def test_unknown_or_excessive_purchase_cost_never_confirms(self):
        for cost in (None, 801):
            with self.subTest(cost=cost):
                result = self.run_replay([lobby(3), purchase(4, cost)])
                self.assertEqual(result.status, "blocked")
                self.assertNotIn("buy_attempts", result.actions)

    def test_bonus_hours_follow_vietnam_time_at_boundaries(self):
        for hour, minute, expected in ((11, 59, False), (12, 0, True), (13, 59, True),
                                       (14, 0, False), (17, 59, False), (18, 0, True),
                                       (21, 59, True), (22, 0, False)):
            with self.subTest(hour=hour, minute=minute):
                instant = datetime(2026, 11, 5, hour, minute, tzinfo=VIETNAM)
                self.assertEqual(bonus_hours(instant.astimezone(timezone.utc)), expected)

    def test_actual_reward_label_remains_recognizable_when_counter_changes(self):
        detector = TeamArenaDetector()
        folder = Path(__file__).parent/"fixtures/team_arena"
        for remaining in (6, 1):
            frame = cv2.imread(str(folder/f"rewards_{remaining}.png"))
            for width in (1920, 1280, 960):
                with self.subTest(remaining=remaining, width=width):
                    resized = cv2.resize(frame, (width, round(frame.shape[0]*width/frame.shape[1])),
                                         interpolation=cv2.INTER_AREA)
                    _, png = cv2.imencode(".png", resized)
                    observed = detector.decode(png.tobytes())
                    self.assertEqual(detector.result_page(observed), "rewards")
                    self.assertEqual(detector.reward_attempts(observed), remaining)


if __name__ == "__main__":
    unittest.main()
