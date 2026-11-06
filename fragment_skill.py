"""Daily quick map sweep for Điển Vi fragments from the ordinary hero bag."""
import uuid

import cv2
import numpy as np

from chest_skill import ChestDetector
from daily_tasks_skill import DailyTasksDetector, DailyTasksSkill, ROOT
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector
from login_engine import Match, SIZE

OPTIONS = ("stamina", "war", "elite")
OPTION_NAMES = {"stamina": "tự dùng Thể Lực Đơn", "war": "tự dùng Chiến Lệnh", "elite": "quét kèm Tinh Anh"}
SWEEP_TIMEOUT = 300


class FragmentDetector(DungeonDetector):
    REGIONS = {
        "entry": (.04, .88, .22, 1), "title": (.08, 0, .22, .10),
        "back": (0, 0, .10, .10), "fragments_tab": (.23, .87, .42, .96),
        "fragments_active": (.23, .87, .42, .96), "receive_many": (.71, .94, .85, 1),
        "selected_label": (.12, .77, .27, .86), "quick": (.76, .76, .93, .86),
        "dien_vi": (.20, .13, .75, .69),
        "checkbox_on": (.32, .13, .93, .76), "checkbox_off": (.32, .13, .93, .76),
        "config_title": (.40, .16, .60, .25),
        "stamina": (.37, .36, .66, .46), "war": (.37, .45, .73, .55),
        "elite": (.37, .54, .67, .64),
        "ok": (.52, .66, .68, .77), "cancel": (.31, .66, .47, .77),
        "log_title": (.25, 0, .75, .20),
        "log_stop": (.20, .73, .80, .96), "log_done": (.20, .73, .80, .96),
    }

    def __init__(self):
        super().__init__(ROOT/"assets/fragment")
        self.lobby = DailyTasksDetector()
        self.digits = EquipmentDetector().digits
        for path in (ROOT/"assets/fragment/digits").glob("digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 0)
            self.digits[int(path.stem.split("_")[1])].append(glyph > 127)
        self._raw = self._frame = None

    def decode(self, png):
        self._frame = super().decode(png)
        self._raw = cv2.imdecode(np.frombuffer(png, np.uint8), 1)
        return self._frame

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and self.lobby.ready

    def _in(self, frame, name, box, threshold=.93, dim=False):
        x1, y1, x2, y2 = map(round, box)
        x1, y1 = max(0, x1), max(0, y1)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        best = None
        for template, _ in self.scaled[name]:
            h, w = template.shape
            if h > gray.shape[0] or w > gray.shape[1]:
                continue
            _, score, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))
            if score >= threshold and (not best or score > best.score):
                if dim or gray[y:y+h, x:x+w].mean() >= template.mean()*.78:
                    best = Match(name, x1+x, y1+y, w, h, score)
        return best

    def screen(self, frame):
        if self.find(frame, "config_title", .94) and self.find(frame, "cancel", .94):
            return "config"
        h, w = frame.shape[:2]
        if (self.find(frame, "log_title", .94) and
                self._in(frame, "title", (w*.08, 0, w*.22, h*.10), dim=True) and
                self._in(frame, "selected_label", (w*.12, h*.77, w*.27, h*.86), dim=True) and
                self._in(frame, "quick", (w*.76, h*.76, w*.93, h*.86), dim=True)):
            if self.find(frame, "log_done", .94):
                return "done"
            if self.find(frame, "log_stop", .94):
                return "running"
        if self.find(frame, "selected_label", .94) and self.find(frame, "quick", .94):
            return "selection"
        if self.find(frame, "title", .94) and self.find(frame, "fragments_tab", .91):
            return "fragments" if self.find(frame, "receive_many", .93) else "heroes"
        if self.lobby.main_lobby(frame):
            return "lobby"
        return None

    def selected_count(self, frame):
        label = self.find(frame, "selected_label", .94)
        if not label:
            return None
        h, w = frame.shape[:2]
        raw = self._raw if frame is self._frame else frame
        rh, rw = raw.shape[:2]
        left = (label.x+label.width*1.53)*rw/w
        right = (label.x+label.width*2.25)*rw/w
        top, bottom = label.y*rh/h, (label.y+label.height)*rh/h
        crop = raw[round(top):round(bottom), round(left):round(right)]
        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 145, 255)
        return ChestDetector._read_mask(mask, rh*.018, self.digits)

    def checkbox(self, frame, box):
        candidates = [self._in(frame, name, box, .91) for name in ("checkbox_on", "checkbox_off")]
        candidates = [marker for marker in candidates if marker]
        if not candidates:
            return None
        marker = max(candidates, key=lambda item: item.score)
        crop = frame[marker.y:marker.y+marker.height, marker.x:marker.x+marker.width]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        green = float((cv2.inRange(hsv, (35, 140, 140), (88, 255, 255)) > 0).mean())
        if green >= .10:
            return True, marker.center
        if green < .025:
            return False, marker.center
        return None

    def target(self, frame):
        name = self.find(frame, "dien_vi", .94)
        if not name:
            return None
        h, w = frame.shape[:2]
        right = w*.94 if name.center[0] > w*.5 else w*.52
        return self.checkbox(frame, (name.x+name.width, name.y, right, min(h*.765, name.y+h*.14)))

    def options(self, frame):
        if self.screen(frame) != "config":
            return None
        h, w = frame.shape[:2]
        result = []
        for name in OPTIONS:
            label = self.find(frame, name, .94)
            if not label:
                return None
            value = self.checkbox(frame, (label.x-w*.07, label.y-h*.035,
                                           label.x-w*.008, label.y+label.height+h*.035))
            if value is None:
                return None
            result.append(value)
        return tuple(result)


class FragmentSweepSkill(DailyTasksSkill):
    def __init__(self, device, **kwargs):
        super().__init__(device, detector=kwargs.pop("detector", None) or FragmentDetector(), **kwargs)

    def _save(self, name):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder/f"{name}.png").write_bytes(self.last_png)

    def _stable(self, classify, message, timeout=None):
        previous = None
        deadline = self.clock()+(timeout or self.timeout)
        while self.clock() < deadline:
            frame = self._observe()
            value = classify(frame)
            if value is not None and value == previous:
                return frame, value
            previous = value
            self.sleeper(.7)
        raise ValueError(message)

    def _press(self, frame, point, action):
        self._check()
        self._save(f"{len(self.actions):03}_{action}")
        self.device.tap(round(point[0]*SIZE[0]/frame.shape[1]),
                        round(point[1]*SIZE[1]/frame.shape[0]), self.frame_size)
        self.actions.append(action)

    def _button(self, frame, name, action):
        marker = self.detector.find(frame, name, .93)
        if marker is None:
            raise ValueError(f"Chưa nhận diện được nút {name}.")
        self._press(frame, marker.center, action)

    def _wait_screen(self, *names):
        return self._stable(lambda f: s if (s := self.detector.screen(f)) in names else None,
                            "Chưa xác nhận màn hình tiếp theo; không bấm lại thao tác vừa gửi.")

    def _enter_selection(self, frame, screen):
        if screen == "config":
            self._button(frame, "cancel", "cancel_unverified_config")
            frame, screen = self._wait_screen("selection")
        if screen == "selection":
            self._press(frame, (frame.shape[1]*.5, frame.shape[0]*.974), "close_old_selection")
            frame, screen = self._wait_screen("fragments")
        if screen in {"heroes", "fragments"}:
            self._button(frame, "back", "verify_main_lobby")
            frame, screen = self._wait_screen("lobby")
        if screen != "lobby":
            raise ValueError("Cần xác nhận sảnh chính trước khi quét mảnh tướng.")
        self._button(frame, "entry", "open_hero_bag")
        frame, screen = self._wait_screen("heroes", "fragments")
        if screen == "heroes":
            self._button(frame, "fragments_tab", "open_fragments_tab")
            frame, screen = self._wait_screen("fragments")
        self._button(frame, "receive_many", "open_many_fragments")
        return self._wait_screen("selection")

    def _select_target(self):
        frame, count = self._stable(lambda f: self.detector.selected_count(f) if
                                    self.detector.screen(f) == "selection" else None,
                                    "Chưa đọc được số tướng đã chọn.")
        if count != 0:
            raise ValueError("Danh sách mới mở vẫn có tướng được chọn; chưa xác nhận chỉ Điển Vi.")
        direction, still, previous = False, 0, None
        for _ in range(26):
            frame = self._observe()
            if self.detector.screen(frame) != "selection":
                raise ValueError("Danh sách Nhận nhiều đã thay đổi.")
            if self.detector.target(frame) is not None:
                frame, target = self._stable(self.detector.target, "Chưa nhận diện ổn định ô Điển Vi.")
                if not target[0]:
                    self._press(frame, target[1], "select_dien_vi")
                frame, _ = self._stable(lambda f: True if self.detector.screen(f) == "selection" and
                                        (v := self.detector.target(f)) and v[0] and
                                        self.detector.selected_count(f) == 1 else None,
                                        "Chưa xác nhận chỉ một tướng Điển Vi được chọn; không quét.")
                return frame
            h, w = frame.shape[:2]
            strip = frame[round(h*.15):round(h*.74), round(w*.22):round(w*.90)]
            if previous is not None and strip.shape == previous.shape:
                still = still+1 if np.mean(cv2.absdiff(strip, previous)) < 2 else 0
            previous = strip.copy()
            if still >= 2:
                if direction:
                    break
                direction, still = True, 0
            self._check()
            start, end = (280, 760) if direction else (760, 280)
            self.device.swipe(1430, start, 1430, end, self.frame_size, 650)
            self.actions.append("scan_fragments_up" if direction else "scan_fragments_down")
            self.sleeper(.8)
        raise ValueError("Đã cuộn danh sách nhưng chưa tìm được mảnh Điển Vi.")

    def _wait_and_confirm(self):
        deadline = self.clock()+SWEEP_TIMEOUT
        unknown_since = None
        while self.clock() < deadline:
            frame = self._observe()
            screen = self.detector.screen(frame)
            if screen == "done":
                frame, _ = self._wait_screen("done")
                self._button(frame, "log_done", "confirm_fragment_sweep")
                frame, screen = self._wait_screen("selection", "fragments", "heroes")
                if screen == "selection":
                    self._press(frame, (frame.shape[1]*.5, frame.shape[0]*.974), "close_selection_after_sweep")
                    self._wait_screen("fragments")
                return
            if screen != "running":
                self._save("sweep_unrecognized")
                if unknown_since is None:
                    unknown_since = self.clock()
                elif self.clock()-unknown_since >= self.timeout:
                    raise ValueError("Chưa nhận diện bảng tiến trình/kết quả sau OK; đã lưu ảnh và không bắt đầu lại.")
            else:
                unknown_since = None
            self.sleeper(1.)
        raise ValueError("Chưa xác nhận quét đã hoàn thành; không gửi lại OK hoặc bắt đầu lượt mới.")

    def run_sweep(self):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        started = False
        try:
            self._check()
            if not self.detector.ready:
                return self._finish("needs_samples", "Thiếu ảnh nhận diện quét mảnh Điển Vi.")
            frame, screen = self._stable(self.detector.screen, "Hãy mở sảnh chính hoặc Túi tướng.")
            started = screen == "running"
            if screen not in {"running", "done"}:
                self._enter_selection(frame, screen)
                self.progress("Đang tìm và chọn riêng mảnh Điển Vi…")
                frame = self._select_target()
                self._button(frame, "quick", "open_quick_sweep")
                self._wait_screen("config")
                for index, name in enumerate(OPTIONS):
                    frame, options = self._stable(self.detector.options, "Chưa nhận diện được đủ ba tùy chọn quét.")
                    if not options[index][0]:
                        self._press(frame, options[index][1], f"enable_{name}")
                        self._stable(lambda f: True if (v := self.detector.options(f)) and v[index][0] else None,
                                     f"Chưa xác nhận {OPTION_NAMES[name]}; không bấm OK.")
                frame, _ = self._stable(lambda f: True if (v := self.detector.options(f)) and
                                        all(item[0] for item in v) else None,
                                        "Ba tùy chọn chưa được tích đầy đủ.")
                self._button(frame, "ok", "start_fragment_sweep")
                started = True
            self.progress("Đang chờ quét mảnh Điển Vi hoàn thành…")
            self._wait_and_confirm()
            return self._finish("completed", "Đã quét mảnh Điển Vi, xác nhận kết quả và dừng.")
        except InterruptedError:
            if started:
                self._cancel_sweep()
            return self._finish("cancelled", "Đã dừng chức năng quét mảnh Điển Vi.")
        except Exception as exc:
            return self._finish("blocked", f"Quét mảnh Điển Vi đã dừng: {exc}")

    def _cancel_sweep(self):
        try:
            png = self.device.capture()
            frame = self.detector.decode(png)
            if self.detector.screen(frame) == "running":
                button = self.detector.find(frame, "log_stop", .94)
                if button:
                    raw = cv2.imdecode(np.frombuffer(png, np.uint8), 1)
                    x, y = button.center
                    self.device.tap(round(x*SIZE[0]/frame.shape[1]), round(y*SIZE[1]/frame.shape[0]),
                                    (raw.shape[1], raw.shape[0]))
                    self.actions.append("stop_game_fragment_sweep")
        except Exception:
            self.progress("Chưa xác nhận dừng càn quét trong game; kiểm tra MuMu.")
