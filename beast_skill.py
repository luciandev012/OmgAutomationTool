"""Finish the current Thần Thú Động round, reset once for free, then stop."""
import uuid

import cv2
import numpy as np

from chest_skill import ChestDetector
from cross_server_skill import CrossServerDetector, CrossServerSkill
from daily_tasks_skill import DailyTasksSkill, ROOT
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector
from login_engine import SIZE


class BeastDetector(CrossServerDetector):
    REGIONS = {
        "lobby_challenge": (.78, .89, .96, 1),
        "lobby_anchor": (.23, .89, .48, 1),
        "challenge_title": (0, 0, .30, .12),
        "card": (.02, .66, .98, .80),
        "title": (0, 0, .32, .11),
        "attempts_label": (0, .25, .17, .35),
        "quick": (0, .33, .18, .44),
        "reset": (.76, .86, 1, .97),
        "reset_label": (.75, .95, 1, 1),
        "config_title": (.37, .04, .64, .15),
        "route_label": (.30, .22, .42, .32),
        "top_on": (.25, .20, .37, .33),
        "count_minus": (.31, .48, .42, .61),
        "count_plus": (.57, .48, .69, .61),
        "config_ok": (.49, .65, .70, .78),
        "warning": (.27, .33, .73, .45),
        "warning_ok": (.49, .60, .70, .73),
        "log_title": (.37, 0, .64, .10),
        "log_stop": (.36, .81, .65, .94),
        "log_done": (.36, .81, .65, .94),
    }

    def __init__(self):
        DungeonDetector.__init__(self, ROOT/"assets/beast")
        self.digits = EquipmentDetector().digits
        for path in (ROOT/"assets/beast/digits").glob("digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
            self.digits[int(path.stem.split("_")[1])].append(glyph > 127)

    def attempts(self, frame):
        return self._number(frame, "attempts_label", .21, .30)

    def free_resets(self, frame):
        return self._number(frame, "reset_label", .01, .23)

    def sweep_options(self, frame):
        minus = self.find(frame, "count_minus", .93)
        plus = self.find(frame, "count_plus", .93)
        label = self.find(frame, "route_label", .92)
        if not (minus and plus and label):
            return None
        x = round((minus.center[0]+plus.center[0])/2)
        y = minus.center[1]
        scale = minus.width/88
        radius = round(25*scale)
        crop = frame[y-round(30*scale):y+round(30*scale), x-radius:x+radius]
        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 145, 255)
        quantity = ChestDetector._read_mask(mask, round(22*scale), self.digits)
        selected = self.find(frame, "top_on", .90)
        if selected:
            hsv = cv2.cvtColor(frame[selected.y:selected.y+selected.height,
                                    selected.x:selected.x+selected.width], cv2.COLOR_BGR2HSV)
            checked = (cv2.inRange(hsv, (35, 140, 140), (87, 255, 255)) > 0).mean() > .12
        else:
            checked = False
        return quantity, checked, (label.x-round(label.width*62/65), label.center[1]), minus.center


class BeastSkill(CrossServerSkill):
    def __init__(self, device, **kwargs):
        DailyTasksSkill.__init__(self, device, detector=kwargs.pop("detector", None) or BeastDetector(), **kwargs)

    def run_beast(self):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        previous = pending = None
        configured = False
        last_attempts = None
        used = 0
        reset_before = None
        scrolls = still = 0
        direction = -1
        menu_before = None
        sweep_since = None
        try:
            self._check()
            if not self.detector.ready:
                return self._finish("needs_samples", "Thiếu ảnh nhận diện Thần Thú Động.")
            deadline = self.clock()+self.timeout
            while self.clock() < deadline:
                frame = self._observe()
                d = self.detector
                action = point = detail = None
                if d.find(frame, "warning", .93):
                    if configured and (button := d.find(frame, "warning_ok", .93)):
                        action, point = "confirm_free_chest_sweep", button.center
                elif d.find(frame, "config_title", .93):
                    options = d.sweep_options(frame)
                    if options:
                        quantity, top, top_point, minus_point = options
                        if quantity is None or quantity < 1:
                            return self._finish("blocked", "Chưa xác nhận số lần mở rương là 1; kiểm tra cấu hình Càn Quét.")
                        if quantity > 1:
                            action, point = "reduce_chest_quantity", minus_point
                        elif not top:
                            action, point = "select_top_route", top_point
                        elif button := d.find(frame, "config_ok", .93):
                            action, point = "start_sweep", button.center
                elif d.find(frame, "log_title", .93):
                    if sweep_since is None:
                        sweep_since = self.clock()
                    if button := d.find(frame, "log_done", .94):
                        action, point = "close_sweep_log", button.center
                    elif d.find(frame, "log_stop", .94) and self.clock()-sweep_since < 180:
                        deadline = self.clock()+self.timeout
                    elif self.clock()-sweep_since >= 180:
                        return self._finish("blocked", "Càn Quét Thần Thú Động chưa kết thúc sau 3 phút.")
                elif d.find(frame, "title", .93):
                    remaining, resets = d.attempts(frame), d.free_resets(frame)
                    if remaining is not None and 0 <= remaining <= 16:
                        if reset_before is not None:
                            if remaining == 16 and resets == reset_before-1:
                                action = "reset_finished"
                        else:
                            if pending == "sweep":
                                if last_attempts is not None and remaining < last_attempts:
                                    used += last_attempts-remaining
                                    pending, configured = None, False
                            if remaining == 0 and pending is None:
                                if resets == 0:
                                    action = "finished_without_reset"
                                elif resets == 1 and (button := d.find(frame, "reset", .94)):
                                    action, point, detail = "free_reset", button.center, resets
                            elif pending is None and (button := d.find(frame, "quick", .93)):
                                action, point, detail = "open_sweep", button.center, remaining
                elif not pending and reset_before is None and d.find(frame, "challenge_title", .93):
                    if card := d.find(frame, "card", .93):
                        action, point = "enter_beast", card.center
                    elif scrolls < 32:
                        action = "scroll_menu"
                elif not pending and reset_before is None and d.find(frame, "lobby_anchor", .92):
                    if entry := d.find(frame, "lobby_challenge", .92):
                        action, point = "open_challenge", entry.center

                key = (action, detail) if action else None
                if key and key == previous:
                    if action == "reset_finished":
                        return self._finish("completed", f"Thần Thú Động: đã dùng {used} lượt, làm mới miễn phí và dừng ở vòng mới.")
                    if action == "finished_without_reset":
                        return self._finish("completed", "Thần Thú Động đã hết lượt và đã dùng lần làm mới miễn phí hôm nay.")
                    if action == "scroll_menu":
                        strip = frame[round(frame.shape[0]*.69):round(frame.shape[0]*.77)]
                        if menu_before is not None and strip.shape == menu_before.shape:
                            still = still+1 if np.mean(cv2.absdiff(strip, menu_before)) < 3 else 0
                        menu_before = strip.copy()
                        if still >= 2:
                            if direction == 1:
                                return self._finish("blocked", "Đã quét hai phía nhưng chưa thấy thẻ Thần Thú Động.")
                            direction, still = 1, 0
                        self._check()
                        start, end = (1530, 340) if direction == -1 else (340, 1530)
                        self.device.swipe(start, 540, end, 540, self.frame_size, 580)
                        self.actions.append(action)
                        scrolls += 1
                    else:
                        if action in {"start_sweep", "confirm_free_chest_sweep", "close_sweep_log", "free_reset", "open_sweep"} and action == pending:
                            return self._finish("blocked", f"Thần Thú Động chưa chuyển màn sau thao tác {action}.")
                        self._tap_point(frame, point, action)
                        if action == "open_sweep":
                            last_attempts, pending = detail, action
                        elif action == "start_sweep":
                            configured, pending = True, action
                        elif action == "confirm_free_chest_sweep":
                            pending = action
                        elif action == "close_sweep_log":
                            pending, sweep_since = "sweep", None
                        elif action == "free_reset":
                            reset_before = detail
                        self.progress(f"Thần Thú Động: {action}.")
                    deadline = self.clock()+self.timeout
                    key = None
                previous = key
                self.sleeper(.8)
            return self._finish("blocked", "Thần Thú Động chưa xác nhận được bước tiếp theo; đã lưu ảnh màn hình.")
        except InterruptedError:
            self._stop_game_sweep()
            return self._finish("cancelled", "Đã dừng Thần Thú Động.")
        except Exception as exc:
            return self._finish("error", f"Lỗi Thần Thú Động: {exc}")

    def _stop_game_sweep(self):
        """The in-game batch keeps running, so Stop must also cancel that batch."""
        try:
            png = self.device.capture()
            frame = self.detector.decode(png)
            if self.detector.find(frame, "log_title", .93) and not self.detector.find(frame, "log_done", .94):
                if button := self.detector.find(frame, "log_stop", .94):
                    raw = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
                    x, y = button.center
                    self.device.tap(round(x*SIZE[0]/frame.shape[1]), round(y*SIZE[1]/frame.shape[0]),
                                    (raw.shape[1], raw.shape[0]))
                    self.actions.append("stop_game_sweep")
        except Exception:
            self.progress("Chưa xác nhận dừng càn quét trong game; kiểm tra MuMu.")
