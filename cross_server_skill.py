"""Daily quick duels in Liên Server."""
import uuid

import cv2
import numpy as np

from chest_skill import ChestDetector
from daily_tasks_skill import DailyTasksSkill, ROOT
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector
from login_engine import SIZE

MAX_DAILY_ATTEMPTS = 20


class CrossServerDetector(DungeonDetector):
    REGIONS = {
        "title": (0, 0, .32, .12),
        "attempts_label": (0, .23, .15, .34),
        "wins_label": (.19, .76, .37, .85),
        "quick": (.22, .82, .47, .96),
        "refresh": (.43, .82, .67, .96),
        "skip_label": (.62, .85, .87, .96),
        "skip_on": (.60, .85, .74, .96),
        "purchase_title": (.34, .09, .67, .22),
        "purchase_cancel": (.25, .68, .49, .86),
        "lobby_challenge": (.78, .89, .96, 1),
        "lobby_anchor": (.23, .89, .48, 1),
        "challenge_title": (0, 0, .30, .12),
        "card": (.02, .66, .98, .80),
        "win": (.32, .02, .72, .25),
        "loss": (.20, .02, .80, .64),
    }

    def __init__(self):
        super().__init__(ROOT/"assets/cross_server")
        self.digits = EquipmentDetector().digits

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and set(self.digits) == set(range(10))

    def _number(self, frame, name, gap, width):
        marker = self.find(frame, name, .92)
        if not marker:
            return None
        x = marker.x + marker.width
        crop = frame[marker.y:marker.y+marker.height,
                     x+round(marker.width*gap):x+round(marker.width*(gap+width))]
        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 145, 255)
        return ChestDetector._read_mask(mask, round(marker.height*.45), self.digits)

    def counters(self, frame):
        return (self._number(frame, "attempts_label", .45, .71),
                self._number(frame, "wins_label", .20, .65))

    def skip(self, frame):
        label = self.find(frame, "skip_label", .91)
        if not label:
            return None, None
        marker = self.find(frame, "skip_on", .90)
        if marker:
            x, y = marker.center
            crop = frame[marker.y:marker.y+marker.height, marker.x:marker.x+marker.width]
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            if (cv2.inRange(hsv, (35, 140, 140), (88, 255, 255)) > 0).mean() >= .12:
                return True, (x, y)
        scale = label.width/186
        x, y = label.x-round(21*scale), label.center[1]
        radius = max(2, round(15*scale))
        crop = frame[y-radius:y+radius, x-radius:x+radius]
        if cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 2].mean() < 95:
            return False, (x, y)
        return None, None

    @staticmethod
    def opponents(frame):
        height, width = frame.shape[:2]
        boxes = ((.15, .72, .24, .76), (.48, .625, .56, .662), (.83, .724, .92, .763))
        strips = []
        for x1, y1, x2, y2 in boxes:
            crop = frame[round(y1*height):round(y2*height), round(x1*width):round(x2*width)]
            white = cv2.inRange(crop, (155, 155, 155), (255, 255, 255))
            strips.append(cv2.resize(white, (100, 28), interpolation=cv2.INTER_NEAREST))
        return np.concatenate(strips, axis=1)


class CrossServerSkill(DailyTasksSkill):
    def __init__(self, device, **kwargs):
        super().__init__(device, detector=kwargs.pop("detector", None) or CrossServerDetector(), **kwargs)

    def _tap_point(self, frame, point, action):
        self._check()
        self.device.tap(round(point[0]*SIZE[0]/frame.shape[1]),
                        round(point[1]*SIZE[1]/frame.shape[0]), self.frame_size)
        self.actions.append(action)

    def run_duels(self):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        pending = previous = settled = None
        settled_at = 0.
        need_refresh = False
        used = wins = losses = 0
        scrolls = still = 0
        direction = -1
        menu_before = None
        outcome = None
        dismissals = 0
        try:
            self._check()
            if not self.detector.ready:
                return self._finish("needs_samples", "Thiếu ảnh nhận diện Tỉ Võ Liên Server.")
            deadline = self.clock()+self.timeout
            while self.clock() < deadline:
                frame = self._observe()
                d = self.detector
                action = point = detail = None
                if d.find(frame, "purchase_title", .93):
                    cancel = d.find(frame, "purchase_cancel", .93)
                    if cancel and "cancel_purchase" not in self.actions:
                        action, point = "cancel_purchase", cancel.center
                elif pending and pending[0] == "quick" and (
                        (win := d.find(frame, "win", .91)) or d.find(frame, "loss", .91)):
                    action, point = "dismiss_result", self._empty_result_space(frame, (.50, .974)).center
                    detail = "win" if win else "loss"
                elif d.find(frame, "title", .93):
                    remaining, current_wins = d.counters(frame)
                    if remaining is not None and current_wins is not None:
                        if remaining > MAX_DAILY_ATTEMPTS:
                            return self._finish("blocked", "Tỉ Võ Nhanh có thể chạy hàng loạt; số lượt hiện tại vượt giới hạn 20.")
                        if pending and pending[0] == "quick":
                            _, old_remaining, old_wins = pending
                            counts = remaining, current_wins
                            if counts != settled:
                                settled, settled_at = counts, self.clock()
                            if remaining < old_remaining and self.clock()-settled_at >= 1.5:
                                consumed = old_remaining-remaining
                                gained = current_wins-old_wins
                                if not 0 <= gained <= consumed:
                                    return self._finish("blocked", "Bộ đếm thắng và lượt Tỉ Võ không khớp; đã dừng để kiểm tra.")
                                used, wins, losses = used+consumed, wins+gained, losses+consumed-gained
                                need_refresh = outcome == "loss" or gained < consumed
                                pending = None
                                previous = None
                                self.progress(f"Liên Server: đã dùng {used} lượt, còn {remaining}; thắng {wins}, thua {losses}.")
                        if not pending and remaining == 0:
                            action = "complete"
                        elif pending and pending[0] == "refresh":
                            if remaining == pending[1]:
                                difference = np.mean(d.opponents(frame) != pending[2])
                                if difference >= .045:
                                    action = "refresh_confirmed"
                        elif not pending and remaining > 0:
                            skip, point = d.skip(frame)
                            if skip is False and "enable_skip" not in self.actions:
                                action = "enable_skip"
                            elif skip:
                                button = d.find(frame, "refresh" if need_refresh else "quick", .93)
                                if button:
                                    action, point = ("refresh" if need_refresh else "quick"), button.center
                                    detail = remaining, current_wins
                elif not pending and d.find(frame, "challenge_title", .93):
                    card = d.find(frame, "card", .93)
                    if card:
                        action, point = "enter_cross_server", card.center
                    elif scrolls < 32:
                        action = "scroll_menu"
                    else:
                        return self._finish("blocked", "Chưa tìm thấy thẻ Liên Server trong Khiêu Chiến.")
                elif not pending and d.find(frame, "lobby_anchor", .92):
                    entry = d.find(frame, "lobby_challenge", .92)
                    if entry:
                        action, point = "open_challenge", entry.center

                key = (action, detail) if action else None
                if key and key == previous:
                    if action == "complete":
                        return self._finish("completed", f"Liên Server đã hết lượt. Lần chạy này dùng {used} lượt: thắng {wins}, thua {losses}.")
                    if action == "refresh_confirmed":
                        pending, need_refresh = None, False
                    elif action == "scroll_menu":
                        strip = frame[round(frame.shape[0]*.69):round(frame.shape[0]*.77)]
                        if menu_before is not None and strip.shape == menu_before.shape:
                            still = still+1 if np.mean(cv2.absdiff(strip, menu_before)) < 3 else 0
                        menu_before = strip.copy()
                        if still >= 2:
                            if direction == 1:
                                return self._finish("blocked", "Đã quét hai phía nhưng chưa tìm thấy thẻ Liên Server.")
                            direction, still = 1, 0
                        self._check()
                        start, end = (1530, 340) if direction == -1 else (340, 1530)
                        self.device.swipe(start, 540, end, 540, self.frame_size, 580)
                        scrolls += 1
                        self.actions.append("scroll_menu")
                    else:
                        if action in {"open_challenge", "enter_cross_server"} and action in self.actions:
                            return self._finish("blocked", "Màn hình không đổi sau thao tác mở Liên Server.")
                        if action == "dismiss_result" and dismissals >= 3:
                            return self._finish("blocked", "Bảng kết quả Tỉ Võ chưa đóng sau 3 lần chạm.")
                        opponents_before = d.opponents(frame) if action == "refresh" else None
                        self._tap_point(frame, point, action)
                        if action == "quick":
                            pending = ("quick", *detail)
                            settled, outcome, dismissals = None, None, 0
                            self.progress(f"Tỉ Võ Nhanh, chờ kết quả; còn {detail[0]} lượt.")
                        elif action == "refresh":
                            pending = ("refresh", detail[0], opponents_before)
                            self.progress("Đã thua; làm mới đối thủ trước lượt Tỉ Võ tiếp theo.")
                        elif action == "dismiss_result":
                            outcome, dismissals = detail, dismissals+1
                    deadline = self.clock()+self.timeout
                    key = None
                previous = key
                self.sleeper(.8)
            reason = "kết quả và bộ đếm lượt" if pending else "màn Liên Server hoặc bộ đếm lượt"
            return self._finish("blocked", f"Chưa xác nhận được {reason}. Đã dùng {used} lượt trong lần chạy này.")
        except InterruptedError:
            return self._finish("cancelled", "Đã dừng Tỉ Võ Liên Server.")
        except Exception as exc:
            return self._finish("error", f"Lỗi Tỉ Võ Liên Server: {exc}")
