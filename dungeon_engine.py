"""Observe the Time Machine dungeon; advance on a verified win, stop on a loss."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from login_engine import AdbDevice, Match, SIZE

ROOT = Path(__file__).resolve().parent
REFERENCE_HEIGHT = 597


@dataclass(frozen=True)
class DungeonResult:
    status: str
    message: str
    wins: int = 0
    screenshot: str = ""


class DungeonDetector:
    # Fractions of the observed image, so left/right anchored UI also works on 16:9.
    REGIONS = {
        "time_machine": (.35, .06, .92, .44),
        "event_home": (.50, .04, 1, .28),
        "event_intro": (.02, .03, .60, .35),
        "intro_dismiss": (.20, .90, .80, 1),
        "dungeon_entry": (.70, .77, 1, 1),
        "chapter_screen": (0, .24, .98, .88),
        "chapter_frontier": (.08, .04, .95, .77),
        "stage_screen": (.75, .80, 1, 1),
        "stage_frontier": (.03, 0, .97, .80),
        "stage_dialog": (.23, .28, .68, .48),
        "fight": (.52, .65, .87, .92),
        "map_back": (0, 0, .23, .17),
        "victory": (.10, .02, .90, .65),
        "defeat": (.10, .02, .90, .65),
        "next_stage": (.30, .55, .98, 1),
        "result_exit": (.03, .55, .95, 1),
        "battle_screen": (0, 0, .18, .20),
        "battle_skip": (.78, .82, 1, 1),
    }

    def __init__(self, asset_dir: Path | None = None):
        self.templates = {}
        self.scaled = {}
        for path in (asset_dir or ROOT / "assets/dungeon").glob("*.png"):
            template = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
            if template is not None:
                name = path.stem.split("__", 1)[0]
                self.templates.setdefault(name, template)
                # The phone examples and MuMu can use slightly different UI scales.
                self.scaled.setdefault(name, []).extend([
                    (cv2.resize(template, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), s)
                    for s in (.85, .90, .95, 1., 1.05, 1.10, 1.15)
                ])

    @property
    def results_ready(self) -> bool:
        return {"victory", "defeat"} <= self.templates.keys() and bool(
            {"next_stage", "result_exit"} & self.templates.keys())

    @staticmethod
    def decode(png: bytes) -> np.ndarray:
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Không đọc được ảnh màn hình MuMu.")
        height, width = image.shape[:2]
        if not 1.65 <= width / height <= 2.5:
            raise ValueError("Hãy đặt MuMu ở màn hình ngang để chạy phó bản.")
        return cv2.resize(image, (round(width * REFERENCE_HEIGHT / height), REFERENCE_HEIGHT),
                          interpolation=cv2.INTER_AREA)

    def find(self, frame: np.ndarray, name: str, threshold: float = .87) -> Match | None:
        if name not in self.scaled:
            return None
        height, width = frame.shape[:2]
        fractions = self.REGIONS.get(name, (0, 0, 1, 1))
        x1, y1, x2, y2 = [round(p * size) for p, size in zip(fractions, (width, height, width, height))]
        gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        best = None
        for template, scale in self.scaled[name]:
            th, tw = template.shape
            if th > gray.shape[0] or tw > gray.shape[1]:
                continue
            scores = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, point = cv2.minMaxLoc(scores)
            if score < threshold or (best and score <= best.score):
                continue
            x, y = point
            # Correlation alone also matches the dimmed map behind a dialog.
            if gray[y:y + th, x:x + tw].mean() < template.mean() * .78:
                continue
            anchor_height = round({"chapter_frontier": 54, "stage_frontier": 44}.get(name, th / scale) * scale)
            best = Match(name, x + x1, y + y1 + (th - anchor_height) // 2, tw, anchor_height, score)
        return best


class DungeonEngine:
    def __init__(self, device: AdbDevice, *, stop: threading.Event | None = None,
                 progress: Callable[[str], None] | None = None,
                 preview: Callable[[bytes], None] | None = None,
                 detector: DungeonDetector | None = None,
                 clock: Callable = time.monotonic, sleeper: Callable | None = None,
                 navigation_timeout: float = 35, battle_timeout: float = 300):
        self.device = device
        self.stop = stop or threading.Event()
        self.progress = progress or (lambda message: None)
        self.preview = preview or (lambda png: None)
        self.detector = detector or DungeonDetector()
        self.clock, self.sleeper = clock, sleeper or self.stop.wait
        self.navigation_timeout, self.battle_timeout = navigation_timeout, battle_timeout
        self.last_png = b""
        self.frame_size = SIZE
        self.wins = 0

    def _check_stop(self) -> None:
        if self.stop.is_set():
            raise InterruptedError()

    def _observe(self) -> np.ndarray:
        self._check_stop()
        self.last_png = self.device.capture()
        raw = cv2.imdecode(np.frombuffer(self.last_png, np.uint8), cv2.IMREAD_COLOR)
        if raw is None:
            raise ValueError("Ảnh chụp không hợp lệ.")
        self.frame_size = raw.shape[1], raw.shape[0]
        frame = self.detector.decode(self.last_png)
        self.preview(self.last_png)
        return frame

    def _tap(self, frame: np.ndarray, match: Match, dy: float = 0) -> None:
        self._check_stop()
        x, y = match.center
        x = min(frame.shape[1] - 1, max(0, x))
        y = min(frame.shape[0] - 1, max(0, round(y + dy)))
        self.device.tap(round(x * SIZE[0] / frame.shape[1]),
                        round(y * SIZE[1] / frame.shape[0]), self.frame_size)

    def _finish(self, status: str, message: str) -> DungeonResult:
        screenshot = ""
        if self.last_png:
            try:
                folder = ROOT / "runtime"
                folder.mkdir(exist_ok=True)
                path = folder / "dungeon_last_screen.png"
                path.write_bytes(self.last_png)
                screenshot = str(path)
            except OSError:
                pass
        message = f"{message} Đã thắng {self.wins} ải trong lần chạy này."
        self.progress(message)
        return DungeonResult(status, message, self.wins, screenshot)

    @staticmethod
    def _chapter_title(frame: np.ndarray, marker: Match) -> np.ndarray | None:
        # The chapter name is below the crossed swords; exclude the star counter.
        x, _ = marker.center
        scale = marker.height / 54
        y1, y2 = round(marker.y + marker.height + 140 * scale), round(marker.y + marker.height + 184 * scale)
        x1, x2 = max(0, round(x - 180 * scale)), min(frame.shape[1], round(x + 180 * scale))
        crop = frame[y1:min(frame.shape[0], y2), x1:x2]
        if not crop.size:
            return None
        return cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (64, 12))

    def run(self, *, max_wins: int = 0) -> DungeonResult:
        """Use the current game session. Zero max_wins means continue until defeat."""
        self.wins, self.last_png = 0, b""
        try:
            self._check_stop()
            if not isinstance(max_wins, int) or isinstance(max_wins, bool) or max_wins < 0:
                raise ValueError("Giới hạn số ải phải là số nguyên từ 0 trở lên.")
            if not self.detector.results_ready:
                return self._finish("needs_samples", "Thiếu bộ ảnh nhận diện phó bản trong assets/dungeon; hãy khôi phục các tệp trước khi chạy.")
            mode = "navigate"
            deadline = self.clock() + self.navigation_timeout
            last_action = None
            outcome_streak, last_outcome = 0, None
            pending_route = None
            # A result must disappear after dismissal before another win is counted.
            dismissing = False
            cleared_frames = 0
            missing_marker_since = None
            scan_attempts = 0
            returned_to_chapters = False
            previous_chapter = None
            skip_sent = False
            self.progress("Đang tìm Cỗ Máy Thời Gian và ải đang mở…")
            while True:
                frame = self._observe()
                find = lambda name: self.detector.find(frame, name)
                defeat, victory = find("defeat"), find("victory")
                if defeat and victory:
                    return self._finish("unknown", "Kết quả trận đấu không rõ ràng; đã dừng.")
                outcome = "defeat" if defeat else "victory" if victory else None
                if dismissing:
                    if outcome:
                        cleared_frames = 0
                        if self.clock() >= deadline:
                            return self._finish("timeout", "Màn hình kết quả chưa đóng; đã dừng để tránh đếm lại trận.")
                        self.sleeper(.8)
                        continue
                    cleared_frames += 1
                    if cleared_frames < 2:
                        self.sleeper(.8)
                        continue
                    dismissing = False
                    mode = "after_next" if pending_route == "next_stage" else "navigate"
                    skip_sent = False
                    deadline = self.clock() + (self.battle_timeout if mode == "after_next" else self.navigation_timeout)
                    last_action = None
                if outcome:
                    outcome_streak = outcome_streak + 1 if outcome == last_outcome else 1
                    last_outcome = outcome
                    if outcome_streak < 2:
                        self.sleeper(.8)
                        continue
                    if outcome == "defeat":
                        return self._finish("defeat", "Đã thua; dừng ở màn hình kết quả.")
                    if mode != "victory":
                        # Never claim a win from an unrelated result already on screen.
                        if mode not in {"battle", "after_next"}:
                            return self._finish("existing_result", "Đang có kết quả trận trước. Hãy đóng kết quả rồi chạy lại.")
                        self.wins += 1
                        self.progress(f"Thắng ải {self.wins}; chuẩn bị ải tiếp theo…")
                        if max_wins and self.wins >= max_wins:
                            return self._finish("limit", "Đã đạt giới hạn số ải đã chọn.")
                        mode = "victory"
                        deadline = self.clock() + self.navigation_timeout
                    next_button, exit_button = find("next_stage"), find("result_exit")
                    button = next_button or exit_button
                    if button is None:
                        if self.clock() >= deadline:
                            return self._finish("unknown", "Đã thắng nhưng chưa nhận diện được nút sang ải tiếp theo.")
                        # Rewards and the dismiss hint appear after the win banner.
                        self.sleeper(.8)
                        continue
                    self._tap(frame, button)
                    pending_route = button.name
                    dismissing = True
                    cleared_frames = 0
                    missing_marker_since, scan_attempts = None, 0
                    deadline = self.clock() + self.navigation_timeout
                    outcome_streak, last_outcome = 0, None
                    self.sleeper(.8)
                    continue
                outcome_streak, last_outcome = 0, None
                if mode == "victory" and (find("stage_screen") or find("stage_dialog")
                                           or find("chapter_screen") or find("battle_screen")):
                    # Native quick combat can close the result before its hint is captured.
                    mode = "navigate"
                    last_action = None
                    skip_sent = False
                    missing_marker_since, scan_attempts = None, 0
                    deadline = self.clock() + self.navigation_timeout
                if mode == "navigate" and find("battle_screen"):
                    # The game can enter combat directly after selecting a stage.
                    mode = "battle"
                    skip_sent = False
                    deadline = self.clock() + self.battle_timeout
                    self.progress("Trận đấu đang chạy; đang chờ kết quả…")
                if self.clock() >= deadline:
                    return self._finish("timeout", "Chờ kết quả trận đấu quá lâu." if mode in {"battle", "after_next"}
                                        else "Không xác nhận được màn hình tiếp theo; đã dừng.")
                if mode == "victory":
                    self.sleeper(.8)
                    continue
                if mode in {"battle", "after_next"}:
                    skip = find("battle_skip")
                    if not skip_sent and skip and find("battle_screen"):
                        self.progress("Bỏ qua hoạt ảnh trận đấu bằng nút của game…")
                        self._tap(frame, skip)
                        skip_sent = True
                if mode == "battle":
                    # Never retry a stale fight dialog or tap an unknown popup.
                    self.sleeper(.8)
                    continue
                dialog, fight = find("stage_dialog"), find("fight")
                intro, intro_dismiss = find("event_intro"), find("intro_dismiss")
                event_home = find("event_home")
                stage_screen = find("stage_screen")
                chapter_screen = find("chapter_screen")
                action, target, dy = None, None, 0
                if intro and intro_dismiss:
                    action, target = "intro", intro_dismiss
                elif dialog and fight:
                    action, target = "fight", fight
                elif stage_screen:
                    target = find("stage_frontier")
                    if target:
                        action = "stage"
                        dy = target.height * (145 / 44)
                        missing_marker_since, scan_attempts = None, 0
                    else:
                        if missing_marker_since is None:
                            missing_marker_since = self.clock()
                        if self.clock() - missing_marker_since >= 3:
                            self._check_stop()
                            if scan_attempts < 3:
                                self.progress("Tìm ải đang mở ở phần tiếp theo của map…")
                                self.device.swipe(1500, 650, 450, 650, self.frame_size)
                                scan_attempts += 1
                                missing_marker_since = self.clock()
                                deadline = self.clock() + self.navigation_timeout
                            elif self.wins and not returned_to_chapters and find("map_back"):
                                self.progress("Không còn ải đang mở trên map; kiểm tra map tiếp theo…")
                                self._tap(frame, find("map_back"))
                                returned_to_chapters = True
                                last_action = None
                                deadline = self.clock() + self.navigation_timeout
                            else:
                                return self._finish("no_frontier", "Không tìm thấy dấu ải đang mở. Hãy kiểm tra map trong game.")
                elif chapter_screen:
                    target = find("chapter_frontier")
                    if target:
                        chapter_title = self._chapter_title(frame, target)
                        if returned_to_chapters and previous_chapter is not None:
                            if chapter_title is None or np.abs(chapter_title.astype(np.int16) - previous_chapter).mean() < 12:
                                return self._finish("no_frontier", "Chưa xác nhận được map mới đã mở; đã dừng để tránh đánh lại map cũ.")
                        previous_chapter = chapter_title.astype(np.int16) if chapter_title is not None else None
                        returned_to_chapters = False
                        action = "chapter"
                        dy = target.height * (90 / 54)
                elif event_home:
                    target = find("dungeon_entry")
                    if target:
                        action = "dungeon"
                else:
                    target = find("time_machine")
                    if target:
                        action = "event"
                if action and action != last_action:
                    messages = {"event": "Mở Cỗ Máy Thời Gian…", "intro": "Đóng bảng giới thiệu sự kiện…", "dungeon": "Mở Phó Bản của sự kiện…",
                                "chapter": "Chọn map đang mở…", "stage": "Chọn ải có dấu hai thanh kiếm…",
                                "fight": f"Bắt đầu trận {self.wins + 1}; đang chờ kết quả…"}
                    self.progress(messages[action])
                    self._tap(frame, target, dy)
                    last_action = action
                    if action == "fight":
                        mode = "battle"
                        skip_sent = False
                        deadline = self.clock() + self.battle_timeout
                    else:
                        mode = "navigate"
                        deadline = self.clock() + self.navigation_timeout
                self.sleeper(.8)
        except InterruptedError:
            return self._finish("cancelled", "Đã dừng theo yêu cầu.")
        except Exception as exc:
            return self._finish("error", f"Lỗi chạy phó bản: {exc}")
