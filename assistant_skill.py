"""Run the five ordinary-lobby Trợ Thủ tabs with verified target counts."""
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from chest_skill import ChestDetector
from daily_tasks_skill import DailyTasksDetector, DailyTasksSkill, ROOT
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector
from login_engine import Match, SIZE

TABS = ("Phó bản", "Đấu trường", "Tháp Ma Hồn", "Vượt ải trảm tướng", "Thần binh")
TARGETS = ({}, {"arena": 30}, {"reset": 2, "hell": 8, "elite": 6},
           {"slash": 6}, {"weapon": 6})
ROW_NAMES = {"arena": "Lượt Đấu trường", "reset": "Tạo mới và càn quét",
             "hell": "Luyện ngục", "elite": "Tinh anh",
             "slash": "Thí luyện trảm tướng", "weapon": "Thần binh chủng",
             "beast": "Phó bản Linh thú", "demon": "Phó bản Ma vương",
             "nightmare": "Phó bản Ác mộng", "dungeon_hell": "Phó bản Luyện ngục"}
SWEEP_TIMEOUT = 180


@dataclass(frozen=True)
class AssistantRow:
    count: int
    plus: tuple[int, int]
    minus: tuple[int, int]
    plus_ten: tuple[int, int] | None = None
    minus_ten: tuple[int, int] | None = None


class AssistantDetector(DungeonDetector):
    REGIONS = {
        "entry": (.32, .04, .76, .25), "title": (.08, 0, .23, .10),
        "execute": (.40, .90, .59, 1), "selected": (.08, .23, .73, .28),
        **{f"tab_{i}": (.08+i*.129, .14, .20+i*.129, .25) for i in range(5)},
        **{name: (.09, .28, .34, .88) for name in (
            "arena_heading", "tower_heading", "hell_heading", "elite_heading",
            "slash_heading", "weapon_heading", "dungeon_heading", "beast_heading",
            "demon_heading", "nightmare_heading", "dungeon_hell_heading",
            "reset_label", "count_label", "sweep_label")},
        **{name: (.45, .30, .87, .88) for name in ("plus", "minus", "plus_ten", "minus_ten")},
        "on": (.70, .35, .87, .57), "off": (.70, .35, .87, .57),
        "result_title": (.39, .08, .61, .17),
        "result_complete": (.39, .78, .61, .88),
        "dismiss_hint": (.35, .94, .65, 1),
    }

    def __init__(self):
        super().__init__(ROOT/"assets/assistant")
        self.lobby = DailyTasksDetector()
        self._raw = self._frame = None
        self.digits = EquipmentDetector().digits
        for path in (ROOT/"assets/assistant/digits").glob("digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 0)
            self.digits[int(path.stem.split("_")[1])].append(glyph > 127)
        self.native_digits = {digit: list(samples) for digit, samples in self.digits.items()}
        for path in (ROOT/"assets/assistant/native_digits").glob("digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 0)
            self.native_digits[int(path.stem.split("_")[1])].append(glyph > 127)

    def decode(self, png):
        self._frame = super().decode(png)
        self._raw = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        return self._frame

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and self.lobby.ready

    def _in(self, frame, name, box, threshold=.93):
        """Search only the section/row that has already been identified."""
        x1, y1, x2, y2 = map(round, box)
        crop = frame[max(0, y1):y2, max(0, x1):x2]
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
                if gray[y:y+h, x:x+w].mean() >= template.mean()*.78:
                    best = Match(name, x+max(0, x1), y+max(0, y1), w, h, score)
        return best

    def page(self, frame):
        if not self.find(frame, "title", .94) or not self.find(frame, "execute", .94):
            return None
        selected = self.find(frame, "selected", .93)
        if not selected:
            return None
        tabs = [(i, self.find(frame, f"tab_{i}", .93)) for i in range(5)]
        matches = [i for i, tab in tabs if tab and abs(tab.center[0]-selected.center[0]) < frame.shape[1]*.035]
        return matches[0] if len(matches) == 1 else None

    def result_visible(self, frame):
        return bool(self.find(frame, "result_title", .94) and
                    self.find(frame, "result_complete", .94))

    def result_strip(self, frame):
        h, w = frame.shape[:2]
        return frame[round(h*.19):round(h*.77), round(w*.22):round(w*.78)].copy()

    def row(self, frame, name):
        heading_name = "tower_heading" if name == "reset" else f"{name}_heading"
        heading = self.find(frame, heading_name, .93)
        if not heading:
            return None
        h, w = frame.shape[:2]
        end = h*.89
        # Repeated "Lượt khiêu chiến" labels belong to different sections.
        for other in ("hell_heading", "elite_heading", "beast_heading", "demon_heading",
                      "nightmare_heading", "dungeon_hell_heading"):
            marker = self.find(frame, other, .93)
            if marker and marker.y > heading.y+heading.height:
                end = min(end, marker.y)
        label_name = ("reset_label" if name == "reset" else "sweep_label" if name in
                      {"slash", "beast", "demon", "nightmare", "dungeon_hell"} else "count_label")
        label = self._in(frame, label_name, (w*.10, heading.y+heading.height, w*.35, end))
        if not label:
            return None
        y = label.center[1]
        box = (w*.46, y-h*.065, w*.87, min(h*.893, y+h*.065))
        minus, plus = self._in(frame, "minus", box), self._in(frame, "plus", box)
        if not minus or not plus or minus.center[0] >= plus.center[0]:
            return None
        x = (minus.center[0]+plus.center[0])/2
        cy = (minus.center[1]+plus.center[1])/2
        # Locate controls on the normalized image, but read thin digits from
        # the original screenshot so downsampling cannot turn 6 into 8.
        numeric = self._raw if frame is self._frame else frame
        nh, nw = numeric.shape[:2]
        nx, ny = x*nw/w, cy*nh/h
        crop = numeric[round(ny-nh*.029):round(ny+nh*.029), round(nx-nw*.030):round(nx+nw*.030)]
        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 145, 255)
        count = ChestDetector._read_mask(mask, nh*.018, self.native_digits if numeric is self._raw else self.digits)
        normalized = frame[round(cy-h*.029):round(cy+h*.029), round(x-w*.030):round(x+w*.030)]
        normalized_mask = cv2.inRange(cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY), 145, 255)
        fallback = ChestDetector._read_mask(normalized_mask, h*.018, self.digits)
        if count is None:
            count = fallback
        if count is None:
            return None
        plus_ten = self._in(frame, "plus_ten", box) if name == "arena" else None
        minus_ten = self._in(frame, "minus_ten", box) if name == "arena" else None
        return AssistantRow(count, plus.center, minus.center,
                            plus_ten.center if plus_ten else None, minus_ten.center if minus_ten else None)

    def main_lobby(self, frame):
        return self.lobby.main_lobby(frame)

    def quick_enabled(self, frame):
        if self.find(frame, "on", .94):
            return True
        if self.find(frame, "off", .94):
            return False
        return None


class AssistantSkill(DailyTasksSkill):
    def __init__(self, device, **kwargs):
        super().__init__(device, detector=kwargs.pop("detector", None) or AssistantDetector(), **kwargs)

    def _save(self, name):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder/f"{name}.png").write_bytes(self.last_png)

    def _stable(self, classify, message, timeout=None):
        deadline = self.clock()+(timeout or self.timeout)
        previous = None
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

    def _scroll(self, up=False):
        self._check()
        start, end = (370, 830) if up else (850, 365)
        self.device.swipe(1780, start, 1780, end, self.frame_size, 650)
        self.actions.append("scroll_up" if up else "scroll_down")
        self.sleeper(.8)

    def _row(self, tab, name):
        # Search both directions, accepting only a row under its own section.
        for up in (False, True):
            for _ in range(5):
                frame = self._observe()
                if self.detector.page(frame) != tab:
                    raise ValueError("Trợ thủ đã đổi tab hoặc có hộp thoại che màn hình.")
                if self.detector.row(frame, name) is not None:
                    return self._stable(lambda f: self.detector.row(f, name) if self.detector.page(f) == tab else None,
                                        f"Chưa đọc ổn định được {ROW_NAMES[name]}.")
                self._scroll(up=up)
        raise ValueError(f"Đã cuộn hai phía nhưng chưa đọc được {ROW_NAMES[name]}.")

    def _configure(self, tab):
        if tab == 0:
            for _ in range(5):
                frame = self._observe()
                if self.detector.page(frame) != tab:
                    raise ValueError("Chưa xác nhận tab Phó bản.")
                if self.detector.quick_enabled(frame) is not None:
                    break
                self._scroll(up=True)
            else:
                raise ValueError("Chưa đọc được trạng thái Phó bản ngày.")
            work = self.detector.quick_enabled(frame)
            for name in ("beast", "demon", "nightmare", "dungeon_hell"):
                _, row = self._row(tab, name)
                work = work or row.count > 0
            return work
        work = False
        for name, target in TARGETS[tab].items():
            frame, row = self._row(tab, name)
            if not 0 <= row.count <= 100:
                raise ValueError(f"Số lượt {ROW_NAMES[name]} không hợp lệ.")
            # Zero is the game's post-execution value; don't add paid attempts
            # again to a section already exhausted earlier today.
            if row.count == 0:
                self.progress(f"{ROW_NAMES[name]} còn 0 lượt; giữ nguyên.")
                continue
            work = True
            for _ in range(35):
                if row.count == target:
                    self.progress(f"Trợ thủ: {ROW_NAMES[name]} = {target}.")
                    break
                increase = row.count < target
                ten = abs(target-row.count) >= 10 and (row.plus_ten if increase else row.minus_ten)
                step = 10 if ten else 1
                point = ten or (row.plus if increase else row.minus)
                before = row.count
                self._press(frame, point, f"set_{name}_{before}_{target}")
                expected = before+(step if increase else -step)
                frame, row = self._stable(
                    lambda f: self.detector.row(f, name) if self.detector.page(f) == tab and
                    (r := self.detector.row(f, name)) and r.count == expected else None,
                    f"{ROW_NAMES[name]} chưa đổi từ {before} sang {expected}; không bấm cộng/trừ lại.")
            else:
                raise ValueError(f"Chưa đặt được {ROW_NAMES[name]} đúng {target} lượt.")
        return work

    def _verify_consumed(self, tab):
        names = TARGETS[tab] or dict.fromkeys(("beast", "demon", "nightmare", "dungeon_hell"))
        for name in names:
            _, row = self._row(tab, name)
            if row.count != 0:
                raise ValueError(f"Sau càn quét, {ROW_NAMES[name]} vẫn còn {row.count} lượt; chưa xác nhận hoàn tất, không chấp hành lại.")

    def _close_result(self):
        deadline = self.clock()+SWEEP_TIMEOUT
        stable_since = None
        previous = None
        while self.clock() < deadline:
            frame = self._observe()
            if self.detector.result_visible(frame):
                strip = self.detector.result_strip(frame)
                if previous is None or strip.shape != previous.shape or np.mean(cv2.absdiff(strip, previous)) > .5:
                    stable_since = self.clock()
                previous = strip
                if stable_since is not None and self.clock()-stable_since >= 3:
                    break
            else:
                stable_since = previous = None
            self.sleeper(.8)
        else:
            raise ValueError("Chưa xác nhận bảng Càn quét đã chạy xong; không chấp hành lại.")
        self._save("last_sweep_result")
        for _ in range(3):
            self._press(frame, (frame.shape[1]*.50, frame.shape[0]*.974), "close_assistant_result")
            self.sleeper(1.)
            frame = self._observe()
            if not self.detector.result_visible(frame):
                return self._stable(self.detector.page, "Bảng kết quả đã ẩn nhưng chưa trở lại Trợ thủ.")
        raise ValueError("Bảng Càn quét chưa đóng sau 3 lần chạm vùng trống.")

    def run_assistant(self):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        completed = []
        executed = 0
        try:
            self._check()
            if not self.detector.ready:
                return self._finish("needs_samples", "Thiếu ảnh nhận diện Trợ thủ.")
            frame, context = self._stable(
                lambda f: "result" if self.detector.result_visible(f) else "assistant" if
                self.detector.page(f) is not None else "lobby" if self.detector.main_lobby(f) else None,
                "Hãy mở sảnh chính hoặc giao diện Trợ thủ.")
            if context == "result":
                frame, _ = self._close_result()
            elif context == "lobby":
                entry = self.detector.find(frame, "entry", .93)
                if not entry:
                    raise ValueError("Chưa thấy icon Trợ thủ trên sảnh chính.")
                self._press(frame, entry.center, "open_assistant")
                frame, _ = self._stable(self.detector.page, "Chưa mở được Trợ thủ.")
            for tab, label in enumerate(TABS):
                self.progress(f"Trợ thủ {tab+1}/5: {label}.")
                frame, current = self._stable(self.detector.page, "Chưa xác nhận được tab Trợ thủ.")
                if current != tab:
                    marker = self.detector.find(frame, f"tab_{tab}", .93)
                    if not marker:
                        raise ValueError(f"Chưa thấy tab {label}.")
                    self._press(frame, marker.center, f"open_tab_{tab}")
                    frame, _ = self._stable(lambda f: tab if self.detector.page(f) == tab else None,
                                            f"Chưa chuyển sang tab {label}.")
                if not self._configure(tab):
                    self.progress(f"{label}: các mục đều đã hết lượt; chuyển tab tiếp theo.")
                    completed.append(label)
                    continue
                frame, _ = self._stable(lambda f: tab if self.detector.page(f) == tab else None,
                                        f"Chưa xác nhận cấu hình tab {label}.")
                button = self.detector.find(frame, "execute", .94)
                self._press(frame, button.center, f"execute_tab_{tab}")
                frame, actual_tab = self._close_result()
                if actual_tab != tab:
                    raise ValueError("Tab sau khi đóng kết quả không khớp tab vừa chạy.")
                self._verify_consumed(tab)
                self._save(f"tab_{tab}_completed")
                completed.append(label)
                executed += 1
            return self._finish("completed", f"Đã xử lý 5 tab Trợ thủ: chấp hành {executed} tab, {5-executed} tab đã hết lượt. Đã đóng các bảng kết quả.")
        except InterruptedError:
            return self._finish("cancelled", f"Đã dừng Trợ thủ; hoàn thành {len(completed)}/5 tab. Lượt càn quét đã bắt đầu vẫn do game xử lý.")
        except Exception as exc:
            return self._finish("blocked", f"Trợ thủ dừng sau {len(completed)}/5 tab: {exc}")
