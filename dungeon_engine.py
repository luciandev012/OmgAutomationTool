"""Observe the Time Machine dungeon; advance on wins and optionally retry losses."""
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
# Sweep toward later stages, then back across the whole map. Missing a marker
# alone never proves that the chapter has been completed.
MAP_SCAN_DIRECTIONS = ("later",) * 3 + ("earlier",) * 6


@dataclass(frozen=True)
class DungeonResult:
    status: str
    message: str
    wins: int = 0
    screenshot: str = ""
    auto_activations: int = 0
    battle_skips: int = 0
    retries: int = 0
    stage_retries: int = 0


@dataclass
class BattleControls:
    """Input state for one battle; an Auto toggle always needs confirmation."""
    observed: str | None = None
    streak: int = 0
    verified_on: bool = False
    toggle_pending: bool = False
    unverified_since: float | None = None
    activations: int = 0
    skip_sent: bool = False


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
        "battle_auto_on": (.72, .80, .96, 1),
        "battle_auto_off": (.72, .80, .96, 1),
        "next_chapter": (.65, .45, 1, .82),
        "stage_frontier_tip": (.03, .03, .40, .14),
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

    @property
    def controls_ready(self) -> bool:
        return {"battle_screen", "battle_skip", "battle_auto_on", "battle_auto_off"} <= self.templates.keys()

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
            if name in {"battle_auto_on", "battle_auto_off"}:
                # Grayscale correlation can confuse the same Auto lettering on
                # green and dark backgrounds. Check the button's actual color.
                crop = frame[y1+y:y1+y+th, x1+x:x1+x+tw]
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                green = float((cv2.inRange(hsv, (35, 75, 45), (90, 255, 255)) > 0).mean())
                if (name == "battle_auto_on" and green < .20) or (name == "battle_auto_off" and green > .08):
                    continue
            anchor_height = round({"chapter_frontier": 54, "stage_frontier": 44}.get(name, th / scale) * scale)
            best = Match(name, x + x1, y + y1 + (th - anchor_height) // 2, tw, anchor_height, score)
        if best is None and name == "stage_frontier":
            best = self._top_clipped_frontier(frame, max(threshold, .94))
        if best is None and name == "stage_frontier":
            # The first stage's swords can sit behind the chapter-name banner.
            # Its exposed blade tips remain above the banner; reconstruct the
            # same crossed-sword anchor used by the full marker templates.
            tip = self.find(frame, "stage_frontier_tip", max(threshold, .94))
            if tip:
                scale = tip.height / 20
                anchor_height = round(44 * scale)
                center_y = tip.center[1] + 24 * scale
                best = Match(name, tip.x, round(center_y - anchor_height / 2),
                             tip.width, anchor_height, tip.score)
        return best

    def _top_clipped_frontier(self, frame: np.ndarray, threshold: float) -> Match | None:
        """Match the visible lower swords at y=0 and restore their full anchor.

        The last boss may place the upper blades outside the screenshot. Compare
        only sufficiently large, textured suffixes of the existing templates;
        require a strict score, brightness, and actual contact with the top edge.
        """
        h, w = frame.shape[:2]
        x1, x2 = round(w*.03), round(w*.97)
        gray = cv2.cvtColor(frame[:round(h*.15), x1:x2], cv2.COLOR_BGR2GRAY)
        best = None
        for template, scale in self.scaled.get("stage_frontier", []):
            th, tw = template.shape
            minimum = max(18, round(th*.35))
            for cut in range(max(1, round(th*.15)), th-minimum+1, 2):
                visible = template[cut:]
                vh = visible.shape[0]
                roi = gray[:vh+3]
                if tw > roi.shape[1] or roi.shape[0] < vh or visible.std() < 20:
                    continue
                scores = cv2.matchTemplate(roi, visible, cv2.TM_CCOEFF_NORMED)
                _, score, _, (x, y) = cv2.minMaxLoc(scores)
                if score < threshold or (best and score <= best.score) or y > 2 or y-cut >= 0:
                    continue
                if roi[y:y+vh, x:x+tw].mean() < visible.mean()*.78:
                    continue
                anchor_height = round(44*scale)
                # Preserve an off-screen center; the normal NPC offset is added
                # before _tap clamps the resulting on-screen input coordinate.
                anchor_y = y-cut+(th-anchor_height)//2
                best = Match("stage_frontier", x+x1, anchor_y, tw, anchor_height, score)
        return best

    @staticmethod
    def stage_identity(frame: np.ndarray) -> np.ndarray | None:
        """Read the static gold stage title, excluding the animated character/stars."""
        h, w = frame.shape[:2]
        title = frame[round(h*.23):round(h*.282), round(w*.32):round(w*.68)]
        hsv = cv2.cvtColor(title, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (15, 100, 140), (40, 255, 255))
        if cv2.countNonZero(mask) < 20:
            return None
        return cv2.resize(mask, (256, 24), interpolation=cv2.INTER_NEAREST)

    @staticmethod
    def same_stage(first: np.ndarray, second: np.ndarray) -> bool:
        union = np.count_nonzero(first | second)
        return bool(union and np.count_nonzero(first ^ second) / union <= .025)

    @staticmethod
    def map_identity(frame: np.ndarray) -> np.ndarray | None:
        """Read the white chapter name in the stage map's fixed upper-left banner."""
        h, w = frame.shape[:2]
        title = frame[round(h*.115):round(h*.18), :round(w*.30)]
        hsv = cv2.cvtColor(title, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 0, 160), (179, 100, 255))
        if cv2.countNonZero(mask) < 20:
            return None
        return cv2.resize(mask, (256, 32), interpolation=cv2.INTER_NEAREST)


class DungeonEngine:
    def __init__(self, device: AdbDevice, *, stop: threading.Event | None = None,
                 progress: Callable[[str], None] | None = None,
                 preview: Callable[[bytes], None] | None = None,
                 detector: DungeonDetector | None = None,
                 clock: Callable = time.monotonic, sleeper: Callable | None = None,
                 navigation_timeout: float = 35, battle_timeout: float = 300,
                 auto_timeout: float = 8):
        self.device = device
        self.stop = stop or threading.Event()
        self.progress = progress or (lambda message: None)
        self.preview = preview or (lambda png: None)
        self.detector = detector or DungeonDetector()
        self.clock, self.sleeper = clock, sleeper or self.stop.wait
        self.navigation_timeout, self.battle_timeout = navigation_timeout, battle_timeout
        self.auto_timeout = auto_timeout
        self.last_png = b""
        self.frame_size = SIZE
        self.wins = 0
        self.auto_activations = self.battle_skips = 0
        self.retries = self.stage_retries = 0

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
        if self.retries:
            message += f" Tổng số trận đánh lại: {self.retries}."
        self.progress(message)
        return DungeonResult(status, message, self.wins, screenshot, self.auto_activations,
                             self.battle_skips, self.retries, self.stage_retries)

    def _save_scan(self, index: int) -> None:
        if not self.last_png:
            return
        try:
            folder = ROOT / "runtime/dungeon_scan"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"scan_{index:02}.png").write_bytes(self.last_png)
        except OSError:
            pass

    def _battle_controls(self, frame: np.ndarray, state: BattleControls) -> str | None:
        """Enable Auto from a stable OFF state, then skip once after stable ON."""
        on = self.detector.find(frame, "battle_auto_on")
        off = self.detector.find(frame, "battle_auto_off")
        observed = "on" if on and not off else "off" if off and not on else None
        state.streak = state.streak + 1 if observed and observed == state.observed else (1 if observed else 0)
        state.observed = observed
        if state.unverified_since is None and not state.verified_on:
            state.unverified_since = self.clock()

        if observed == "on" and state.streak >= 2:
            if state.toggle_pending:
                self.progress("Đã xác nhận Auto được bật.")
            state.verified_on, state.toggle_pending = True, False
            state.unverified_since = None
            skip = self.detector.find(frame, "battle_skip")
            if skip and not state.skip_sent:
                self.progress("Auto đang bật; bỏ qua trận bằng nút của game…")
                self._tap(frame, skip)
                state.skip_sent = True
                self.battle_skips += 1
        elif observed == "off" and state.streak >= 2:
            if not state.toggle_pending:
                if state.activations >= 3:
                    return "Auto liên tục bị tắt; đã dừng để kiểm tra."
                self.progress("Auto đang tắt; bật Auto và chờ xác nhận…")
                self._tap(frame, off)
                state.activations += 1
                self.auto_activations += 1
                state.toggle_pending = True
                state.verified_on = False
                state.unverified_since = self.clock()

        if state.unverified_since is not None and self.clock() - state.unverified_since >= self.auto_timeout:
            return "Chưa xác nhận được Auto đang bật; dừng, không bấm lặp Auto hoặc Bỏ qua."
        return None

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

    def run(self, *, max_wins: int = 0, spam: bool = False, spam_limit: int = 100) -> DungeonResult:
        """Allow at most spam_limit additional fights per stage; wins reset that budget.

        An explicit new run with spam enabled may start on a previous defeat. It
        closes that result and retries the unchanged frontier in the same map.
        """
        self.wins, self.last_png = 0, b""
        self.auto_activations = self.battle_skips = 0
        self.retries = self.stage_retries = 0
        try:
            self._check_stop()
            if not isinstance(max_wins, int) or isinstance(max_wins, bool) or max_wins < 0:
                raise ValueError("Giới hạn số ải phải là số nguyên từ 0 trở lên.")
            if not isinstance(spam, bool):
                raise ValueError("Tùy chọn spam phải là bật hoặc tắt.")
            if not isinstance(spam_limit, int) or isinstance(spam_limit, bool) or spam_limit < 1:
                raise ValueError("Số lần spam phải là số nguyên lớn hơn 0.")
            if not self.detector.results_ready:
                return self._finish("needs_samples", "Thiếu bộ ảnh nhận diện phó bản trong assets/dungeon; hãy khôi phục các tệp trước khi chạy.")
            if not self.detector.controls_ready:
                return self._finish("needs_samples", "Thiếu mẫu Auto/Bỏ qua trong assets/dungeon; chưa bắt đầu trận.")
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
            controls = BattleControls()
            stage_identity = None
            stage_anchor = None
            retry_start_pending = False
            chapter_button_streak = 0
            transition_source = transition_title = None
            transition_kind = None
            transition_streak = 0
            clipped_candidate, clipped_streak = None, 0

            def stable_frontier(marker: Match, frame: np.ndarray) -> bool:
                nonlocal clipped_candidate, clipped_streak
                if marker.y >= 0:
                    clipped_candidate, clipped_streak = None, 0
                    return True
                stable = (clipped_candidate is not None and
                          abs(marker.center[0]-clipped_candidate.center[0]) <= frame.shape[1]*.015 and
                          abs(marker.center[1]-clipped_candidate.center[1]) <= frame.shape[0]*.015 and
                          abs(marker.height-clipped_candidate.height) <= max(3, marker.height*.15))
                clipped_streak = clipped_streak + 1 if stable else 1
                clipped_candidate = marker
                if clipped_streak < 2:
                    self.progress("Thấy dấu kiếm bị cắt ở mép trên; chờ xác nhận cùng vị trí…")
                return clipped_streak >= 2

            def confirm_retry() -> None:
                nonlocal retry_start_pending, mode
                if retry_start_pending:
                    self.stage_retries += 1
                    self.retries += 1
                    retry_start_pending = False
                    mode = "battle"
                    self.progress(f"Đánh lại cùng ải: {self.stage_retries}/{spam_limit}…")

            self.progress("Đang tìm Cỗ Máy Thời Gian và ải đang mở…")
            while True:
                frame = self._observe()
                matches = {}
                def find(name):
                    if name not in matches:
                        matches[name] = self.detector.find(frame, name)
                    return matches[name]
                defeat, victory = find("defeat"), find("victory")
                if defeat and victory:
                    return self._finish("unknown", "Kết quả trận đấu không rõ ràng; đã dừng.")
                outcome = "defeat" if defeat else "victory" if victory else None
                if outcome or not find("stage_screen") or find("stage_dialog"):
                    clipped_candidate, clipped_streak = None, 0
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
                    mode = ("retry" if pending_route == "retry" else
                            "after_next" if pending_route == "next_stage" else "navigate")
                    controls = BattleControls()
                    deadline = self.clock() + (self.battle_timeout if mode == "after_next" else self.navigation_timeout)
                    last_action = None
                if outcome:
                    outcome_streak = outcome_streak + 1 if outcome == last_outcome else 1
                    last_outcome = outcome
                    if outcome_streak < 2:
                        self.sleeper(.8)
                        continue
                    confirm_retry()
                    if outcome == "defeat":
                        if not spam:
                            return self._finish("defeat", "Đã thua; dừng ở màn hình kết quả.")
                        if mode not in {"battle", "after_next", "navigate", "defeat"}:
                            return self._finish("retry_unverified", "Gặp kết quả thua trong lúc chưa bắt đầu trận đánh lại; đã dừng.")
                        if self.stage_retries >= spam_limit:
                            return self._finish("spam_limit", f"Vẫn thua sau {self.stage_retries}/{spam_limit} lần đánh lại ải này. Đã dừng; bạn có thể chọn chạy một lượt spam mới hoặc dừng tiến trình.")
                        if mode != "defeat":
                            mode = "defeat"
                            deadline = self.clock() + self.navigation_timeout
                            self.progress(f"Đã thua; chuẩn bị đánh lại cùng ải ({self.stage_retries}/{spam_limit} lần đã dùng)…")
                        # Use the result's dismiss hint, then reopen the same
                        # map target rather than using the replay control.
                        button = find("result_exit")
                        if button is None:
                            if self.clock() >= deadline:
                                return self._finish("retry_unverified", "Chưa nhận diện được vùng đóng kết quả thua; đã dừng.")
                            self.sleeper(.8)
                            continue
                        self._tap(frame, button)
                        pending_route, dismissing, cleared_frames = "retry", True, 0
                        deadline = self.clock() + self.navigation_timeout
                        outcome_streak, last_outcome = 0, None
                        self.sleeper(.8)
                        continue
                    if mode != "victory":
                        # Never claim a win from an unrelated result already on screen.
                        if mode not in {"battle", "after_next"}:
                            return self._finish("existing_result", "Đang có kết quả trận trước. Hãy đóng kết quả rồi chạy lại.")
                        self.wins += 1
                        self.stage_retries = 0
                        stage_identity = None
                        stage_anchor = None
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
                if mode == "defeat":
                    # Some quick combat versions dismiss the result themselves.
                    mode, last_action = "retry", None
                    deadline = self.clock() + self.navigation_timeout
                if mode == "victory" and (find("stage_screen") or find("stage_dialog")
                                           or find("chapter_screen") or find("battle_screen")):
                    # Native quick combat can close the result before its hint is captured.
                    mode = "navigate"
                    last_action = None
                    controls = BattleControls()
                    missing_marker_since, scan_attempts = None, 0
                    deadline = self.clock() + self.navigation_timeout
                if mode == "navigate" and find("battle_screen"):
                    # The game can enter combat directly after selecting a stage.
                    mode = "battle"
                    controls = BattleControls()
                    deadline = self.clock() + self.battle_timeout
                    self.progress("Trận đấu đang chạy; đang chờ kết quả…")
                if self.clock() >= deadline:
                    return self._finish("timeout", "Chờ kết quả trận đấu quá lâu." if mode in {"battle", "after_next"}
                                        else "Đã bấm Chương kế nhưng chưa xác nhận được map mới; đã dừng." if mode == "chapter_transition"
                                        else "Không xác nhận được màn hình tiếp theo; đã dừng.")
                if mode == "chapter_transition":
                    # Keep the old map inert while the button/scene is fading.
                    # In particular, don't select its cleared boss or click again.
                    identity = self.detector.map_identity(frame) if find("stage_screen") else None
                    new_map = (not find("next_chapter") and identity is not None and
                               not self.detector.same_stage(transition_source, identity))
                    chapter_list = bool(find("chapter_screen") and find("chapter_frontier") and
                                        not find("stage_screen") and not find("next_chapter"))
                    stable_title = (transition_title is not None and identity is not None and
                                    self.detector.same_stage(transition_title, identity))
                    kind = "map" if new_map else "list" if chapter_list else None
                    transition_streak = (transition_streak + 1 if kind and kind == transition_kind and
                                         (chapter_list or stable_title) else 1 if kind else 0)
                    transition_kind = kind
                    transition_title = identity if new_map else None
                    if transition_streak >= 2:
                        self.progress("Đã chuyển chương; tìm ải đầu tiên đang mở trên map mới…")
                        mode, last_action = "navigate", None
                        controls = BattleControls()
                        missing_marker_since, scan_attempts = None, 0
                        returned_to_chapters = chapter_list
                        deadline = self.clock() + self.navigation_timeout
                    else:
                        self.sleeper(.8)
                        continue
                if mode == "retry":
                    dialog, fight = find("stage_dialog"), find("fight")
                    if dialog and fight:
                        identity = self.detector.stage_identity(frame)
                        if identity is None or (stage_identity is not None and
                                not self.detector.same_stage(stage_identity, identity)):
                            return self._finish("retry_unverified", "Chưa xác nhận được đúng tên ải cần đánh lại; đã dừng trước khi bấm Chiến.")
                        stage_identity = identity
                        self._tap(frame, fight)
                        retry_start_pending = True
                        self.progress(f"Bắt đầu trận đánh lại {self.stage_retries + 1}/{spam_limit}; chờ xác nhận vào trận…")
                        mode, last_action = "battle", "fight"
                        controls = BattleControls()
                        deadline = self.clock() + self.battle_timeout
                    elif find("stage_screen"):
                        marker = find("stage_frontier")
                        if marker and last_action != "retry_stage":
                            if not stable_frontier(marker, frame):
                                self.sleeper(.8)
                                continue
                            anchor = (marker.center[0] / frame.shape[1], marker.center[1] / frame.shape[0])
                            if stage_anchor is not None and any(abs(a-b) > .02 for a, b in zip(anchor, stage_anchor)):
                                return self._finish("retry_unverified", "Vị trí ải đang mở đã thay đổi sau trận thua; đã dừng.")
                            stage_anchor = anchor
                            self._tap(frame, marker, marker.height * (145 / 44))
                            clipped_candidate, clipped_streak = None, 0
                            last_action = "retry_stage"
                            retry_start_pending = True
                    elif find("battle_screen") and last_action == "retry_stage" and retry_start_pending:
                        # Native quick combat may bypass the fight dialog after
                        # selecting the verified map target.
                        confirm_retry()
                        controls = BattleControls()
                        deadline = self.clock() + self.battle_timeout
                    elif find("chapter_screen") or find("event_home") or find("battle_screen"):
                        return self._finish("retry_unverified", "Không xác nhận được đường quay lại cùng ải; đã dừng.")
                    # Never scan another chapter or choose a different route on loss.
                    self.sleeper(.8)
                    continue
                if mode == "victory":
                    self.sleeper(.8)
                    continue
                if mode in {"battle", "after_next"} and find("battle_screen"):
                    confirm_retry()
                    error = self._battle_controls(frame, controls)
                    if error:
                        return self._finish("auto_unverified", error)
                    mode = "battle"
                if mode == "battle":
                    # Never retry a stale fight dialog or tap an unknown popup.
                    self.sleeper(.8)
                    continue
                dialog, fight = find("stage_dialog"), find("fight")
                intro, intro_dismiss = find("event_intro"), find("intro_dismiss")
                event_home = find("event_home")
                stage_screen = find("stage_screen")
                chapter_screen = find("chapter_screen")
                chapter_button = find("next_chapter") if stage_screen else None
                action, target, dy = None, None, 0
                chapter_button_streak = chapter_button_streak + 1 if chapter_button else 0
                if chapter_button:
                    if chapter_button_streak < 2:
                        self.sleeper(.8)
                        continue
                    transition_source = self.detector.map_identity(frame)
                    if transition_source is None:
                        return self._finish("unknown", "Có nút Chương kế nhưng chưa xác nhận được tên map hiện tại; đã dừng.")
                    self.progress("Đã hoàn thành map; bấm Chương kế…")
                    self._tap(frame, chapter_button)
                    mode, last_action = "chapter_transition", "next_chapter"
                    transition_title, transition_streak, chapter_button_streak = None, 0, 0
                    transition_kind = None
                    stage_identity = stage_anchor = None
                    self.stage_retries = 0
                    retry_start_pending = False
                    deadline = self.clock() + self.navigation_timeout
                    self.sleeper(.8)
                    continue
                if intro and intro_dismiss:
                    action, target = "intro", intro_dismiss
                elif dialog and fight:
                    action, target = "fight", fight
                elif stage_screen:
                    target = find("stage_frontier")
                    if target:
                        if not stable_frontier(target, frame):
                            self.sleeper(.8)
                            continue
                        action = "stage"
                        dy = target.height * (145 / 44)
                        missing_marker_since, scan_attempts = None, 0
                    else:
                        clipped_candidate, clipped_streak = None, 0
                        if missing_marker_since is None:
                            missing_marker_since = self.clock()
                        if self.clock() - missing_marker_since >= 3:
                            self._check_stop()
                            self._save_scan(scan_attempts)
                            if scan_attempts < len(MAP_SCAN_DIRECTIONS):
                                direction = MAP_SCAN_DIRECTIONS[scan_attempts]
                                label = "phần cuối" if direction == "later" else "phần đầu"
                                self.progress(f"Chưa thấy dấu ải; quét lại {label} map ({scan_attempts+1}/{len(MAP_SCAN_DIRECTIONS)})…")
                                start, end = (1500, 450) if direction == "later" else (450, 1500)
                                self.device.swipe(start, 650, end, 650, self.frame_size)
                                scan_attempts += 1
                                missing_marker_since = self.clock()
                                deadline = self.clock() + self.navigation_timeout
                            else:
                                return self._finish("no_frontier", "Đã chờ và quét hai chiều nhưng chưa xác nhận được dấu ải đang mở. Giữ nguyên map; ảnh từng vùng ở runtime/dungeon_scan.")
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
                    clipped_candidate, clipped_streak = None, 0
                    last_action = action
                    if action == "fight":
                        stage_identity = self.detector.stage_identity(frame) if spam else None
                        mode = "battle"
                        controls = BattleControls()
                        deadline = self.clock() + self.battle_timeout
                    else:
                        if action == "stage" and spam:
                            stage_anchor = (target.center[0] / frame.shape[1], target.center[1] / frame.shape[0])
                        mode = "navigate"
                        deadline = self.clock() + self.navigation_timeout
                self.sleeper(.8)
        except InterruptedError:
            return self._finish("cancelled", "Đã dừng theo yêu cầu.")
        except Exception as exc:
            return self._finish("error", f"Lỗi chạy phó bản: {exc}")
