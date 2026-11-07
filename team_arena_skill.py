"""Quần Anh Tranh Bá daily team battles."""
import uuid
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from chest_skill import ChestDetector
from cross_server_skill import CrossServerDetector, CrossServerSkill
from daily_tasks_skill import ROOT, DailyTasksSkill
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector
from login_engine import SIZE

VIETNAM = timezone(timedelta(hours=7))
MAX_EXTRA_ATTEMPTS = 4
MAX_PURCHASE_COST = 800
READY_TIMEOUT = 180
MATCH_TIMEOUT = 300
BATTLE_TIMEOUT = 300


def bonus_hours(now):
    local = now.astimezone(VIETNAM)
    return 12 <= local.hour < 14 or 18 <= local.hour < 22


class TeamArenaDetector(CrossServerDetector):
    REGIONS = {
        "lobby_challenge": (.78, .89, .96, 1),
        "lobby_anchor": (.23, .89, .48, 1),
        "challenge_title": (0, 0, .30, .12),
        "card": (.02, .65, .98, .81),
        "title": (0, 0, .40, .12),
        "attempts_label": (0, .27, .14, .37),
        "buy_plus": (.14, .27, .23, .38),
        "create": (.28, .72, .52, .86),
        "auto": (.57, .72, .82, .86),
        "purchase_prompt": (.30, .31, .65, .42),
        "purchase_cap_label": (.37, .60, .60, .69),
        "purchase_minus": (.34, .41, .43, .53),
        "purchase_plus": (.55, .41, .65, .53),
        "purchase_ok": (.48, .67, .71, .80),
        "purchase_cancel": (.30, .67, .52, .80),
        "cost_label": (.38, .53, .51, .61),
        "invite": (.10, .92, .24, 1),
        "leave": (0, .92, .14, 1),
        "fight": (.42, .76, .69, .92),
        "leader": (.43, .43, .64, .62),
        "ready_stamp": (.17, .20, .92, .78),
        "matching": (.33, .34, .61, .48),
        "matching_cancel": (.35, .66, .64, .79),
        "buy_exhausted": (.27, .27, .69, .42),
        "exhausted_cancel": (.30, .68, .52, .81),
        "result_title": (.28, .02, .72, .23),
        "result_ours": (.38, .22, .61, .33),
        "result_enemy": (.33, .80, .63, .94),
        "reward_label": (.30, .49, .62, .63),
        "rewards_remaining": (.35, .78, .62, .89),
        "win": (.32, .02, .72, .25),
        "loss": (.20, .02, .80, .64),
        "dismiss_hint": (.31, .90, .70, 1),
    }

    def __init__(self):
        DungeonDetector.__init__(self, ROOT/"assets/team_arena")
        self.digits = EquipmentDetector().digits
        for path in (ROOT/"assets/team_arena/digits").glob("digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 0)
            self.digits[int(path.stem.split("_")[1])].append(glyph > 127)
        self.ready_patterns = []
        for path in (ROOT/"assets/team_arena").glob("ready*.png"):
            image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 1)
            if image is not None:
                mask = self._green(image)
                self.ready_patterns.extend(cv2.resize(mask, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
                                           for s in (.9, .95, 1., 1.05, 1.1))

    @property
    def ready(self):
        return super().ready and bool(self.ready_patterns)

    @staticmethod
    def _green(frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        return cv2.inRange(hsv, (30, 100, 110), (90, 255, 255))

    def ready_count(self, frame):
        # Separate slots prevent the same stamp from counting for two people.
        regions = ((.26, .26, .49, .42), (.69, .26, .85, .42),
                   (.20, .61, .41, .78), (.72, .61, .93, .78))
        height, width = frame.shape[:2]
        ready = 0
        for x1, y1, x2, y2 in regions:
            crop = self._green(frame[round(y1*height):round(y2*height),
                                     round(x1*width):round(x2*width)])
            for pattern in self.ready_patterns:
                h, w = pattern.shape
                if h <= crop.shape[0] and w <= crop.shape[1]:
                    _, score, _, _ = cv2.minMaxLoc(cv2.matchTemplate(crop, pattern, cv2.TM_CCORR_NORMED))
                    if score >= .75:
                        ready += 1
                        break
        return ready

    def result_page(self, frame):
        if (self.find(frame, "result_title", .92) and self.find(frame, "result_ours", .92)
                and self.find(frame, "result_enemy", .92)):
            return "summary"
        if (self.find(frame, "rewards_remaining", .92) and self.find(frame, "reward_label", .92)
                and (self.find(frame, "win", .91) or self.find(frame, "loss", .91))):
            return "rewards"
        return None

    def attempts(self, frame):
        return self._number(frame, "attempts_label", .35, .66)

    def reward_attempts(self, frame):
        return self._number(frame, "rewards_remaining", .27, .18)

    def _glyph_number(self, frame, box, minimum_height, red=False):
        x1, y1, x2, y2 = map(round, box)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        if red:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (0, 125, 130), (12, 255, 255))
            mask |= cv2.inRange(hsv, (170, 125, 130), (179, 255, 255))
        else:
            mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 145, 255)
        return ChestDetector._read_mask(mask, minimum_height, self.digits)

    def purchase(self, frame):
        cap_label = self.find(frame, "purchase_cap_label", .92)
        minus = self.find(frame, "purchase_minus", .93)
        plus = self.find(frame, "purchase_plus", .93)
        cost_label = self.find(frame, "cost_label", .92)
        if not all((cap_label, minus, plus, cost_label)):
            return None
        scale = plus.width/87
        x = cap_label.x+cap_label.width
        cap = self._glyph_number(frame, (x, cap_label.y, x+cap_label.width*.075,
                                        cap_label.y+cap_label.height), 12*scale, red=True)
        x, y = (minus.center[0]+plus.center[0])/2, minus.center[1]
        quantity = self._glyph_number(frame, (x-22*scale, y-24*scale, x+22*scale, y+24*scale), 20*scale)
        x = cost_label.x+cost_label.width
        cost = self._glyph_number(frame, (x+65*scale, cost_label.y,
                                         x+145*scale, cost_label.y+cost_label.height), 20*scale)
        return cap, quantity, cost, minus.center, plus.center


class TeamArenaSkill(CrossServerSkill):
    def __init__(self, device, *, now=None, **kwargs):
        DailyTasksSkill.__init__(self, device, detector=kwargs.pop("detector", None) or TeamArenaDetector(), **kwargs)
        self.now = now or (lambda: datetime.now(VIETNAM))

    def run_arena(self):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png, self.actions = b"", []
        run_date = self.now().astimezone(VIETNAM).date()
        purchases_done = False
        purchase_pending = None
        purchase_cancel_sent = False
        attempts_before_probe = None
        battle_pending = False
        before_fight = receipt_remaining = None
        result_seen = False
        completed = purchased = 0
        previous = phase = None
        phase_started = self.clock()
        result_kind = None
        result_taps = 0
        last_invite = float("-inf")
        count_changes = 0
        menu_before = None
        scrolls = still = 0
        direction = -1
        try:
            self._check()
            if not self.detector.ready:
                return self._finish("needs_samples", "Thiếu ảnh nhận diện Quần Anh Tranh Bá.")
            deadline = self.clock()+self.timeout
            while True:
                self._check()
                if self.now().astimezone(VIETNAM).date() != run_date:
                    return self._finish("blocked", "Đã qua ngày mới ở Việt Nam; kiểm tra lại số lượt Quần Anh Tranh Bá.")
                frame = self._observe()
                d = self.detector
                action = point = detail = None
                waiting = None
                result_page = d.result_page(frame)
                if d.find(frame, "buy_exhausted", .93):
                    if button := d.find(frame, "exhausted_cancel", .93):
                        action, point = "close_buy_exhausted", button.center
                elif d.find(frame, "purchase_prompt", .93):
                    purchase = d.purchase(frame)
                    if attempts_before_probe is None and not purchase_pending:
                        if button := d.find(frame, "purchase_cancel", .93):
                            action, point = "close_untracked_purchase", button.center
                    elif purchase and not purchase_pending:
                        cap, quantity, cost, minus, plus = purchase
                        if cap is not None and not 0 <= cap <= MAX_EXTRA_ATTEMPTS:
                            return self._finish("blocked", "Giới hạn mua lượt khác mức 4 lượt đã được hướng dẫn; cần kiểm tra trước khi mua.")
                        if cap == 0:
                            if button := d.find(frame, "purchase_cancel", .93):
                                action, point = "close_buy_exhausted", button.center
                        elif cap is not None and quantity is not None:
                            if count_changes >= 10:
                                return self._finish("blocked", "Chưa đặt được số lượng mua lượt chính xác.")
                            if quantity != cap:
                                action, point = ("increase_quantity", plus) if quantity < cap else ("decrease_quantity", minus)
                                detail = quantity
                            elif cost is not None and 0 < cost <= MAX_PURCHASE_COST:
                                if button := d.find(frame, "purchase_ok", .93):
                                    action, point = "buy_attempts", button.center
                                    detail = (cap, quantity, cost)
                            elif cost is not None:
                                return self._finish("blocked", f"Giá mua lượt hiện là {cost} NB; cần kiểm tra lại giá 4 lượt.")
                elif result_page:
                    result_seen = True
                    battle_pending = True
                    if result_page != result_kind:
                        result_kind, result_taps = result_page, 0
                    if result_page == "rewards":
                        value = d.reward_attempts(frame)
                        if value is not None:
                            receipt_remaining = value
                    action = "close_result"
                    point = self._empty_result_space(frame, (.50, .974)).center
                    detail = result_page
                elif d.find(frame, "matching", .92) and d.find(frame, "matching_cancel", .92):
                    if not battle_pending:
                        before_fight = d.attempts(frame)
                    battle_pending = True
                    waiting = "matching"
                elif d.find(frame, "title", .93):
                    remaining = d.attempts(frame)
                    if remaining is not None:
                        if not 0 <= remaining <= 7:
                            return self._finish("blocked", f"Số lượt Quần Anh Tranh Bá hiện là {remaining}, khác mức tối đa 7.")
                        if battle_pending:
                            if result_seen and ((receipt_remaining is not None and remaining == receipt_remaining)
                                                or (before_fight is not None and remaining == before_fight-1)):
                                completed += 1
                                battle_pending, result_seen = False, False
                                before_fight = receipt_remaining = result_kind = None
                                result_taps = 0
                                previous = None
                                self.progress(f"Quần Anh Tranh Bá: đã xong {completed} trận trong lần chạy này, còn {remaining} lượt.")
                            else:
                                waiting = "battle"
                        if not battle_pending:
                            if purchase_cancel_sent:
                                purchases_done = True
                            if purchase_pending and remaining == purchase_pending[0]+purchase_pending[1]:
                                purchased += purchase_pending[1]
                                purchases_done, purchase_pending = True, None
                                self.progress(f"Đã xác nhận mua thêm {purchased} lượt; hiện có {remaining} lượt.")
                            if purchase_pending:
                                waiting = "purchase"
                            elif not purchases_done:
                                if button := d.find(frame, "buy_plus", .93):
                                    action, point = "probe_purchase", button.center
                                    detail = remaining
                            elif remaining == 0:
                                action = "complete"
                            elif d.find(frame, "create", .93):
                                automatic = bonus_hours(self.now())
                                button = d.find(frame, "auto" if automatic else "create", .93)
                                if button:
                                    action = "auto_team" if automatic else "create_team"
                                    point = button.center
                            elif d.find(frame, "leave", .91):
                                count = d.ready_count(frame)
                                button = d.find(frame, "fight", .93)
                                # "Chiến" is the leader's action. Its text is more
                                # stable than the leader badge behind hero effects.
                                leader = button or d.find(frame, "leader", .90)
                                if leader and count == 4 and button:
                                    action, point, detail = "fight", button.center, remaining
                                elif not bonus_hours(self.now()) and leader and count < 4:
                                    if self.clock()-last_invite >= 20 and (invite := d.find(frame, "invite", .91)):
                                        action, point = "quick_invite", invite.center
                                    waiting = "ready"
                                else:
                                    waiting = "ready"
                elif battle_pending:
                    # Once the match starts, the game plays without inputs.
                    waiting = "battle"
                elif d.find(frame, "challenge_title", .93):
                    if card := d.find(frame, "card", .93):
                        action, point = "enter_arena", card.center
                    elif scrolls < 32:
                        action = "scroll_menu"
                elif d.find(frame, "lobby_anchor", .92):
                    if entry := d.find(frame, "lobby_challenge", .92):
                        action, point = "open_challenge", entry.center

                if waiting != phase:
                    phase, phase_started = waiting, self.clock()
                    if waiting:
                        self.progress({"matching": "Đang chờ ghép đối thủ online…",
                                       "battle": "Đang chờ trận đấu và kết quả…",
                                       "ready": "Đang chờ đủ 4 đồng đội sẵn sàng…",
                                       "purchase": "Đang kiểm tra số lượt sau khi mua…"}[waiting])
                if waiting:
                    limit = {"matching": MATCH_TIMEOUT, "battle": BATTLE_TIMEOUT,
                             "ready": READY_TIMEOUT, "purchase": self.timeout}[waiting]
                    if self.clock()-phase_started >= limit:
                        if waiting == "matching":
                            self._cancel_matching()
                        return self._finish("blocked", f"Quần Anh Tranh Bá chờ quá {limit} giây ở bước {waiting}; đã xong {completed} trận.")
                    deadline = self.clock()+self.timeout
                key = (action, detail) if action else None
                if key and key == previous:
                    if action == "complete":
                        return self._finish("completed", f"Quần Anh Tranh Bá đã hết lượt. Lần chạy này mua thêm {purchased} lượt và hoàn thành {completed} trận.")
                    if action == "scroll_menu":
                        strip = frame[round(frame.shape[0]*.69):round(frame.shape[0]*.77)]
                        if menu_before is not None and strip.shape == menu_before.shape:
                            still = still+1 if np.mean(cv2.absdiff(strip, menu_before)) < 3 else 0
                        menu_before = strip.copy()
                        if still >= 2:
                            if direction == 1:
                                return self._finish("blocked", "Đã quét hai phía nhưng chưa thấy Quần Anh Tranh Bá.")
                            direction, still = 1, 0
                        self._check()
                        start, end = (1530, 340) if direction == -1 else (340, 1530)
                        self.device.swipe(start, 540, end, 540, self.frame_size, 580)
                        self.actions.append(action)
                        scrolls += 1
                    else:
                        if action == "close_result" and result_taps >= 3:
                            return self._finish("blocked", "Bảng kết quả chưa đóng sau 3 lần chạm vùng trống.")
                        if action == "probe_purchase" and "probe_purchase" in self.actions:
                            return self._finish("blocked", "Hộp mua lượt chưa xuất hiện; giữ nguyên để kiểm tra.")
                        if (action in {"auto_team", "create_team", "enter_arena"} and self.actions
                                and action == self.actions[-1]):
                            return self._finish("blocked", "Game chưa chuyển màn sau khi lập đội hoặc mở Quần Anh Tranh Bá.")
                        self._tap_point(frame, point, action)
                        if action == "probe_purchase":
                            attempts_before_probe = detail
                        elif action == "buy_attempts":
                            purchase_pending = (attempts_before_probe, detail[1])
                        elif action == "close_buy_exhausted":
                            purchase_cancel_sent = True
                        elif action in {"increase_quantity", "decrease_quantity"}:
                            count_changes += 1
                        elif action == "fight":
                            battle_pending, before_fight = True, detail
                            result_seen = False
                        elif action == "quick_invite":
                            last_invite = self.clock()
                        elif action == "close_result":
                            result_taps += 1
                    deadline = self.clock()+self.timeout
                    key = None
                previous = key
                if self.clock() >= deadline:
                    return self._finish("blocked", "Quần Anh Tranh Bá chưa xác nhận được màn hình tiếp theo; xem ảnh đã lưu.")
                self.sleeper(1.)
        except InterruptedError:
            self._cancel_matching()
            return self._finish("cancelled", f"Đã dừng Quần Anh Tranh Bá sau {completed} trận trong lần chạy này.")
        except Exception as exc:
            return self._finish("error", f"Lỗi Quần Anh Tranh Bá: {exc}")

    def _cancel_matching(self):
        try:
            png = self.device.capture()
            frame = self.detector.decode(png)
            if self.detector.find(frame, "matching", .92):
                if button := self.detector.find(frame, "matching_cancel", .92):
                    raw = cv2.imdecode(np.frombuffer(png, np.uint8), 1)
                    x, y = button.center
                    self.device.tap(round(x*SIZE[0]/frame.shape[1]), round(y*SIZE[1]/frame.shape[0]),
                                    (raw.shape[1], raw.shape[0]))
                    self.actions.append("cancel_matching")
        except Exception:
            self.progress("Chưa xác nhận hủy ghép đội trong game; kiểm tra MuMu.")
