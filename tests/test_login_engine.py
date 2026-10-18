import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import login_engine as login


class FakeClock:
    def __init__(self):
        self.time = 0

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += seconds


class FakeDevice:
    def __init__(self, states):
        self.states = iter(states)
        self.state = 0
        self.actions = []

    def capture(self):
        self.state = next(self.states, self.state)
        frame = np.full((9, 16, 3), self.state, np.uint8)
        return cv2.imencode(".png", frame)[1].tobytes()

    def launch(self, reset=False):
        self.actions.append(("launch", reset))

    def tap(self, x, y, frame_size):
        self.actions.append(("tap", x, y))

    def replace_text(self, value):
        self.actions.append(("text", value))


class FakeDetector:
    SCREENS = {
        1: {"zingid"},
        2: {"zingid_form", "cancel", "submit"},
        3: {"start_game", "switch_account", "choose_server", "terms_label"},
        4: {"server_panel", "played_tab"},
        5: {"start_game", "switch_account", "choose_server", "terms_label"},
        6: {"lobby_announcement", "announcement_confirm"},
        7: {"promo_dismiss"},
        8: {"lobby_status", "lobby_menu"},
        9: {"server_panel", "played_tab"},
    }

    @staticmethod
    def decode(png):
        return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)

    def find(self, frame, name, threshold=.92):
        if name in self.SCREENS.get(int(frame[0, 0, 0]), set()):
            return login.Match(name, 900, 340, 100, 30, 1)
        return None

    def first_played_card(self, frame):
        return login.Match("server_card", 616, 171, 35, 30, 1) if int(frame[0, 0, 0]) == 4 else None

    def terms_checked(self, frame, label):
        return int(frame[0, 0, 0]) == 5

    def orange_button(self, frame, match):
        return True

    def unobscured(self, frame, match):
        return True


class LoginTests(unittest.TestCase):
    def run_engine(self, states, **options):
        clock, device = FakeClock(), FakeDevice(states)
        engine = login.LoginEngine(device, detector=FakeDetector(), timeout=35,
                                   clock=clock.now, sleeper=clock.sleep, startup_delay=0)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch.object(login, "ROOT", Path(directory)):
                result = engine.run("test-user", "test-password", **options)
        return result, device

    def test_full_login_requires_credentials_and_two_verified_lobby_frames(self):
        result, device = self.run_engine([1, 2, 2, 2, 2, 3, 4, 3, 5, 6, 7, 8, 8], accept_terms=True)
        self.assertEqual(result.status, "success")
        self.assertEqual([a[1] for a in device.actions if a[0] == "text"], ["test-user", "test-password"])
        self.assertEqual(device.actions[0], ("launch", True))

    def test_saved_session_cannot_be_reported_as_selected_account(self):
        result, device = self.run_engine([5] * 50, accept_terms=True)
        self.assertEqual(result.status, "unknown")
        self.assertFalse(any(a[0] == "text" for a in device.actions))
        self.assertEqual(len([a for a in device.actions if a[0] == "tap"]), 2)

    def test_start_button_authentication_reopens_title_before_choosing_server(self):
        states = [5] * 12 + [1, 2, 2, 2, 2] + [3] * 6 + [4, 5, 6, 7, 8, 8]
        result, device = self.run_engine(states, accept_terms=True)
        self.assertEqual(result.status, "success")
        self.assertEqual(len([a for a in device.actions if a[0] == "launch"]), 2)

    def test_consent_can_be_reapplied_after_game_restarts_and_changes_server(self):
        states = [3] * 4 + [5, 1, 2, 2, 2, 2] + [3] * 4 + [4, 3, 5, 8, 8]
        result, device = self.run_engine(states, accept_terms=True)
        self.assertEqual(result.status, "success")
        self.assertEqual(device.actions.count(("tap", 782, 355)), 2)

    def test_failed_authentication_is_submitted_only_once(self):
        result, device = self.run_engine([2] * 50)
        self.assertEqual(result.status, "failed")
        self.assertEqual(len([a for a in device.actions if a[0] == "text"]), 2)

    def test_empty_server_history_stops_before_character_creation(self):
        result, device = self.run_engine([2, 2, 2, 2, 3] + [9] * 20, accept_terms=True)
        self.assertEqual(result.status, "needs_character")

    def test_consent_is_not_accepted_without_option(self):
        result, _ = self.run_engine([2, 2, 2, 2, 3, 4, 3])
        self.assertEqual(result.status, "needs_terms")

    def test_unknown_screen_produces_no_taps(self):
        result, device = self.run_engine([0] * 50)
        self.assertEqual(result.status, "timeout")
        self.assertFalse(any(a[0] == "tap" for a in device.actions))

    def test_stop_event_prevents_launch(self):
        stop = threading.Event()
        stop.set()
        device = FakeDevice([0])
        result = login.LoginEngine(device, stop=stop).run("test", "test")
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(device.actions, [])

    def test_account_file_bom_comments_and_duplicates(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "accounts.txt"
            path.write_text("\ufeffuser1\n# note\n\nuser2\nuser1\n", encoding="utf-8")
            self.assertEqual(login.load_accounts(path), ["user1", "user2"])

    def test_field_replacement_clears_both_sides_and_uses_writer(self):
        calls, texts = [], []
        device = login.AdbDevice("adb", "serial", lambda *a, **kw: calls.append(a),
                                 lambda *a: texts.append(a))
        device.replace_text("example")
        self.assertEqual(calls[0].count("67"), 128)
        self.assertEqual(calls[0].count("112"), 128)
        self.assertNotIn("example", calls[0])
        self.assertEqual(texts[0][-1], "example")

    def test_dimmed_lobby_is_not_accepted_as_visible(self):
        detector = login.Detector()
        template = detector.templates["lobby_menu"]
        frame = np.zeros((1080, 1920, 3), np.uint8)
        y, x = 1024, 24
        h, w = template.shape
        frame[y:y+h, x:x+w] = cv2.cvtColor((template * .3).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        match = login.Match("lobby_menu", x, y, w, h, 1)
        self.assertFalse(detector.unobscured(frame, match))

    def test_played_card_detection_prefers_first_character_not_highest_match(self):
        detector = login.Detector()
        frame = np.zeros((1080, 1920, 3), np.uint8)
        template = detector.templates["server_card"]
        h, w = template.shape
        for x in (616, 1155):
            frame[171:171+h, x:x+w] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
        card = detector.first_played_card(frame)
        self.assertEqual((card.x, card.y), (616, 171))
        self.assertIsNone(detector.first_played_card(np.zeros_like(frame)))

    def test_capture_error_still_returns_result_when_diagnostics_cannot_decode(self):
        device = FakeDevice([0])
        device.capture = lambda: b"invalid-image"
        result = login.LoginEngine(device, detector=FakeDetector()).run("test", "test-password")
        self.assertEqual(result.status, "error")
        self.assertNotIn("test-password", result.message)


if __name__ == "__main__":
    unittest.main()
