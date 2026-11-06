"""Daily mission navigation and actions in the ordinary lobby."""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from functools import cached_property
from pathlib import Path

import cv2
import numpy as np

from chest_skill import ChestDetector
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector
from login_engine import SIZE, Match

ROOT = Path(__file__).resolve().parent
# The game accepts dismissal on the bottom hint strip, below "Tiếp 500 lần".
# Taps in the middle of this particular reward overlay can be ignored.
SOUL_REWARD_DISMISS_POINTS = ((.50, .974), (.38, .974), (.62, .974))
SOUL_REWARD_DISMISS_DELAY = 1.5


@dataclass(frozen=True)
class DailyTasksResult:
    status: str
    message: str
    actions: tuple[str, ...] = ()
    screenshot: str = ""
    evidence_dir: str = ""


class DailyTasksDetector(DungeonDetector):
    DAILY_REGIONS = {
        "main_liep_hon": (0, .88, .55, 1),
        "main_hoang_thanh": (0, .88, .60, 1),
        "mission_entry": (.75, .03, 1, .27),
        "mission_title": (0, 0, .50, .11),
        "achievement_title": (0, 0, .50, .11),
        "daily_tab": (.05, .88, .50, 1),
        "daily_active": (.05, .88, .50, 1),
    }
    SOUL_REGIONS = {
        "soul_entry": (.19, .80, .40, 1),
        "soul_title": (0, 0, .32, .12),
        "soul_quick": (.71, .78, .96, 1),
        "soul_dialog": (.33, 0, .67, .33),
        "soul_500_heading": (.51, .09, .88, .48),
        "soul_500_button": (.51, .49, .89, .87),
        "soul_priority_on": (.11, .70, .35, 1),
        "soul_priority_off": (.11, .70, .35, 1),
        "soul_convert_on": (.51, .70, .72, 1),
        "soul_convert_off": (.51, .70, .72, 1),
    }
    HUNTER_REGIONS = {
        "soul_reward_title": (.18, 0, .82, .24),
        "soul_reward_500": (0, .05, .45, .30),
        "soul_reward_continue_500": (.34, .85, .69, .98),
        "hunter_entry": (0, .75, .25, 1),
        "hunter_title": (0, 0, .27, .09),
        "hunter_refresh_label": (0, .12, .25, .25),
        "hunter_challenge_label": (0, .20, .25, .34),
        "hunter_skip_label": (.54, .77, .85, .92),
        "hunter_skip_on": (.51, .77, .76, .92),
        "hunter_refresh": (.25, .83, .56, 1),
        "hunter_fight": (.49, .83, .78, 1),
        "hunter_trieu_van": (.21, .07, .57, .25),
        "hunter_nam_hoa": (.21, .07, .57, .25),
        "hunter_nameplate": (.21, .07, .57, .25),
        "hunter_victory": (.32, .02, .72, .25),
        "hunter_dismiss_hint": (.31, .90, .70, 1),
    }
    REGIONS = DAILY_REGIONS | SOUL_REGIONS | HUNTER_REGIONS

    def __init__(self, asset_dir: Path | None = None):
        super().__init__(asset_dir or ROOT/"assets/daily")

    @property
    def ready(self) -> bool:
        return set(self.DAILY_REGIONS) <= self.templates.keys()

    @property
    def soul_ready(self) -> bool:
        return (set(self.SOUL_REGIONS) | set(self.HUNTER_REGIONS) |
                {"main_hoang_thanh"}) <= self.templates.keys()

    def main_lobby(self, frame: np.ndarray) -> bool:
        return bool(self.find(frame, "main_liep_hon", .94) and
                    self.find(frame, "main_hoang_thanh", .94))

    def soul_reward_visible(self, frame):
        if not self.find(frame, "soul_reward_title", .91):
            return False
        # The reward label is drawn over changing effects. The repeat button
        # identifies the same panel when the label is obscured.
        return bool(self.find(frame, "soul_reward_500", .92) or
                    self.find(frame, "soul_reward_continue_500", .95))

    def soul_checkbox(self, frame, name):
        for checked in (True, False):
            suffix = "on" if checked else "off"
            marker = self.find(frame, f"{name}_{suffix}", .90)
            if marker is None:
                continue
            crop = frame[marker.y:marker.y+marker.height, marker.x:marker.x+marker.width]
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            green = cv2.inRange(hsv, (35, 140, 150), (85, 255, 255))
            ratio = np.count_nonzero(green) / green.size
            if (checked and ratio >= .08) or (not checked and ratio < .02):
                return checked, marker
        return None, None

    def hunter_skip(self, frame):
        label = self.find(frame, "hunter_skip_label", .91)
        if not label:
            return None, None
        size = label.width / 83
        x, y = label.x - round(37*size), label.y - round(9*size)
        w, h = round(33*size), round(31*size)
        box = Match("hunter_skip", x, y, w, h, label.score)
        crop = frame[y:y+h, x:x+w]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 140, 150), (85, 255, 255)).mean() / 255
        tick = self.find(frame, "hunter_skip_on", .88)
        if green >= .08 and tick and abs(tick.center[0] - box.center[0]) <= w/3:
            return True, box
        if green < .02 and hsv[h//4:3*h//4, w//4:3*w//4, 2].mean() < 95:
            return False, box
        return None, None

    @cached_property
    def hunter_digits(self):
        return EquipmentDetector().digits

    def hunter_count(self, frame, label):
        x = label.x + label.width
        crop = frame[label.y:label.y+label.height,
                     x+round(.11*label.width):x+round(.53*label.width)]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        mask = cv2.inRange(gray, 135, 255)
        return ChestDetector._read_mask(mask, round(label.height*.49), self.hunter_digits)


class DailyTasksSkill:
    name = "open_main_lobby_daily_tasks"

    def __init__(self, device, *, detector=None, stop=None, progress=None,
                 preview=None, clock=time.monotonic, sleeper=None, timeout=20,
                 evidence_root: Path | None = None):
        self.device = device
        self.detector = detector or DailyTasksDetector()
        self.stop = stop or threading.Event()
        self.progress = progress or (lambda message: None)
        self.preview = preview or (lambda png: None)
        self.clock = clock
        self.sleeper = sleeper or self.stop.wait
        self.timeout = timeout
        self.evidence_root = evidence_root or ROOT/"runtime/daily_tasks"
        self.last_png = b""
        self.frame_size = SIZE
        self.actions = []

    def _check(self):
        if self.stop.is_set():
            raise InterruptedError()

    def _observe(self):
        self._check()
        self.last_png = self.device.capture()
        raw = cv2.imdecode(np.frombuffer(self.last_png, np.uint8), cv2.IMREAD_COLOR)
        if raw is None:
            raise ValueError("Không đọc được màn hình MuMu.")
        self.frame_size = raw.shape[1], raw.shape[0]
        frame = self.detector.decode(self.last_png)
        self.preview(self.last_png)
        self._check()
        return frame

    def _tap(self, frame, marker, action):
        self._check()
        x, y = marker.center
        self.device.tap(round(x*SIZE[0]/frame.shape[1]),
                        round(y*SIZE[1]/frame.shape[0]), self.frame_size)
        self.actions.append(action)

    def _finish(self, status, message):
        screenshot = ""
        self.folder.mkdir(parents=True, exist_ok=True)
        if self.last_png:
            path = self.folder/"result.png"
            path.write_bytes(self.last_png)
            screenshot = str(path)
        result = DailyTasksResult(status, message, tuple(self.actions), screenshot, str(self.folder))
        (self.folder/"result.json").write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        self.progress(message)
        return result

    def _soul_next_action(self, frame):
        detector = self.detector
        heading = detector.find(frame, "soul_500_heading", .92)
        if heading and detector.find(frame, "soul_dialog", .92):
            options = [
                (name, *detector.soul_checkbox(frame, name))
                for name in ("soul_priority", "soul_convert")
            ]
            if any(checked is None for _, checked, _ in options):
                return None, None
            for name, checked, marker in options:
                if not checked:
                    return name, marker
            button = detector.find(frame, "soul_500_button", .92)
            if button and abs(button.center[0] - heading.center[0]) <= heading.width / 2:
                return "soul_submit_500", button
            return None, None

        if detector.find(frame, "soul_title", .92):
            return "soul_open_quick", detector.find(frame, "soul_quick", .90)
        # The Liệp Hồn icon and the neighbouring Hoàng Thành label identify the ordinary lobby.
        if detector.find(frame, "main_hoang_thanh", .90):
            return "soul_open", detector.find(frame, "soul_entry", .90)
        return None, None

    @staticmethod
    def _empty_result_space(frame, point=(.85, .37)):
        height, width = frame.shape[:2]
        x, y = point
        return Match("result_space", round(x*width), round(y*height), 1, 1, 1.)

    def run_soul_hunt(self) -> DailyTasksResult:
        """Run one 500-draw batch, then spend the remaining Hồn Tướng challenges."""
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        messages = {
            "soul_open": "Mở Liệp Hồn ở sảnh chính…",
            "soul_open_quick": "Mở Liệp Hồn Nhanh…",
            "soul_priority": "Bật ưu tiên dùng Quan Vũ Liệp Hồn Lệnh…",
            "soul_convert": "Bật tự chuyển hóa Chiến Hồn Tím…",
            "soul_submit_500": "Đã xác nhận hai ô, bấm Liệp Hồn 500 lần…",
            "soul_close_reward": "Đóng bảng kết quả Liệp Hồn 500 lần…",
            "hunter_open": "Mở Hồn Tướng…",
            "hunter_skip": "Bật Bỏ qua chiến đấu…",
            "hunter_refresh": "Làm mới Hồn Tướng…",
            "hunter_fight": "Đã nhận diện Triệu Vân hoặc Nam Hoa, bấm Chiến…",
            "hunter_close_reward": "Đóng bảng thưởng Hồn Tướng…",
        }
        pending = None
        closed_battle_reward = False
        hunter_started = False
        fights = 0
        reward_close_attempts = 0
        reward_close_after = 0.
        waiting_for = "màn hình Liệp Hồn"
        try:
            self._check()
            if not self.detector.soul_ready:
                return self._finish("needs_samples", "Thiếu ảnh nhận diện Liệp Hồn trong assets/daily.")
            deadline = self.clock()+self.timeout
            previous = None
            while self.clock() < deadline:
                frame = self._observe()
                detector = self.detector
                action, marker, count = None, None, None
                if not hunter_started and detector.soul_reward_visible(frame):
                    waiting_for = "bảng kết quả Liệp Hồn 500 lần đã đóng"
                    if self.clock() >= reward_close_after:
                        if reward_close_attempts < len(SOUL_REWARD_DISMISS_POINTS):
                            point = SOUL_REWARD_DISMISS_POINTS[reward_close_attempts]
                            action, marker = "soul_close_reward", self._empty_result_space(frame, point)
                        else:
                            action = "soul_reward_still_open"
                elif (not closed_battle_reward and detector.find(frame, "hunter_dismiss_hint", .91)
                      and ((pending and pending[0] == "hunter_fight")
                           or detector.find(frame, "hunter_victory", .92))):
                    hunter_started = True
                    action, marker = "hunter_close_reward", self._empty_result_space(frame)
                elif detector.find(frame, "hunter_title", .92):
                    hunter_started = True
                    challenge_label = detector.find(frame, "hunter_challenge_label", .92)
                    refresh_label = detector.find(frame, "hunter_refresh_label", .92)
                    if challenge_label and refresh_label:
                        challenges = detector.hunter_count(frame, challenge_label)
                        refreshes = detector.hunter_count(frame, refresh_label)
                        waiting_for = "số lượt và tên Hồn Tướng"
                        if pending:
                            kind, old_count = pending
                            observed = challenges if kind == "hunter_fight" else refreshes
                            waiting_for = "số lượt giảm sau khi Chiến" if kind == "hunter_fight" else "số lượt giảm sau khi Làm Mới"
                            if observed == old_count - 1:
                                if kind == "hunter_fight":
                                    fights += 1
                                pending = None
                                previous = None
                        if not pending and challenges in (0, 1, 2, 3):
                            if challenges == 0:
                                action = "hunter_done"
                            else:
                                skip, skip_box = detector.hunter_skip(frame)
                                target = (detector.find(frame, "hunter_trieu_van", .90)
                                          or detector.find(frame, "hunter_nam_hoa", .91))
                                if skip is False:
                                    action, marker = "hunter_skip", skip_box
                                elif skip is True and target:
                                    action, count = "hunter_fight", challenges
                                    marker = detector.find(frame, action, .92)
                                elif (skip is True and refreshes is not None
                                      and detector.find(frame, "hunter_nameplate", .89)):
                                    if refreshes == 0:
                                        action = "hunter_no_refresh"
                                    else:
                                        action, count = "hunter_refresh", refreshes
                                        marker = detector.find(frame, action, .92)
                elif not hunter_started:
                    if "soul_close_reward" in self.actions:
                        if detector.find(frame, "soul_title", .92):
                            action, marker = "hunter_open", detector.find(frame, "hunter_entry", .90)
                        waiting_for = "biểu tượng Hồn Tướng sau khi đóng bảng thưởng"
                    elif "soul_submit_500" in self.actions:
                        waiting_for = "bảng kết quả Liệp Hồn 500 lần"
                    else:
                        action, marker = self._soul_next_action(frame)

                terminal = action in {"hunter_done", "hunter_no_refresh", "soul_reward_still_open"}
                repeatable = action in {"hunter_fight", "hunter_refresh", "hunter_close_reward", "soul_close_reward"}
                current = (action, count) if terminal or (marker and (repeatable or action not in self.actions)) else None
                if current and current == previous:
                    if action == "hunter_done":
                        return self._finish("completed", f"Hồn Tướng đã hết lượt khiêu chiến. Lượt dùng trong lần chạy này: {fights}.")
                    if action == "hunter_no_refresh":
                        return self._finish("blocked", "Hết lượt làm mới mà chưa gặp Triệu Vân hoặc Nam Hoa.")
                    if action == "soul_reward_still_open":
                        return self._finish("blocked", f"Bảng kết quả Liệp Hồn 500 lần vẫn mở sau {reward_close_attempts} lần chạm vùng trống.")
                    self.progress(messages[action])
                    self._tap(frame, marker, action)
                    deadline = self.clock()+self.timeout
                    if action == "soul_close_reward":
                        reward_close_attempts += 1
                        reward_close_after = self.clock()+SOUL_REWARD_DISMISS_DELAY
                    elif action in {"hunter_fight", "hunter_refresh"}:
                        pending = action, count
                        closed_battle_reward = False
                    elif action == "hunter_close_reward":
                        closed_battle_reward = True
                    current = None
                previous = current
                self.sleeper(.7)
            return self._finish("blocked", f"Đã dừng vì chưa xác nhận được {waiting_for}. Lượt khiêu chiến đã xác nhận: {fights}.")
        except InterruptedError:
            return self._finish("cancelled", "Đã dừng Liệp Hồn.")
        except Exception as exc:
            return self._finish("error", f"Lỗi khi chạy Liệp Hồn: {exc}")

    def run(self) -> DailyTasksResult:
        """Navigation only: never press a task, reward, milestone chest or quick claim."""
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        try:
            self._check()
            if not self.detector.ready:
                return self._finish("needs_samples", "Thiếu ảnh nhận diện trong assets/daily; chưa thao tác.")
            deadline = self.clock()+self.timeout
            previous, streak = None, 0
            while self.clock() < deadline:
                frame = self._observe()
                mission = self.detector.find(frame, "mission_title", .94)
                achievement = self.detector.find(frame, "achievement_title", .94)
                active = self.detector.find(frame, "daily_active", .94)
                tab = self.detector.find(frame, "daily_tab", .94)
                entry = self.detector.find(frame, "mission_entry", .94)
                if mission and active:
                    state = "daily"
                elif achievement and tab:
                    state = "select_daily"
                elif not mission and not achievement and self.detector.main_lobby(frame) and entry:
                    state = "lobby"
                else:
                    state = "unknown"
                streak = streak+1 if state == previous else 1
                previous = state
                if streak >= 2:
                    if state == "daily":
                        self._check()
                        return self._finish("opened", "Đã mở Nhiệm vụ hằng ngày ở sảnh chính. Chưa thực hiện nhiệm vụ hay nhận thưởng.")
                    if state == "lobby" and "open_missions" not in self.actions:
                        self.progress("Đã xác nhận sảnh chính; mở icon cuộn giấy Nhiệm vụ…")
                        self._tap(frame, entry, "open_missions")
                        previous, streak = None, 0
                    elif state == "select_daily" and "select_daily_tab" not in self.actions:
                        self.progress("Chuyển từ Thành tựu sang tab Nhiệm vụ hằng ngày…")
                        self._tap(frame, tab, "select_daily_tab")
                        previous, streak = None, 0
                    elif state == "unknown" and not self.actions:
                        return self._finish("blocked", "Hãy về sảnh chính của OMG 3Q rồi mở Nhiệm vụ hằng ngày. Chưa gửi thao tác.")
                self.sleeper(.7)
            return self._finish("blocked", "Chưa xác nhận được bảng Nhiệm vụ hằng ngày; đã dừng, không bấm lại hoặc nhận thưởng.")
        except InterruptedError:
            return self._finish("cancelled", "Đã dừng mở Nhiệm vụ hằng ngày.")
        except Exception as exc:
            return self._finish("error", f"Không mở được Nhiệm vụ hằng ngày: {exc}")
