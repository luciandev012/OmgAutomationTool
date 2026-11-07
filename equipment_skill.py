"""Verified quick equip / quick enhance for Time Machine heroes.

Single-hero operation and bounded traversal of up to six formation heroes.
All actions are scoped to the injected AdbDevice, like the existing engines.
"""
from __future__ import annotations

import threading
import time
import uuid
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from dungeon_engine import DungeonDetector
from login_engine import AdbDevice, SIZE

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class EquipmentResult:
    status: str
    message: str
    before_stats: tuple[int, ...] = ()
    after_stats: tuple[int, ...] = ()
    equip_changed: bool = False
    enhance_changed: bool = False
    screenshot: str = ""
    before_screenshot: str = ""
    evidence_dir: str = ""


@dataclass(frozen=True)
class HeroCard:
    x: int
    y: int
    width: int
    height: int
    fingerprint: bytes
    selected: bool = False

    @property
    def center(self):
        return self.x + self.width // 2, self.y + self.height // 2

    def same_hero(self, other):
        left = np.frombuffer(self.fingerprint, np.uint8).astype(float)
        right = np.frombuffer(other.fingerprint, np.uint8).astype(float)
        return left.shape == right.shape and float(np.mean(np.abs(left - right))) < 12


@dataclass(frozen=True)
class HeroEquipmentResult:
    index: int
    hero_id: str
    result: EquipmentResult


@dataclass(frozen=True)
class TeamEquipmentResult:
    status: str
    message: str
    heroes: tuple[HeroEquipmentResult, ...] = ()
    screenshot: str = ""
    evidence_dir: str = ""

    @property
    def processed(self):
        return len(self.heroes)

    @property
    def changed(self):
        return sum(hero.result.status == "success" for hero in self.heroes)


class EquipmentDetector(DungeonDetector):
    REGIONS = {
        "formation_entry": (0, .80, .18, 1),
        "formation_title": (0, 0, .33, .12),
        "equipment_menu": (.32, .82, .68, 1),
        "quick_equip": (.35, .66, .76, .88),
        "quick_enhance": (.28, .66, .68, .88),
        "enhance_prompt": (.30, .19, .70, .35),
        "enhance_silver": (.30, .35, .75, .52),
        "enhance_ok": (.48, .58, .75, .76),
        "achievement_title": (.30, .04, .72, .21),
        "achievement_equipment": (.22, .50, .55, .69),
        "achievement_dismiss": (.25, .90, .80, 1),
        "roster_up": (0, .04, .20, .17),
        "roster_down": (0, .76, .20, .90),
        "hero_empty": (0, .10, .20, .83),
    }

    def __init__(self, asset_dir: Path | None = None):
        folder = asset_dir or ROOT / "assets/equipment"
        super().__init__(folder)
        self.digits = {}
        for path in folder.glob("digit_*.png"):
            image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 0)
            if image is not None:
                self.digits.setdefault(int(path.stem[6]), []).append(image > 127)
        for name in list(self.templates):
            if name.startswith("digit_"):
                self.templates.pop(name)
                self.scaled.pop(name)

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and set(self.digits) == set(range(10))

    def visible_heroes(self, frame):
        """Full portrait cards only; exclude clipped cards and green + slots."""
        up, down = self.find(frame, "roster_up"), self.find(frame, "roster_down")
        if not up or not down or not self.find(frame, "formation_title"):
            raise ValueError("Không nhận diện được danh sách tướng trong Đội Hình.")
        anchor = up.center[0]
        x1, x2 = max(0, anchor - 65), min(frame.shape[1], anchor + 43)
        y1, y2 = up.y + up.height + 2, down.y - 1
        roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 70, 100), (179, 255, 255))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cards = []
        empty_templates = self.scaled.get("hero_empty", [])
        phases = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if not (72 <= w <= 108 and 78 <= h <= 108 and y > 0 and y + h < roi.shape[0]):
                continue
            phases.append((y + y1 + h / 2) % 100)
        if not phases:
            raise ValueError("Chưa thấy khung chân dung đầy đủ; không chọn tướng theo vị trí đoán.")
        # Selected-card glow can join adjacent contours. Infer the validated
        # 100px row pitch from intact frames, then inspect every full row.
        distance = lambda a, b: abs((a - b + 50) % 100 - 50)
        seed = max(phases, key=lambda p: sum(distance(p, q) < 8 for q in phases))
        phase = (seed + float(np.median([(q-seed+50) % 100-50 for q in phases if distance(q, seed) < 8]))) % 100
        for cy in (round(phase + i * 100) for i in range(7)):
            if cy - 45 <= y1 or cy + 45 >= y2:
                continue
            x, y, w, h = anchor - 52, cy - 45, 91, 90
            gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
            if any(t.shape[0] <= h and t.shape[1] <= w and
                   cv2.minMaxLoc(cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED))[1] >= .88
                   for t, scale in empty_templates):
                continue
            cx = anchor - 7
            portrait = frame[cy-25:cy+25, cx-25:cx+25]
            # In the plus animation's invisible phase, the empty slot is flat
            # brown. Measure spatial luminance; RGB channel differences are
            # not portrait detail.
            if portrait.shape[:2] != (50, 50) or float(cv2.cvtColor(portrait, cv2.COLOR_BGR2GRAY).std()) < 15:
                continue
            fingerprint = cv2.resize(portrait, (16, 20), interpolation=cv2.INTER_AREA).tobytes()
            pointer = frame[cy-20:cy+20, anchor+40:anchor+56]
            selected = bool(pointer.size and (cv2.inRange(cv2.cvtColor(pointer, cv2.COLOR_BGR2HSV),
                                                        (5, 50, 110), (45, 255, 255)) > 0).mean() > .10)
            cards.append(HeroCard(x, y, w, h, fingerprint, selected))
        return sorted(cards, key=lambda card: card.y)

    def _read_blob(self, mask, cache=None):
        """Split touching narrow-font digits (notably 71) before classification."""
        ys, xs = np.where(mask > 0)
        if not len(xs):
            return None
        mask = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        width = mask.shape[1]
        if width > 24:
            return None
        cache = {} if cache is None else cache
        key = (mask.shape, mask.tobytes())
        if key in cache:
            return cache[key]
        if width > 8:
            candidates = []
            for cut in range(2, min(8, width - 2) + 1):
                left, right = self._read_blob(mask[:, :cut], cache), self._read_blob(mask[:, cut:], cache)
                if left and right:
                    candidates.append((left[1] + right[1], left[0] + right[0]))
            if not candidates:
                cache[key] = None
                return None
            error, text = min(candidates)
            cache[key] = (text, error)
            return text, error
        glyph = cv2.resize(mask, (18, 28), interpolation=cv2.INTER_NEAREST) > 127
        scores = sorted((min(float(np.mean(glyph != sample)) for sample in samples), digit)
                        for digit, samples in self.digits.items())
        if scores[0][0] > .25 or scores[1][0] - scores[0][0] < .025:
            cache[key] = None
            return None
        cache[key] = (str(scores[0][1]), scores[0][0])
        return str(scores[0][1]), scores[0][0]

    def read_stats(self, frame: np.ndarray) -> tuple[int, ...] | None:
        """Read only the four white numeric stats; unknown glyphs fail closed.

        HP, attack, physical defence, magic defence. These ROIs belong to the
        inspected formation layout, normalized to height 597 and right anchored.
        """
        values = []
        width = frame.shape[1]
        for row in (189, 223, 256, 290):
            crop = frame[row:row + 24, width - 138:width - 61]
            mask = cv2.inRange(crop, (190, 190, 190), (255, 255, 255))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            boxes = sorted([cv2.boundingRect(c) for c in contours if cv2.boundingRect(c)[3] >= 9])
            if not 1 <= len(boxes) <= 10:
                return None
            text = ""
            for x, y, w, h in boxes:
                if x == 0 or x + w >= mask.shape[1]:
                    return None
                reading = self._read_blob(mask[y:y+h, x:x+w])
                if reading is None:
                    return None
                text += reading[0]
            values.append(int(text))
        return tuple(values)


class EquipmentSkill:
    name = "upgrade_equipment"

    def __init__(self, device: AdbDevice, *, stop: threading.Event | None = None,
                 progress: Callable | None = None, preview: Callable | None = None,
                 detector: EquipmentDetector | None = None, navigation_detector=None,
                 clock: Callable = time.monotonic, sleeper: Callable | None = None,
                 timeout: float = 35, evidence_root: Path | None = None):
        self.device = device
        self.stop = stop or threading.Event()
        self.progress = progress or (lambda text: None)
        self.preview = preview or (lambda png: None)
        self.detector = detector or EquipmentDetector()
        self.navigation = navigation_detector or DungeonDetector()
        self.clock, self.sleeper = clock, sleeper or self.stop.wait
        self.timeout = timeout
        self.evidence_root = evidence_root or ROOT / "runtime/equipment"
        self.folder = self.evidence_root / uuid.uuid4().hex
        self.last_png = b""
        self.frame_size = SIZE
        self.before_stats = self.after_stats = ()
        self.equip_changed = self.enhance_changed = False

    def _check(self):
        if self.stop.is_set():
            raise InterruptedError()

    def _observe(self):
        self._check()
        self.last_png = self.device.capture()
        raw = cv2.imdecode(np.frombuffer(self.last_png, np.uint8), 1)
        if raw is None:
            raise ValueError("Ảnh ADB không hợp lệ.")
        self.frame_size = raw.shape[1], raw.shape[0]
        frame = self.detector.decode(self.last_png)
        self.preview(self.last_png)
        return frame

    def _tap(self, frame, match):
        self._check()
        x, y = match.center
        self.device.tap(round(x * SIZE[0] / frame.shape[1]),
                        round(y * SIZE[1] / frame.shape[0]), self.frame_size)

    def _save(self, name):
        if not self.last_png:
            return ""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / (name + ".png")
        path.write_bytes(self.last_png)
        return str(path)

    def _finish(self, status, message):
        result = EquipmentResult(status, message, self.before_stats, self.after_stats,
                                 self.equip_changed, self.enhance_changed, self._save("result"),
                                 str(self.folder / "before.png") if self.before_stats else "", str(self.folder))
        if self.last_png:
            import json
            (self.folder / "result.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        self.progress(message)
        return result

    def _formation(self):
        deadline, last_action, confirmed = self.clock() + self.timeout, "", 0
        while self.clock() < deadline:
            frame = self._observe()
            find = lambda name: self.detector.find(frame, name)
            if find("formation_title") and find("equipment_menu"):
                confirmed += 1
                if confirmed >= 2:
                    return frame
            else:
                confirmed = 0
                nf = lambda name: self.navigation.find(frame, name)
                action = target = None
                if nf("event_intro"):
                    action, target = "intro", nf("intro_dismiss")
                elif nf("event_home"):
                    action, target = "formation", find("formation_entry")
                elif nf("time_machine"):
                    action, target = "event", nf("time_machine")
                if target and action != last_action:
                    self.progress("Đi đến Đội Hình trong Cỗ Máy Thời Gian…")
                    self._tap(frame, target)
                    last_action = action
            self.sleeper(.7)
        raise TimeoutError("Không xác nhận được màn hình Đội Hình; không gửi thêm thao tác.")

    def _stable_stats(self):
        deadline, previous = self.clock() + self.timeout, None
        while self.clock() < deadline:
            frame = self._observe()
            if self.detector.find(frame, "formation_title") and self.detector.find(frame, "equipment_menu"):
                stats = self.detector.read_stats(frame)
                if stats is not None and stats == previous:
                    return frame, stats
                previous = stats
            else:
                previous = None
            self.sleeper(.7)
        raise TimeoutError("Không đọc được chỉ số ổn định sau thao tác; giữ màn hình để kiểm tra.")

    def _open_menu(self, frame):
        target = self.detector.find(frame, "equipment_menu")
        if not target or not self.detector.find(frame, "formation_title"):
            raise ValueError("Không ở màn hình trang bị hợp lệ.")
        both = lambda f: all(self.detector.find(f, name) for name in ("quick_equip", "quick_enhance"))
        if both(frame):
            return frame
        self._tap(frame, target)
        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            frame = self._observe()
            if self.detector.find(frame, "formation_title") and both(frame):
                return frame
            self.sleeper(.5)
        raise TimeoutError("Không thấy đủ hai nút Trang Bị Nhanh / Cường Hóa Nhanh.")

    def _enhance_result(self):
        deadline, previous, prompt_frames, confirmed = self.clock() + self.timeout, None, 0, False
        achievements = 0
        while self.clock() < deadline:
            frame = self._observe()
            find = lambda name: self.detector.find(frame, name)
            if all(find(name) for name in ("enhance_prompt", "enhance_silver", "enhance_ok")):
                previous = None
                prompt_frames += 1
                if prompt_frames >= 2 and not confirmed:
                    self._save("silver_confirmation")
                    self.progress("Đã nhận diện xác nhận dùng Bạc cường hóa tất cả trang bị; xác nhận một lần…")
                    self._tap(frame, find("enhance_ok"))
                    confirmed = True
                    self.sleeper(2)
            elif confirmed and all(find(name) for name in ("achievement_title", "achievement_equipment", "achievement_dismiss")):
                if achievements >= 4:
                    raise TimeoutError("Bảng thành tựu chưa đóng sau giới hạn; giữ màn hình để kiểm tra.")
                self._save("achievement_" + str(achievements + 1))
                self.progress("Đã nhận diện thành tựu cường hóa trang bị; đóng bảng để kiểm tra chỉ số…")
                self._tap(frame, find("achievement_dismiss"))
                achievements += 1
                previous = None
                self.sleeper(1)
            elif find("formation_title") and find("equipment_menu"):
                stats = self.detector.read_stats(frame)
                if stats is not None and stats == previous:
                    return frame, stats
                previous = stats
            else:
                previous = None
                prompt_frames = 0
            self.sleeper(.7)
        raise TimeoutError("Chưa xác nhận được kết quả cường hóa; giữ màn hình, không gửi lại lệnh.")

    def run(self, *, enhance: bool = True) -> EquipmentResult:
        """One verified quick-equip action, then one quick-enhance invocation.

        Starting precondition: Time Machine lobby or its formation screen.
        Unknown dialogs are never confirmed or retried automatically.
        """
        try:
            self.folder = self.evidence_root / uuid.uuid4().hex
            self.last_png = b""
            self.before_stats = self.after_stats = ()
            self.equip_changed = self.enhance_changed = False
            self._check()
            if not self.detector.ready:
                return self._finish("needs_samples", "Thiếu mẫu nhận diện trang bị/chỉ số; chưa thao tác.")
            self._formation()
            frame, self.before_stats = self._stable_stats()
            self._save("before")
            frame = self._open_menu(frame)
            self.progress("Trang Bị Nhanh: tối ưu đồ trong túi cho nhân vật đang chọn…")
            self._tap(frame, self.detector.find(frame, "quick_equip"))
            self.sleeper(2)
            frame, equipped = self._stable_stats()
            self.after_stats = equipped
            self.equip_changed = equipped != self.before_stats
            self._save("after_equip")
            if enhance:
                frame = self._open_menu(frame)
                self.progress("Cường Hóa Nhanh: nâng trang bị đang mặc, chờ xác nhận kết quả…")
                self._tap(frame, self.detector.find(frame, "quick_enhance"))
                self.sleeper(2)
                frame, self.after_stats = self._enhance_result()
                self.enhance_changed = all(a >= b for a, b in zip(self.after_stats, equipped)) and any(a > b for a, b in zip(self.after_stats, equipped))
                self._save("after_enhance")
            if self.equip_changed or self.enhance_changed:
                return self._finish("success", "Đã xác nhận kết quả: " +
                                    ("trang bị đã thay đổi; " if self.equip_changed else "trang bị giữ nguyên; ") +
                                    ("cường hóa tăng chỉ số." if self.enhance_changed else "chưa thấy chỉ số tăng do cường hóa."))
            return self._finish("no_action", "Chưa thấy chỉ số thay đổi; đã dừng, không lặp lại thao tác.")
        except InterruptedError:
            return self._finish("cancelled", "Đã dừng skill trang bị theo yêu cầu.")
        except TimeoutError as exc:
            return self._finish("blocked", str(exc))
        except Exception as exc:
            return self._finish("error", f"Lỗi skill trang bị: {exc}")


class TeamEquipmentSkill(EquipmentSkill):
    """Apply the existing verified operation once per distinct formation hero."""
    name = "upgrade_team_equipment"

    def __init__(self, *args, hero_skill_factory=EquipmentSkill, **kwargs):
        super().__init__(*args, **kwargs)
        self.hero_skill_factory = hero_skill_factory

    def _close_menu(self, frame):
        if not self.detector.find(frame, "formation_title") or not self.detector.find(frame, "equipment_menu"):
            raise ValueError("Màn hình không rõ sau khi xử lý tướng; dừng duyệt đội hình.")
        if not self.detector.find(frame, "quick_equip"):
            return frame
        self._tap(frame, self.detector.find(frame, "equipment_menu"))
        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            frame = self._observe()
            if self.detector.find(frame, "formation_title") and self.detector.find(frame, "equipment_menu") and not self.detector.find(frame, "quick_equip"):
                return frame
            self.sleeper(.5)
        raise TimeoutError("Không đóng được menu trang bị; chưa chuyển tướng.")

    @staticmethod
    def _same_view(left, right):
        return len(left) == len(right) and all(a.same_hero(b) for a, b in zip(left, right))

    def _scroll(self, frame, direction):
        self._swipe_roster(frame, direction)
        self.sleeper(1)
        previous = self.detector.visible_heroes(frame)
        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            frame = self._observe()
            current = self.detector.visible_heroes(frame)
            if (self._same_view(previous, current)
                    and all(abs(a.y-b.y) <= 2 and a.selected == b.selected
                            for a,b in zip(previous,current))):
                return frame
            previous = current
            self.sleeper(.5)
        raise TimeoutError("Danh sách tướng chưa ổn định sau cuộn; chưa chọn tướng tiếp theo.")

    def _swipe_roster(self, frame, direction):
        self._check()
        up, down = self.detector.find(frame, "roster_up"), self.detector.find(frame, "roster_down")
        if not up or not down or not self.detector.find(frame, "formation_title"):
            raise ValueError("Không xác nhận được vùng cuộn danh sách tướng.")
        x = up.center[0] - 7
        top, bottom = up.y + up.height + 50, down.y - 45
        y1, y2 = (top, bottom) if direction == "up" else (bottom, top)
        self.device.swipe(round(x * SIZE[0] / frame.shape[1]), round(y1 * SIZE[1] / frame.shape[0]),
                          round(x * SIZE[0] / frame.shape[1]), round(y2 * SIZE[1] / frame.shape[0]),
                          self.frame_size, duration=650)

    def _select_hero(self, frame, target):
        self._tap(frame, target)
        deadline, stable = self.clock() + self.timeout, 0
        while self.clock() < deadline:
            frame = self._observe()
            if self.detector.find(frame, "formation_title"):
                selected = [card for card in self.detector.visible_heroes(frame) if card.selected and card.same_hero(target)]
                stable = stable + 1 if len(selected) == 1 else 0
                if stable >= 2:
                    return frame
            self.sleeper(.5)
        raise TimeoutError("Chưa xác nhận chọn đúng tướng; chưa chạy thao tác nâng cấp.")

    def _make_hero_skill(self, index):
        return self.hero_skill_factory(
            self.device, stop=self.stop, detector=self.detector, navigation_detector=self.navigation,
            progress=lambda text: self.progress(f"Tướng {index}/6: {text}"),
            preview=self.preview, clock=self.clock, sleeper=self.sleeper, timeout=self.timeout,
            evidence_root=self.folder / f"hero_{index:02d}")

    def _run_hero(self, child, enhance):
        return child.run(enhance=enhance)

    def _finish_team(self, status, message, heroes):
        import json
        result = TeamEquipmentResult(status, message, tuple(heroes), self._save("result"), str(self.folder))
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "result.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        self.progress(message)
        return result

    def run(self, *, enhance: bool = True, max_heroes: int = 6) -> TeamEquipmentResult:
        self.folder = self.evidence_root / uuid.uuid4().hex
        self.last_png = b""
        results, visited = [], []
        try:
            self._check()
            if not isinstance(max_heroes, int) or isinstance(max_heroes, bool) or not 1 <= max_heroes <= 6:
                raise ValueError("Giới hạn tướng phải từ 1 đến 6.")
            if not self.detector.ready:
                return self._finish_team("needs_samples", "Thiếu mẫu nhận diện trang bị/danh sách tướng.", results)
            frame = self._close_menu(self._formation())
            self.progress("Đưa danh sách tướng về đầu để duyệt toàn đội…")
            for _ in range(8):
                old = self.detector.visible_heroes(frame)
                frame = self._scroll(frame, "up")
                if self._same_view(old, self.detector.visible_heroes(frame)):
                    break
            else:
                raise TimeoutError("Danh sách chưa ổn định khi cuộn về đầu.")
            scans = 0
            while len(results) < max_heroes:
                self._check()
                frame = self._close_menu(frame)
                cards = self.detector.visible_heroes(frame)
                target = next((card for card in cards if not any(card.same_hero(old) for old in visited)), None)
                if target is None:
                    old = cards
                    frame = self._scroll(frame, "down")
                    scans += 1
                    if self._same_view(old, self.detector.visible_heroes(frame)):
                        break
                    if scans > 8:
                        raise TimeoutError("Đã hết giới hạn cuộn danh sách; dừng để tránh lặp tướng.")
                    continue
                index = len(results) + 1
                self.progress(f"Tướng {index}/{max_heroes}: chọn và xác nhận chân dung…")
                frame = self._select_hero(frame, target)
                visited.append(target)
                child = self._make_hero_skill(index)
                outcome = self._run_hero(child, enhance)
                if child.last_png:
                    self.last_png = child.last_png
                results.append(HeroEquipmentResult(index, hashlib.sha256(target.fingerprint).hexdigest()[:12], outcome))
                if outcome.status not in {"success", "no_action"}:
                    return self._finish_team(outcome.status, f"Dừng ở tướng {index}: {outcome.message}", results)
                frame = self._observe()
            if not results:
                return self._finish_team("blocked", "Chưa nhận diện được tướng để xử lý; không báo hoàn thành đội hình.", results)
            changed = sum(item.result.status == "success" for item in results)
            message = f"Đã xử lý {len(results)} tướng; {changed} tướng thay đổi trang bị/chỉ số, {len(results)-changed} tướng không có thay đổi."
            return self._finish_team("success" if changed else "no_action", message, results)
        except InterruptedError:
            return self._finish_team("cancelled", f"Đã dừng; có kết quả của {len(results)} tướng.", results)
        except TimeoutError as exc:
            return self._finish_team("blocked", str(exc), results)
        except Exception as exc:
            return self._finish_team("error", f"Lỗi duyệt đội hình: {exc}", results)
