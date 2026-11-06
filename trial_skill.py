"""Daily Phi Thăng and Ma Động trials from the ordinary lobby."""
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from chest_skill import ChestDetector
from daily_tasks_skill import DailyTasksSkill, ROOT
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector
from login_engine import SIZE

TRIALS = {"phi": "Thí Luyện Phi Thăng", "ma": "Thí Luyện Ma Động"}
SLOTS = {"left": (560, 486), "right": (1354, 486), "top": (965, 294)}
SLOT_LABELS = {"left": "dưới trái", "right": "dưới phải", "top": "phía trên", "boss": "boss"}
MAX_SCROLLS = 16


@dataclass(frozen=True)
class Board:
    floor: int
    lives: int
    defeated: tuple[str, ...]
    targets: tuple[tuple[str, tuple[float, float]], ...]


class TrialDetector(DungeonDetector):
    REGIONS = {
        "lobby_challenge": (.78, .89, .96, 1),
        "lobby_anchor": (.23, .89, .48, 1),
        "challenge_title": (0, 0, .30, .12),
        "challenge_back": (0, 0, .20, .12),
        "card_ma": (0, .66, 1, .80),
        "card_phi": (0, .66, 1, .80),
        "title_ma": (0, 0, .36, .12),
        "title_phi": (0, 0, .36, .12),
        "lives": (0, .28, .22, .39),
        "dialog": (.23, .63, .43, .74),
        "fight": (.45, .71, .76, .90),
        "skip_label": (.28, .73, .53, .87),
        "skip_on": (.27, .73, .41, .87),
        "win": (.32, .02, .72, .25),
        "loss": (.20, .02, .80, .64),
        "dead": (.16, .41, .86, .76),
        "boss_ma": (.40, .13, .57, .23),
        "boss_phi": (.45, .13, .65, .23),
        "boss_sealed": (.35, .40, .68, .58),
    }

    def __init__(self):
        super().__init__(ROOT/"assets/trial")
        self.digits = EquipmentDetector().digits
        self.stamps = []
        for path in (ROOT/"assets/trial").glob("dead*.png"):
            sample = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            if sample is not None:
                mask = self._red(sample)
                self.stamps.extend(cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
                                   for scale in (.85, .9, .95, 1., 1.05, 1.1, 1.15))

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and bool(self.stamps) and set(self.digits) == set(range(10))

    @staticmethod
    def _cyan(crop):
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        return cv2.inRange(hsv, (87, 130, 105), (112, 255, 255))

    @staticmethod
    def _red(crop):
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        return cv2.inRange(hsv, (0, 140, 145), (12, 255, 255)) | cv2.inRange(
            hsv, (170, 140, 145), (179, 255, 255))

    @staticmethod
    def _point(frame, x, y):
        h, w = frame.shape[:2]
        scale = h/1080
        return round(w/2+(x-960)*scale), round(y*scale)

    def _crop(self, frame, x1, y1, x2, y2):
        left, top = self._point(frame, x1, y1)
        right, bottom = self._point(frame, x2, y2)
        return frame[top:bottom, left:right]

    def _floor(self, frame):
        gauge = self._cyan(self._crop(frame, 480, 1000, 1450, 1013))
        filled = np.flatnonzero((gauge > 0).mean(axis=0) > .45)
        if filled.size == 0 or filled[0] > gauge.shape[1]*.07:
            return None
        progress = filled[-1]/gauge.shape[1]
        for floor, threshold in ((4, .76), (3, .50), (2, .27), (1, .06)):
            if progress >= threshold:
                return floor
        return None

    def _lives(self, frame):
        label = self.find(frame, "lives", .91)
        if not label:
            return None
        right = label.x+label.width
        crop = frame[label.y:label.y+label.height,
                     right+round(.35*label.width):right+round(.70*label.width)]
        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 140, 255)
        return ChestDetector._read_mask(mask, round(label.height*.47), self.digits)

    def _slot_defeated(self, frame, x, y):
        crop = self._crop(frame, x-122, y+140, x+122, y+312)
        return self._dead_stamp(crop)

    def _dead_stamp(self, crop):
        mask = self._red(crop)
        for template in self.stamps:
            h, w = template.shape
            if h > mask.shape[0] or w > mask.shape[1]:
                continue
            _, score, _, _ = cv2.minMaxLoc(cv2.matchTemplate(mask, template, cv2.TM_CCORR_NORMED))
            if score >= .78:
                return True
        return False

    def board(self, frame):
        floor, lives = self._floor(frame), self._lives(frame)
        if floor is None or lives is None:
            return None
        defeated, targets = [], []
        for slot, (x, y) in SLOTS.items():
            if self._slot_defeated(frame, x, y):
                defeated.append(slot)
            else:
                bar = self._cyan(self._crop(frame, x-86, y-15, x+86, y+15))
                # Damage persists after a loss, so the blue fill can be just a sliver.
                leading_edge = bar[:, :max(1, round(bar.shape[1]*.10))]
                if (bar > 0).mean() >= .045 or (leading_edge > 0).mean() >= .12:
                    targets.append((slot, self._point(frame, x, y+225)))
        if floor == 4:
            # A single wide pink HP bar replaces all three blue NPC bars.
            defeated, targets = [], []
            if self.find(frame, "boss_sealed", .92):
                defeated = ["boss"]
            elif boss := self.find(frame, "boss_ma", .90) or self.find(frame, "boss_phi", .90):
                scale = frame.shape[0]/1080
                x, _ = boss.center
                left = x-round(212*scale)
                crop = frame[round(247*scale):round(274*scale), left:left+round(100*scale)]
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                pink = cv2.inRange(hsv, (142, 155, 150), (176, 255, 255))
                if (pink > 0).mean() >= .025:
                    targets = [("boss", (x, round(570*scale)))]
        return Board(floor, lives, tuple(defeated), tuple(targets))

    def skip(self, frame):
        label = self.find(frame, "skip_label", .91)
        if not label:
            return None, None
        x, y = label.center
        center = (label.x-round(label.width*.115), y)
        tick = self.find(frame, "skip_on", .90)
        if tick:
            return True, tick.center
        crop = frame[y-10:y+10, center[0]-10:center[0]+10]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 125, 140), (87, 255, 255))
        if not np.any(green) and hsv[:, :, 2].mean() < 90:
            return False, center
        return None, None


class TrialSkill(DailyTasksSkill):
    def __init__(self, device, **kwargs):
        super().__init__(device, detector=kwargs.pop("detector", None) or TrialDetector(), **kwargs)

    def _tap_point(self, frame, point, action):
        h, w = frame.shape[:2]
        self._check()
        self.device.tap(round(point[0]*SIZE[0]/w), round(point[1]*SIZE[1]/h), self.frame_size)
        self.actions.append(action)

    def _scroll(self):
        self._check()
        self.device.swipe(1640, 540, 220, 540, self.frame_size, 580)
        self.actions.append("scroll_right")

    def _next(self, frame, kind, selected, pending, result, scrolls):
        d = self.detector
        if pending:
            win = d.find(frame, "win", .91)
            loss = d.find(frame, "loss", .91) if not win else None
            if win or loss:
                outcome = "win" if win else "loss"
                return "dismiss_result", self._empty_result_space(frame, (.50, .974)).center, outcome
        if selected and not pending and d.find(frame, "dialog", .91):
            checked, point = d.skip(frame)
            if checked is False:
                return "enable_skip", point, None
            if checked and (fight := d.find(frame, "fight", .92)):
                return "fight", fight.center, None
        if d.find(frame, f"title_{kind}", .92):
            board = d.board(frame)
            if board is None:
                return None
            if pending:
                old_floor, old_lives, slot = selected
                if board.lives == old_lives-1 and result != "win":
                    return "confirmed_loss", None, None
                if board.lives == old_lives and (board.floor > old_floor or slot in board.defeated):
                    return "confirmed_win", None, slot
                return None
            if board.defeated == ("boss",):
                return "complete", None, None
            if board.lives == 0:
                return "no_lives", None, None
            if selected:
                return None
            targets = dict(board.targets)
            order = ("boss",) if "boss" in targets else SLOTS
            for slot in order:
                if slot not in board.defeated:
                    if slot in targets:
                        return "select_npc", targets[slot], (board.floor, board.lives, slot)
                    break
            return None
        if selected:
            return None
        other = "ma" if kind == "phi" else "phi"
        if d.find(frame, f"title_{other}", .92) and (back := d.find(frame, "challenge_back", .92)):
            return "back_to_challenge", back.center, None
        if d.find(frame, "challenge_title", .93):
            phi, ma = d.find(frame, "card_phi", .92), d.find(frame, "card_ma", .92)
            if phi and ma:
                return "enter_trial", (phi if kind == "phi" else ma).center, None
            if scrolls < MAX_SCROLLS:
                return "scroll_right", None, None
            return "card_missing", None, None
        if d.find(frame, "lobby_anchor", .92) and (entry := d.find(frame, "lobby_challenge", .92)):
            return "open_challenge", entry.center, None
        return None

    def run_trial(self, *, kind):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        title = TRIALS[kind]
        selected = previous = result = None
        pending = False
        wins = losses = scrolls = dismissals = 0
        skip_enabled = False
        try:
            if not self.detector.ready:
                return self._finish("needs_samples", f"Thiếu ảnh nhận diện {title}.")
            deadline = self.clock()+self.timeout
            while self.clock() < deadline:
                frame = self._observe()
                step = self._next(frame, kind, selected, pending, result, scrolls)
                key = (step[0], step[2]) if step else None
                if key and key == previous:
                    action, point, detail = step
                    if action == "no_lives":
                        return self._finish("blocked", f"{title}: hết lượt còn lại. Đã thắng {wins}, thua {losses} trận.")
                    if action == "complete":
                        return self._finish("completed", f"{title}: đã hoàn thành. Thắng {wins}, thua {losses} trận.")
                    if action == "card_missing":
                        return self._finish("blocked", f"Chưa tìm thấy hai thẻ Thí Luyện ở cuối danh sách Khiêu Chiến.")
                    if action == "scroll_right":
                        self._scroll()
                        scrolls += 1
                    elif action == "confirmed_win":
                        wins += 1
                        if detail == "boss":
                            return self._finish("completed", f"{title}: đã hạ boss. Thắng {wins}, thua {losses} trận.")
                        selected, pending = None, False
                    elif action == "confirmed_loss":
                        losses += 1
                        selected, pending = None, False
                    else:
                        if action == "dismiss_result" and dismissals >= 3:
                            return self._finish("blocked", f"{title}: bảng kết quả vẫn mở sau 3 lần chạm.")
                        if action == "enable_skip" and skip_enabled:
                            return self._finish("blocked", f"{title}: chưa xác nhận được Bỏ qua chiến đấu.")
                        if action in {"open_challenge", "enter_trial", "back_to_challenge"} and action in self.actions:
                            return self._finish("blocked", f"{title}: màn hình không đổi sau khi điều hướng.")
                        self._tap_point(frame, point, action)
                        if action == "select_npc":
                            selected = detail
                            skip_enabled = False
                            self.progress(f"{title}: tầng {selected[0]}, mục tiêu {SLOT_LABELS[selected[2]]}.")
                        elif action == "fight":
                            pending, result, dismissals = True, None, 0
                        elif action == "enable_skip":
                            skip_enabled = True
                        elif action == "dismiss_result":
                            result, dismissals = detail, dismissals+1
                    deadline = self.clock()+self.timeout
                    key = None
                previous = key
                self.sleeper(.8)
            state = "kết quả và thay đổi trên bảng" if pending else "hộp Chiến" if selected else "tầng, số lượt hoặc NPC tiếp theo"
            return self._finish("blocked", f"{title}: chưa xác nhận được {state}. Đã thắng {wins}, thua {losses} trận.")
        except InterruptedError:
            return self._finish("cancelled", f"Đã dừng {title}.")
        except Exception as exc:
            return self._finish("error", f"Lỗi khi chạy {title}: {exc}")
