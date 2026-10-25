"""Time Machine hero levelling with bounded input and verified EXP progress."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import cv2
import numpy as np

from advance_skill import AdvanceDetector, EventFormationGate, ScreenNumbers
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector, EquipmentSkill, TeamEquipmentSkill
from hero_navigation import HeroNavigationMixin
from login_engine import Match

ROOT = Path(__file__).resolve().parent

@dataclass(frozen=True)
class LevelState:
    level: int
    exp: int
    exp_needed: int
    books: tuple[int, ...]
    capped: bool = False
    enabled: bool = True

@dataclass(frozen=True)
class LevelResult:
    status: str
    message: str
    reason: str
    initial_level: int | None = None
    final_level: int | None = None
    actions: int = 0
    levels_gained: int = 0
    books_used: tuple[int, ...] = (0, 0, 0, 0)
    screenshot: str = ""
    evidence_dir: str = ""
    batch_actions: int = 0
    single_actions: int = 0

@dataclass(frozen=True)
class HeroLevelResult:
    index: int
    hero_id: str
    result: LevelResult

@dataclass(frozen=True)
class TeamLevelResult:
    status: str
    message: str
    heroes: tuple[HeroLevelResult, ...] = ()
    screenshot: str = ""
    evidence_dir: str = ""

    @property
    def processed(self):
        return len(self.heroes)

    @property
    def changed(self):
        return sum(h.result.actions > 0 for h in self.heroes)

class LevelDetector(DungeonDetector):
    REGIONS = {
        "level_tab": (.16, .86, .43, 1),
        "level_tab_selected": (.16, .86, .43, 1),
        "level_button": (.69, .73, .89, .88),
        "level_batch_button": (.54, .73, .70, .88),
        "level_heading": (.51, .12, .60, .21),
    }
    BOOK_BOXES = ((634, 389, 663, 420), (721, 389, 751, 420),
                  (807, 389, 837, 420), (880, 389, 926, 420))

    def __init__(self, asset_dir=None, numbers=None, context=None):
        super().__init__(asset_dir or ROOT / "assets/level")
        self.numbers = numbers or ScreenNumbers()
        self.context = context or AdvanceDetector()
        self.book_digits = EquipmentDetector().digits
        self.level_digits = {}
        for path in (asset_dir or ROOT / "assets/level").glob("level_digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),0)
            self.level_digits.setdefault(int(path.stem[-1]),[]).append(glyph>127)

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and set(self.book_digits) == set(range(10)) and self.context.ready

    def find(self, frame, name, threshold=.87):
        if name == "level_cap":
            return self.context.find(frame,"rank_cap",threshold)
        if name in {"hero_title", "back", "main_badge"}:
            return self.context.find(frame, name, threshold)
        return super().find(frame, name, threshold)

    def is_level(self, frame):
        return bool(self.find(frame, "hero_title") and self.find(frame, "level_heading")
                    and self.find(frame, "level_tab_selected"))

    def _level_number(self, frame):
        offset = frame.shape[1]-1061
        roi = frame[83:113,599+offset:635+offset]
        mask = cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(10,80,130),(45,255,255))
        cs,_ = cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        boxes = sorted(cv2.boundingRect(c) for c in cs if cv2.boundingRect(c)[3]>=9)
        if not 1 <= len(boxes) <= 3:
            return None
        text = ""
        for x,y,w,h in boxes:
            glyph = cv2.resize(mask[y:y+h,x:x+w],(18,28),interpolation=cv2.INTER_NEAREST)>127
            scores = sorted((min(float(np.mean(glyph != sample)) for sample in samples),digit)
                            for digit,samples in self.level_digits.items())
            if len(scores)<2 or scores[0][0]>.10 or scores[1][0]-scores[0][0]<.03:
                return None
            text += str(scores[0][1])
        return int(text)

    def _book_count(self, frame, box):
        x1,y1,x2,y2 = box
        roi = frame[y1:y2,x1:x2]
        mask = cv2.inRange(roi,(170,170,170),(255,255,255))
        contours,_ = cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        boxes = sorted(cv2.boundingRect(c) for c in contours
                       if 8 <= cv2.boundingRect(c)[3] <= 21 and 2 <= cv2.boundingRect(c)[2] <= 14)
        if not 1 <= len(boxes) <= 6:
            return None
        text = ""
        for x,y,w,h in boxes:
            glyph = cv2.resize(mask[y:y+h,x:x+w],(18,28),interpolation=cv2.INTER_NEAREST)>127
            scores = sorted((min(float(np.mean(glyph != sample)) for sample in samples),digit)
                            for digit,samples in self.book_digits.items())
            if len(scores)<2 or scores[0][0]>.25 or scores[1][0]-scores[0][0]<.025:
                return None
            text += str(scores[0][1])
        return int(text)

    def _books(self, frame, words):
        counts = []
        offset = frame.shape[1] - 1061
        for x1, y1, x2, y2 in self.BOOK_BOXES:
            box = (x1+offset, y1, x2+offset, y2)
            count = self.numbers.integer(words, box)
            if count is None:
                count = self._book_count(frame,box)
            if count is None:
                return None
            counts.append(count)
        return tuple(counts)

    def state(self, frame, png, folder):
        if not self.is_level(frame):
            return None
        words = self.numbers.read(png, folder)
        offset = frame.shape[1] - 1061
        level = self.numbers.integer(words, (599+offset, 83, 635+offset, 113))
        visual_level = self._level_number(frame)
        if visual_level is not None:
            if level is not None and visual_level != level:
                return None
            level = visual_level
        exp_words = [w for w in sorted(words, key=lambda w:w["x"])
                     if self.numbers.in_box(w, (750+offset, 83, 884+offset, 116))]
        text = "".join(w["text"] for w in exp_words)
        ratio = re.fullmatch(r"([0-9]{1,12})/([0-9]{1,12})", text)
        books = self._books(frame, words)
        if level is None or ratio is None or books is None:
            raw = cv2.imdecode(np.frombuffer(png, np.uint8), 1)
            small = cv2.resize(raw, (round(raw.shape[1]*720/raw.shape[0]),720), interpolation=cv2.INTER_AREA)
            secondary = self.numbers.read(cv2.imencode(".png", small)[1].tobytes(), folder)
            if level is None:
                level = self.numbers.integer(secondary, (599+offset,83,635+offset,113))
            if books is None:
                books = self._books(frame, secondary)
            if ratio is None:
                text = "".join(w["text"] for w in sorted(secondary, key=lambda w:w["x"])
                               if self.numbers.in_box(w,(750+offset,83,884+offset,116)))
                ratio = re.fullmatch(r"([0-9]{1,12})/([0-9]{1,12})",text)
        if level is None or level < 1 or ratio is None or books is None:
            return None
        exp, needed = map(int, ratio.groups())
        if exp > needed:
            return None
        capped = bool(self.find(frame,"level_cap",.92))
        return LevelState(level,exp,needed,books,capped,bool(self.find(frame,"level_button")))

class LevelSkill(HeroNavigationMixin, EquipmentSkill):
    name = "level_hero"

    def __init__(self,device,*,detector=None,roster_detector=None,context_detector=None,
                 level_limit=None,max_steps=300,**kwargs):
        kwargs.setdefault("evidence_root", ROOT / "runtime/level")
        super().__init__(device, detector=detector or LevelDetector(), **kwargs)
        self.roster = roster_detector or EquipmentDetector()
        self.context = context_detector or getattr(self.detector,"context",None) or AdvanceDetector()
        self.level_limit, self.max_steps = level_limit, max_steps
        self.configured_level_limit = level_limit
        self.gate = EventFormationGate(device,detector=self.roster,advance_detector=self.context,
            stop=self.stop,progress=self.progress,preview=self.preview,navigation_detector=self.navigation,
            clock=self.clock,sleeper=self.sleeper,timeout=self.timeout)
        self._reset()

    def _reset(self):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png = b""
        self.initial_level = self.final_level = None
        self.actions = self.batch_actions = self.single_actions = 0
        self.books_used = [0,0,0,0]

    @staticmethod
    def validate_target(target_level):
        if target_level is not None and (isinstance(target_level,bool)
            or not isinstance(target_level,int) or not 0 <= target_level <= 999):
            raise ValueError("Cấp mục tiêu phải là số nguyên từ 0 đến 999.")

    def _finish_level(self,status,reason,message):
        gained = (self.final_level-self.initial_level
                  if self.initial_level is not None and self.final_level is not None else 0)
        result = LevelResult(status,message,reason,self.initial_level,self.final_level,
            self.actions,gained,tuple(self.books_used),self._save("result"),str(self.folder),
            batch_actions=self.batch_actions,single_actions=self.single_actions)
        self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/"result.json").write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding="utf-8")
        self.progress(message)
        return result

    def _done(self,reason,message):
        return self._finish_level("success" if self.actions else "no_action",reason,message)

    def _open_tab(self):
        deadline, opened, tab_sent = self.clock()+self.timeout,False,False
        while self.clock() < deadline:
            frame = self._observe()
            if self.detector.is_level(frame):
                return frame
            if self.detector.find(frame,"hero_title"):
                tab = self.detector.find(frame,"level_tab")
                if tab and not tab_sent:
                    self._tap(frame,tab)
                    tab_sent = True
            elif self.roster.find(frame,"formation_title") and self.roster.find(frame,"equipment_menu") and not opened:
                selected = [c for c in self.roster.visible_heroes(frame) if c.selected]
                if len(selected) != 1:
                    raise ValueError("Chưa xác nhận đúng tướng đang chọn.")
                badge = self.detector.find(frame,"main_badge",.90)
                main = bool(badge and selected[0].x <= badge.center[0] <= selected[0].x+selected[0].width
                            and selected[0].y <= badge.center[1] <= selected[0].y+selected[0].height)
                if main:
                    return None
                body = Match("hero_body",round(frame.shape[1]*.45),round(frame.shape[0]*.64),1,1,1)
                self._tap(frame,body)
                opened = True
            self.sleeper(.6)
        raise TimeoutError("Không mở được tab Tăng cấp; chưa dùng sách EXP.")

    def _stable_state(self):
        deadline, previous = self.clock()+self.timeout,None
        while self.clock() < deadline:
            frame = self._observe()
            state = self.detector.state(frame,self.last_png,self.folder)
            if state is not None and state == previous:
                return frame,state
            previous = state
            self.sleeper(.5)
        raise TimeoutError("Chưa đọc được cấp, EXP và số sách ổn định; chưa bấm tăng cấp.")

    def _after_click(self,old,batch_size=1):
        deadline, previous = self.clock()+self.timeout,None
        settled_since = None
        while self.clock() < deadline:
            frame = self._observe()
            state = self.detector.state(frame,self.last_png,self.folder)
            if state is not None:
                if (state.capped and state.level == old.level
                        and state.exp == old.exp and state.books == old.books):
                    return frame,state,False
                used = tuple(a-b for a,b in zip(old.books,state.books))
                progress = state.level > old.level or (state.level == old.level and state.exp > old.exp)
                if state.level < old.level or state.level > old.level+batch_size or any(n < 0 for n in used):
                    raise ValueError("Cấp hoặc số sách thay đổi ngoài dự kiến; đã dừng để kiểm tra.")
                if progress and any(n > 0 for n in used):
                    if state == previous:
                        terminal = state.capped or not any(state.books) or not state.enabled or state.exp_needed == 0
                        complete = state.level-old.level >= batch_size
                        # A batch can end early at a resource/level limit. Allow
                        # time for intermediate animations; never repeat it.
                        if complete or terminal or self.clock()-settled_since >= 2:
                            return frame,state,True
                    else:
                        settled_since = self.clock()
                    previous = state
                else:
                    previous = None
            self.sleeper(.6)
        raise TimeoutError("Chưa xác nhận cấp/EXP tăng và sách đã dùng; dừng, không gửi lại lần bấm.")

    def _run_in_event(self,target_level=None):
        self._reset()
        try:
            self.validate_target(target_level)
            self._check()
            if not self.detector.ready:
                return self._finish_level("needs_samples","missing_templates","Thiếu bộ ảnh nhận diện Tăng cấp.")
            if self._open_tab() is None:
                return self._done("main_hero","Chủ tướng không có tab Tăng cấp bằng sách EXP; bỏ qua.")
            frame,state = self._stable_state()
            self.initial_level = self.final_level = state.level
            self._save("before")
            for _ in range(self.max_steps):
                self._check()
                self.final_level = state.level
                if target_level is not None and state.level >= target_level:
                    return self._done("target_reached",f"Đã đạt cấp {state.level}; dừng tại mốc {target_level}.")
                if state.capped or (self.level_limit is not None and state.level >= self.level_limit):
                    return self._done("level_cap",f"Tướng cấp {state.level}: đã chạm giới hạn cấp hiện tại.")
                if not any(state.books):
                    return self._done("missing_books",f"Tướng cấp {state.level}: hết sách EXP; dừng tướng này.")
                if not state.enabled or state.exp_needed == 0:
                    return self._done("conditions_not_met","Nút Tăng cấp không khả dụng; dừng tướng này.")
                remaining = target_level-state.level if target_level is not None else None
                cap_remaining = self.level_limit-state.level if self.level_limit is not None else None
                batch_size = 1 if ((remaining is not None and remaining < 5)
                                   or (cap_remaining is not None and cap_remaining < 5)) else 5
                name = "level_batch_button" if batch_size == 5 else "level_button"
                button = self.detector.find(frame,name)
                if not button:
                    raise ValueError("Chưa xác nhận nút 5 lần." if batch_size == 5 else "Chưa xác nhận nút Tăng cấp.")
                self._save(f"before_step_{self.actions+1:03d}")
                self.progress(f"Tướng cấp {state.level}: bấm {'5 lần' if batch_size == 5 else 'Tăng cấp'}, chờ xác nhận…")
                self._tap(frame,button)
                frame,new,changed = self._after_click(state,batch_size)
                if not changed:
                    return self._done("level_cap","Game báo đã đạt giới hạn cấp; dừng tướng này.")
                self.actions += 1
                self.batch_actions += int(batch_size == 5)
                self.single_actions += int(batch_size == 1)
                partial_batch = batch_size == 5 and new.level-state.level < 5
                self.final_level = new.level
                self.books_used = [used+a-b for used,a,b in zip(self.books_used,state.books,new.books)]
                state = new
                self._save(f"after_step_{self.actions:03d}")
                if target_level is not None and state.level >= target_level:
                    return self._done("target_reached",f"Đã đạt cấp {state.level}; dừng tại mốc {target_level}.")
                if partial_batch:
                    if state.capped:
                        return self._done("level_cap",f"Tướng cấp {state.level}: đã chạm giới hạn cấp.")
                    if not any(state.books):
                        return self._done("missing_books",f"Tướng cấp {state.level}: hết sách EXP.")
                    if not state.enabled or state.exp_needed == 0:
                        return self._done("conditions_not_met","Game dừng lượt 5 lần; chưa đủ điều kiện tăng tiếp.")
                    return self._done("partial_batch",f"Lượt 5 lần chỉ tăng được đến cấp {state.level}; dừng tướng này sau khi xác nhận màn hình ổn định.")
                # The next loop checks the game limit before any further input.
            return self._finish_level("blocked","step_budget","Đã hết giới hạn thao tác trong lượt tăng cấp.")
        except InterruptedError:
            return self._finish_level("cancelled","cancelled","Đã dừng tăng cấp theo yêu cầu.")
        except TimeoutError as exc:
            return self._finish_level("blocked","unverified",str(exc))
        except Exception as exc:
            return self._finish_level("error","error",str(exc))

    def run(self,*,target_level=None):
        self._reset()
        self.level_limit = self.configured_level_limit
        try:
            self.validate_target(target_level)
        except ValueError as exc:
            return self._finish_level("error","invalid_target",str(exc))
        try:
            if not self.detector.ready or not self.roster.ready:
                return self._finish_level("needs_samples","missing_templates","Thiếu mẫu nhận diện Tăng cấp/Đội Hình.")
            frame = self._observe()
            if self.detector.find(frame,"hero_title"):
                return self._finish_level("blocked","choose_in_formation",
                    "Hãy quay về Đội Hình và chọn tướng trước khi chạy chế độ một tướng.")
            frame = self.gate.enter()
            self._restore_selected(frame)
        except InterruptedError:
            return self._finish_level("cancelled","cancelled","Đã dừng trước khi tăng cấp.")
        except Exception as exc:
            self.last_png = self.gate.last_png or self.last_png
            return self._finish_level("blocked","event_not_verified",str(exc))
        return self._run_in_event(target_level)

class TeamLevelSkill(TeamEquipmentSkill):
    name = "level_team"

    def __init__(self,*args,level_detector=None,context_detector=None,**kwargs):
        kwargs.setdefault("evidence_root",ROOT/"runtime/level")
        super().__init__(*args,**kwargs)
        self.level_detector = level_detector or LevelDetector()
        self.context = context_detector or getattr(self.level_detector,"context",None) or AdvanceDetector()
        self.target_level, self.level_limit = None,None
        self.gate = EventFormationGate(self.device,detector=self.detector,advance_detector=self.context,
            stop=self.stop,progress=self.progress,preview=self.preview,navigation_detector=self.navigation,
            clock=self.clock,sleeper=self.sleeper,timeout=self.timeout)

    def _formation(self):
        try:
            return self.gate.enter()
        finally:
            self.last_png = self.gate.last_png or self.last_png

    def _make_hero_skill(self,index):
        return LevelSkill(self.device,detector=self.level_detector,context_detector=self.context,
            roster_detector=self.detector,level_limit=self.level_limit,stop=self.stop,
            progress=lambda text:self.progress(f"Tướng {index}/6: {text}"),preview=self.preview,
            navigation_detector=self.navigation,clock=self.clock,sleeper=self.sleeper,timeout=self.timeout,
            evidence_root=self.folder/f"hero_{index:02d}")

    def _run_hero(self,child,enhance):
        result = child._run_in_event(self.target_level)
        if result.status in {"success","no_action"}:
            try:
                child.return_to_formation()
            except Exception as exc:
                result = replace(result,status="blocked",reason="return_failed",message=str(exc),
                                 screenshot=child._save("return_failed"))
        return result

    def _finish_team(self,status,message,heroes):
        items = tuple(HeroLevelResult(h.index,h.hero_id,h.result) for h in heroes)
        if status in {"success","no_action"}:
            gains = sum(h.result.levels_gained for h in items)
            message = f"Đã kiểm tra {len(items)} tướng; tăng thành công {gains} cấp. Lý do dừng lưu riêng từng tướng."
        result = TeamLevelResult(status,message,items,self._save("result"),str(self.folder))
        self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/"result.json").write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding="utf-8")
        self.progress(message)
        return result

    def run(self,*,target_level=None,max_heroes=6):
        self.level_limit = None
        self.folder = self.evidence_root/uuid.uuid4().hex
        try:
            LevelSkill.validate_target(target_level)
        except ValueError as exc:
            return self._finish_team("error",str(exc),[])
        if not self.level_detector.ready:
            return self._finish_team("needs_samples","Thiếu mẫu nhận diện Tăng cấp.",[])
        self.target_level = target_level
        return super().run(max_heroes=max_heroes)
