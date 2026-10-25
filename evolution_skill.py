"""Breakthrough and awakening in Time Machine, with verified per-step progress."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import uuid
import cv2
import numpy as np
from advance_skill import (AdvanceDetector, AdvanceSkill, ResourceCount, ScreenNumbers,
                           TeamAdvanceSkill)
from equipment_skill import EquipmentDetector, TeamEquipmentSkill
from login_engine import Match

ROOT = Path(__file__).resolve().parent
KINDS = {"breakthrough": "Đột Phá", "awakening": "Giác Tỉnh"}


def validate_target(kind, target):
    if kind not in KINDS:
        raise ValueError("Loại nâng tướng không hợp lệ.")
    if target is None:
        return
    count = 1 if kind == "breakthrough" else 2
    if not isinstance(target, tuple) or len(target) != count or any(
            not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= 999 for n in target):
        raise ValueError("Mốc Đột Phá là (bậc,); mốc Giác Tỉnh là (sao, Lv), các số từ 0 đến 999.")


def progress_text(kind, value):
    if value is None:
        return "chưa đọc được bậc"
    return f"Đỏ-Bậc {value[0]}" if kind == "breakthrough" else f"{value[0]} sao Lv{value[1]}"


@dataclass(frozen=True)
class EvolutionState:
    rank: tuple[int, ...] | None
    next_rank: tuple[int, ...] | None
    resources: tuple[ResourceCount, ...] = ()
    condition_blocked: bool = False
    enabled: bool = True
    capped: bool = False
    condition_text: str = ""


@dataclass(frozen=True)
class EvolutionResult:
    status: str
    message: str
    reason: str
    initial_rank: tuple[int, ...] | None = None
    final_rank: tuple[int, ...] | None = None
    upgrades: int = 0
    resources: tuple[ResourceCount, ...] = ()
    screenshot: str = ""
    evidence_dir: str = ""


class EvolutionDetector(AdvanceDetector):
    REGIONS = {
        "page_title": (.09, 0, .21, .10),
        "entry": (.39, .46, .51, .76),
        "info_tab": (.08, .87, .24, 1),
        "info_heading": (.52, .17, .70, .27),
        "button": (.70, .84, .88, .99),
        "pill_icon": (.60, .66, .73, .83),
        "rank_label": (.59, .09, .73, .17),
        "fragment_mark": (.78, .66, .91, .83),
    }

    def __init__(self, kind, asset_dir=None, numbers=None, context=None):
        if kind not in KINDS:
            raise ValueError("Loại nâng tướng không hợp lệ.")
        self.kind = kind
        self.asset_dir = Path(asset_dir or ROOT / "assets" / kind)
        super().__init__(self.asset_dir, numbers=numbers)
        self.context = context or AdvanceDetector()
        self.digits = {k: list(v) for k, v in EquipmentDetector().digits.items()}
        for path in self.asset_dir.glob("digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 0)
            self.digits[int(path.stem.split("_")[1])].append(glyph > 127)

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and self.context.ready

    def find(self, frame, name, threshold=.87):
        if name == "page_title":
            title = super().find(frame, name, threshold)
            if title:
                return title
            # Hero artwork changes the background behind the page caption.
            # Require three independent controls unique to this upgrade screen.
            heading = super().find(frame, "rank_label", threshold)
            if (heading and super().find(frame, "pill_icon", threshold)
                    and super().find(frame, "button", threshold)):
                return Match(name, heading.x, heading.y, heading.width, heading.height, heading.score)
            return None
        if name == "hero_title":
            return self.find(frame, "page_title", threshold) or self.context.find(frame, name, threshold)
        if name in {"back", "event_context", "main_badge"}:
            return self.context.find(frame, name, threshold)
        if name == "rank_cap":
            return self.context.find(frame, name, threshold)
        if name == "advance_button":
            return super().find(frame, "button", threshold)
        return super().find(frame, name, threshold)

    def is_advance(self, frame):
        return bool(self.find(frame, "page_title") and self.find(frame, "rank_label"))

    def is_info(self, frame):
        return bool(self.context.find(frame, "hero_title") and self.find(frame, "info_heading"))

    def red_condition(self, frame):
        offset = frame.shape[1] - 1061
        y1, y2 = (502, 528) if self.kind == "breakthrough" else (487, 513)
        hsv = cv2.cvtColor(frame[y1:y2, 700+offset:993+offset], cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 110, 110), (10, 255, 255)) | cv2.inRange(hsv, (170, 110, 110), (179, 255, 255))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        letters = [cv2.boundingRect(c) for c in contours if 7 <= cv2.boundingRect(c)[3] <= 25
                   and 1 <= cv2.boundingRect(c)[2] <= 25]
        return len(letters) >= 3 and sum(w*h for x, y, w, h in letters) >= 60

    def _digit(self, frame, box):
        x1, y1, x2, y2 = box
        hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
        if self.kind == "breakthrough":
            mask = cv2.inRange(hsv, (0, 120, 130), (12, 255, 255)) | cv2.inRange(hsv, (170, 120, 130), (179, 255, 255))
        else:
            mask = cv2.inRange(hsv, (8, 110, 140), (45, 255, 255))
        cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = sorted(cv2.boundingRect(c) for c in cs if cv2.boundingRect(c)[3] >= 18)
        if not 1 <= len(boxes) <= 3:
            return None
        text = ""
        for x, y, w, h in boxes:
            glyph = cv2.resize(mask[y:y+h, x:x+w], (18, 28), interpolation=cv2.INTER_NEAREST) > 127
            scores = sorted((min(float(np.mean(glyph != sample)) for sample in samples), digit)
                            for digit, samples in self.digits.items())
            if scores[0][0] > .18 or scores[1][0] - scores[0][0] < .025:
                return None
            text += str(scores[0][1])
        return int(text)

    def _progress(self, frame):
        offset = frame.shape[1] - 1061
        boxes = ((746, 62, 771, 92), (958, 62, 981, 92)) if self.kind == "breakthrough" else (
            (717, 64, 735, 94), (788, 64, 804, 94), (929, 64, 947, 94), (1001, 64, 1016, 94))
        values = [self._digit(frame, (x1+offset, y1, x2+offset, y2)) for x1,y1,x2,y2 in boxes]
        if any(n is None for n in values):
            return None, None
        if self.kind == "breakthrough":
            return (values[0],), (values[1],)
        return tuple(values[:2]), tuple(values[2:])

    def state(self, frame, png, folder, is_main=False):
        if not self.is_advance(frame):
            return None
        rank, next_rank = self._progress(frame)
        blocked = self.red_condition(frame)
        # A confirmed red prerequisite blocks input even when OCR is incomplete.
        if blocked:
            return EvolutionState(rank, next_rank, condition_blocked=True)
        capped = bool(self.find(frame, "rank_cap", .92))
        if capped:
            return EvolutionState(rank, None, capped=True, enabled=False)
        if rank is None or next_rank is None or next_rank <= rank:
            return None
        if self.kind == "breakthrough" and next_rank != (rank[0]+1,):
            return None
        if self.kind == "awakening" and not (
                next_rank == (rank[0], rank[1]+1) or next_rank == (rank[0]+1, 0)):
            return None
        if not self.find(frame, "pill_icon"):
            return None
        offset = frame.shape[1]-1061
        y1,y2 = (449,479) if self.kind == "breakthrough" else (436,465)
        two = bool(self.find(frame, "fragment_mark", .92))
        counts = None
        for height in (None, 720, 900):
            image = png
            if height:
                raw = cv2.imdecode(np.frombuffer(png,np.uint8),1)
                raw = cv2.resize(raw,(round(raw.shape[1]*height/raw.shape[0]),height),interpolation=cv2.INTER_AREA)
                image = cv2.imencode(".png",raw)[1].tobytes()
            words = self.numbers.read(image,folder)
            counts = self.numbers.resources(words,(723+offset,y1,1008+offset,y2),not two)
            if counts is not None:
                break
        if counts is None:
            return None
        resources = tuple(ResourceCount("pills" if i == 0 else "fragments",r.available,r.required)
                          for i,r in enumerate(counts))
        return EvolutionState(rank,next_rank,resources,enabled=bool(self.find(frame,"advance_button")))


class EvolutionSkill(AdvanceSkill):
    def __init__(self, device, *, kind, detector=None, **kwargs):
        self.kind = kind
        self.name = kind + "_hero"
        self.subject_label = KINDS[kind]
        self.resource_names = {"pills": "Đột phá đơn" if kind == "breakthrough" else "Giác tỉnh đơn",
                               "fragments": "mảnh tướng"}
        kwargs.setdefault("evidence_root",ROOT/"runtime"/kind)
        super().__init__(device,detector=detector or EvolutionDetector(kind),**kwargs)

    def validate_target(self,target_rank):
        validate_target(self.kind,target_rank)

    def _finish_advance(self,status,reason,message):
        result = EvolutionResult(status,message,reason,self.initial_rank,self.final_rank,self.upgrades,
                                 self.last_resources,self._save("result"),str(self.folder))
        self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/"result.json").write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding="utf-8")
        self.progress(message)
        return result

    def _open_tab(self):
        deadline = self.clock()+self.timeout
        body_sent = entry_sent = info_sent = False
        absent = 0
        while self.clock()<deadline:
            frame = self._observe()
            if self.detector.is_advance(frame):
                return frame
            if self.detector.is_info(frame):
                entry = self.detector.find(frame,"entry")
                if entry and not entry_sent:
                    self._tap(frame,entry);entry_sent=True
                elif not entry:
                    absent += 1
                    if absent >= 2:
                        return None
            elif self.roster.find(frame,"formation_title") and not body_sent:
                if len([c for c in self.roster.visible_heroes(frame) if c.selected]) != 1:
                    raise ValueError("Chưa xác nhận tướng đang chọn.")
                self._tap(frame,Match("hero_body",round(frame.shape[1]*.45),round(frame.shape[0]*.56),2,2,1))
                body_sent=True
            elif self.detector.context.find(frame,"hero_title") and not info_sent:
                tab = self.detector.find(frame,"info_tab")
                if tab:
                    self._tap(frame,tab);info_sent=True
            self.sleeper(.6)
        raise TimeoutError(f"Không mở được trang {self.subject_label}; chưa dùng nguyên liệu.")

    def return_to_formation(self):
        deadline = self.clock()+self.timeout
        last = None
        while self.clock()<deadline:
            frame = self._observe()
            if self.roster.find(frame,"formation_title") and self.roster.find(frame,"equipment_menu"):
                return frame
            page = "upgrade" if self.detector.find(frame,"page_title") else (
                "hero" if self.detector.context.find(frame,"hero_title") else None)
            back = self.detector.find(frame,"back")
            if page and back and page != last:
                self._tap(frame,back);last=page
            self.sleeper(.6)
        raise TimeoutError("Chưa trở về Đội Hình; dừng trước khi chọn tướng tiếp theo.")

    def _confirm_step(self, old):
        deadline, previous = self.clock()+self.timeout,None
        while self.clock()<deadline:
            frame = self._observe()
            state = self.detector.state(frame,self.last_png,self.folder,False)
            if state and state.rank == old.next_rank:
                if previous == state.rank:
                    for before in old.resources:
                        after = next((r for r in state.resources if r.kind==before.kind),None)
                        if after and before.available-after.available != before.required:
                            raise ValueError("Bậc thay đổi nhưng số nguyên liệu giảm chưa khớp; dừng.")
                    return frame,state
                previous = state.rank
            elif state and state.rank is not None and state.rank != old.rank:
                raise ValueError("Bậc thay đổi ngoài bước kế tiếp đã xác nhận; dừng.")
            else:
                previous = None
            self.sleeper(.6)
        raise TimeoutError("Chưa xác nhận kết quả sau lần nâng; không gửi lại lệnh.")

    def _run_in_event(self,target_rank=None):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png = b""
        self.initial_rank = self.final_rank = None
        self.upgrades,self.last_resources = 0,()
        try:
            self.validate_target(target_rank);self._check()
            if not self.detector.ready:
                return self._finish_advance("needs_samples","missing_templates","Thiếu mẫu nhận diện " + self.subject_label)
            if self._open_tab() is None:
                return self._stopped("not_available",f"Tướng không có nút {self.subject_label}; bỏ qua.")
            self.is_main=False
            frame,state = self._stable_state()
            self.initial_rank = self.final_rank = state.rank
            self._save("before")
            for _ in range(self.max_steps):
                self._check()
                self.final_rank,self.last_resources = state.rank,state.resources
                if target_rank is not None and state.rank is not None and state.rank>=target_rank:
                    return self._stopped("target_reached",f"Đã đạt {progress_text(self.kind,state.rank)}; dừng đúng mốc.")
                if state.condition_blocked:
                    return self._stopped("conditions_not_met",f"{self.subject_label}: có chữ đỏ báo thiếu điều kiện gần nút nâng; dừng tướng này.")
                if state.capped:
                    return self._stopped("max_rank",f"{self.subject_label}: đã đạt giới hạn game.")
                missing = next((r for r in state.resources if r.available<r.required),None)
                if missing:
                    return self._stopped("missing_"+missing.kind,f"Thiếu {self.resource_names[missing.kind]} ({missing.available}/{missing.required}); dừng tướng này.")
                if state.rank is None or state.next_rank is None or not state.resources:
                    raise ValueError("Chưa đọc đủ bậc hoặc nguyên liệu; chưa nâng.")
                if target_rank is not None and state.next_rank>target_rank:
                    return self._stopped("target_would_exceed","Bước kế tiếp vượt mốc người dùng đặt; dừng.")
                button = self.detector.find(frame,"advance_button")
                if not state.enabled or not button:
                    return self._stopped("conditions_not_met","Nút nâng không khả dụng; dừng tướng này.")
                self._save(f"before_step_{self.upgrades+1:03d}")
                self.progress(f"{self.subject_label}: {progress_text(self.kind,state.rank)} → {progress_text(self.kind,state.next_rank)}…")
                self._tap(frame,button)
                frame,state = self._confirm_step(state)
                self.upgrades += 1;self.final_rank=state.rank
                self._save(f"after_step_{self.upgrades:03d}")
                frame,state = self._stable_state()
            return self._finish_advance("blocked","step_budget","Đã hết giới hạn số lần nâng của lượt; dừng bảo vệ.")
        except InterruptedError:
            return self._finish_advance("cancelled","cancelled","Đã dừng " + self.subject_label)
        except TimeoutError as exc:
            return self._finish_advance("blocked","unverified",str(exc))
        except Exception as exc:
            return self._finish_advance("error","error",str(exc))


class BreakthroughSkill(EvolutionSkill):
    def __init__(self,device,**kwargs):
        super().__init__(device,kind="breakthrough",**kwargs)


class AwakeningSkill(EvolutionSkill):
    def __init__(self,device,**kwargs):
        super().__init__(device,kind="awakening",**kwargs)


class TeamEvolutionSkill(TeamAdvanceSkill):
    def __init__(self,*args,kind,**kwargs):
        self.kind=kind
        self.action_name=KINDS[kind]
        kwargs.setdefault("evidence_root",ROOT/"runtime"/kind)
        super().__init__(*args,advance_detector=kwargs.pop("evolution_detector",None) or EvolutionDetector(kind),**kwargs)

    def _make_hero_skill(self,index):
        return EvolutionSkill(self.device,kind=self.kind,detector=self.advance_detector,roster_detector=self.detector,
            stop=self.stop,progress=lambda text:self.progress(f"Tướng {index}/6: {text}"),preview=self.preview,
            navigation_detector=self.navigation,clock=self.clock,sleeper=self.sleeper,timeout=self.timeout,
            evidence_root=self.folder/f"hero_{index:02d}")

    def run(self,*,target_rank=None,max_heroes=6):
        self.folder=self.evidence_root/uuid.uuid4().hex
        try:
            validate_target(self.kind,target_rank)
            if not self.advance_detector.ready:
                return self._finish_team("needs_samples","Thiếu mẫu nhận diện " + self.action_name,[])
        except ValueError as exc:
            return self._finish_team("error",str(exc),[])
        self.target_rank=target_rank
        return TeamEquipmentSkill.run(self,max_heroes=max_heroes)


class TeamBreakthroughSkill(TeamEvolutionSkill):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,kind="breakthrough",**kwargs)


class TeamAwakeningSkill(TeamEvolutionSkill):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,kind="awakening",**kwargs)