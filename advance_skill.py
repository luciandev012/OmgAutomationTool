"""Hero advancement in Time Machine: selected hero or a bounded team traversal."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
import cv2
import numpy as np
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector, EquipmentSkill, TeamEquipmentSkill
from login_engine import Match
from hero_navigation import HeroNavigationMixin

ROOT = Path(__file__).resolve().parent

@dataclass(frozen=True)
class ResourceCount:
    kind: str
    available: int
    required: int

@dataclass(frozen=True)
class AdvanceState:
    rank: int
    next_rank: int | None
    resources: tuple[ResourceCount, ...] = ()
    capped: bool = False
    enabled: bool = True
    condition_blocked: bool = False

@dataclass(frozen=True)
class AdvanceResult:
    status: str
    message: str
    reason: str
    initial_rank: int | None = None
    final_rank: int | None = None
    upgrades: int = 0
    resources: tuple[ResourceCount, ...] = ()
    screenshot: str = ""
    evidence_dir: str = ""

@dataclass(frozen=True)
class HeroAdvanceResult:
    index: int
    hero_id: str
    result: AdvanceResult

@dataclass(frozen=True)
class TeamAdvanceResult:
    status: str
    message: str
    heroes: tuple[HeroAdvanceResult, ...] = ()
    screenshot: str = ""
    evidence_dir: str = ""

    @property
    def processed(self):
        return len(self.heroes)

    @property
    def changed(self):
        return sum(h.result.upgrades > 0 for h in self.heroes)

class ScreenNumbers:
    """Read a complete game screenshot locally; select only numeric word boxes."""
    def __init__(self, runner=subprocess.run):
        self.runner = runner
        self.cache = {}

    def read(self, png, folder):
        key = hashlib.sha256(png).hexdigest()
        if key in self.cache:
            return self.cache[key]
        raw = cv2.imdecode(np.frombuffer(png, np.uint8), 1)
        if raw is None:
            raise ValueError("Ảnh OCR không hợp lệ.")
        folder.mkdir(parents=True, exist_ok=True)
        path = (folder / "ocr_input.png").resolve()
        path.write_bytes(png)
        exe = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
        result = self.runner([str(exe), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              str(ROOT / "windows_number_ocr.ps1"), "-ImagePath", str(path)],
                             capture_output=True, timeout=25,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("Windows OCR không hoạt động; cần bộ nhận diện tiếng Anh en-US của Windows.")
        data = json.loads(result.stdout.decode("utf-8-sig"))
        scale = 597 / raw.shape[0]
        words = [{"text": str(w["text"]), "x": float(w["x"])*scale, "y": float(w["y"])*scale,
                  "w": float(w["w"])*scale, "h": float(w["h"])*scale}
                 for w in data.get("words", [])]
        if len(self.cache) >= 24:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = words
        return words

    @staticmethod
    def in_box(word, box):
        x1,y1,x2,y2 = box
        return x1 <= word["x"] + word["w"]/2 <= x2 and y1 <= word["y"] + word["h"]/2 <= y2

    @classmethod
    def integer(cls, words, box, max_digits=4):
        text = "".join(w["text"] for w in sorted(words, key=lambda w: w["x"]) if cls.in_box(w, box))
        text = re.sub(r"\s+", "", text)
        return int(text) if re.fullmatch(rf"[0-9]{{1,{max_digits}}}", text) else None

    @classmethod
    def resources(cls, words, box, is_main):
        lines = []
        for word in sorted((w for w in words if cls.in_box(w, box)), key=lambda w: (w["y"],w["x"])):
            center = word["y"] + word["h"]/2
            line = next((line for line in lines if abs(line[0] - center) < 9), None)
            if line is None:
                lines.append([center, [word]])
            else:
                line[1].append(word)
        counts = []
        for _, items in lines:
            text = " ".join(w["text"] for w in sorted(items, key=lambda w: w["x"]))
            for found in re.finditer(r"(?<![\w/])([0-9]{1,12})\s*/\s*([0-9]{1,9})(?![\w/])", text):
                a,b = map(int, found.groups())
                if b <= 0:
                    return None
                counts.append((a,b))
        if len(counts) != (1 if is_main else 2):
            return None
        return tuple(ResourceCount("pills" if i == 0 else "fragments", a, b)
                     for i,(a,b) in enumerate(counts))

class AdvanceDetector(DungeonDetector):
    REGIONS = {
        "hero_title": (0,0,.28,.12), "back": (0,0,.13,.12),
        "advance_tab": (.16,.86,.54,1), "advance_heading": (.50,.10,.72,.25),
        "advance_button": (.57,.73,.88,.90), "pill_icon": (.51,.52,.75,.76),
        "main_badge": (0,.10,.18,.83), "event_context": (.72,.08,.98,.25),
        "rank_cap": (.59,.71,.89,.80), "rank_10": (.68,.14,.74,.21),
    }

    def __init__(self, asset_dir=None, numbers=None):
        super().__init__(asset_dir or ROOT / "assets/advance")
        self.numbers = numbers or ScreenNumbers()

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys()

    def is_advance(self, frame):
        return bool(self.find(frame,"hero_title") and self.find(frame,"advance_heading") and self.find(frame,"advance_tab"))

    def state(self, frame, png, folder, is_main):
        if not self.is_advance(frame):
            return None
        words = self.numbers.read(png, folder)
        # UI is height-normalized, and advancement is in the right-hand panel.
        offset = frame.shape[1] - 1061
        rank = self.numbers.integer(words, (726+offset,86,769+offset,119))
        if rank is None and self.find(frame,"rank_10",.96):
            rank = 10
        if rank is None:
            return None
        capped = bool(self.find(frame,"rank_cap",.90))
        next_rank = self.numbers.integer(words,(865+offset,86,905+offset,119))
        if capped:
            return AdvanceState(rank, None, capped=True, enabled=False)
        button = self.find(frame,"advance_button")
        if not button:
            return AdvanceState(rank,next_rank,enabled=False)
        resources = self.numbers.resources(words,(565+offset,345,998+offset,434),is_main)
        if resources is None:
            # Windows OCR misses small red fragment counters at 1080p.
            # A second full-frame pass at 720p keeps UI context and coordinates.
            raw = cv2.imdecode(np.frombuffer(png,np.uint8),1)
            small = cv2.resize(raw,(round(raw.shape[1]*720/raw.shape[0]),720),interpolation=cv2.INTER_AREA)
            alternative = cv2.imencode(".png",small)[1].tobytes()
            secondary = self.numbers.read(alternative,folder)
            resources = self.numbers.resources(secondary,(565+offset,345,998+offset,434),is_main)
            # Check prerequisite text in both passes.
            words = words + secondary
        if resources is None or next_rank != rank+1 or not self.find(frame,"pill_icon"):
            return None
        # Prerequisite messages below the resource row; item art is excluded.
        condition_blocked = False
        for word in words:
            if self.numbers.in_box(word,(560+offset,430,977+offset,461)):
                x,y,w,h = (round(word[k]) for k in ("x","y","w","h"))
                crop = frame[max(0,y):y+h,max(0,x):x+w]
                if crop.size:
                    hsv = cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
                    red = cv2.inRange(hsv,(0,90,90),(8,255,255)) | cv2.inRange(hsv,(170,90,90),(179,255,255))
                    condition_blocked |= float((red>0).mean()) > .12
        return AdvanceState(rank,next_rank,resources,condition_blocked=condition_blocked)

class EventFormationGate(EquipmentSkill):
    """Always prove event context by visiting the event lobby before spending."""
    def __init__(self, *args, advance_detector=None, **kwargs):
        super().__init__(*args,**kwargs)
        self.advance = advance_detector or AdvanceDetector()

    def enter(self):
        self.selected_card = None
        deadline = self.clock()+90
        event_frames, backs, last = 0,0,""
        while self.clock() < deadline:
            frame = self._observe()
            if self.advance.find(frame,"event_context",.90) and self.navigation.find(frame,"event_home"):
                event_frames += 1
                if event_frames >= 2:
                    self.progress("Đã xác minh sảnh Cỗ Máy Thời Gian; mở Đội Hình…")
                    return super()._formation()
            else:
                event_frames = 0
                hero = self.advance.find(frame,"hero_title")
                formation = self.detector.find(frame,"formation_title")
                if hero or formation:
                    if formation and self.selected_card is None:
                        selected = [c for c in self.detector.visible_heroes(frame) if c.selected]
                        if len(selected) == 1:
                            self.selected_card = selected[0]
                    if backs >= 4:
                        raise TimeoutError("Chưa xác minh được sảnh sự kiện; chưa tiến cấp.")
                    back = self.advance.find(frame,"back")
                    if not back:
                        raise TimeoutError("Không thấy nút quay về an toàn.")
                    self._tap(frame,back)
                    backs += 1
                    last = ""
                    self.sleeper(1)
                    continue
                intro = self.navigation.find(frame,"event_intro")
                target = self.navigation.find(frame,"intro_dismiss") if intro else self.navigation.find(frame,"time_machine")
                action = "intro" if intro else "event"
                if target and action != last:
                    self._tap(frame,target)
                    last = action
            self.sleeper(.6)
        raise TimeoutError("Không xác minh được Cỗ Máy Thời Gian; chưa tiêu tài nguyên.")

class AdvanceSkill(HeroNavigationMixin, EquipmentSkill):
    name = "advance_hero"
    subject_label = "Tướng"
    resource_names = {"pills":"Tiến cấp đơn","fragments":"mảnh tướng"}

    def __init__(self, device, *, detector=None, roster_detector=None, max_steps=100, **kwargs):
        kwargs.setdefault("evidence_root", ROOT / "runtime/advance")
        super().__init__(device,detector=detector or AdvanceDetector(),**kwargs)
        self.roster = roster_detector or EquipmentDetector()
        self.max_steps = max_steps
        self.initial_rank = self.final_rank = None
        self.upgrades = 0
        self.last_resources = ()
        self.gate = EventFormationGate(device,detector=self.roster,advance_detector=self.detector,
            stop=self.stop,progress=self.progress,preview=self.preview,navigation_detector=self.navigation,
            clock=self.clock,sleeper=self.sleeper,timeout=self.timeout)

    @staticmethod
    def validate_target(target_rank):
        if target_rank is not None and (not isinstance(target_rank,int) or isinstance(target_rank,bool) or target_rank < 0 or target_rank > 999):
            raise ValueError("Bậc mục tiêu phải là số nguyên từ 0 đến 999; để chế độ tự dừng nếu không đặt mốc.")

    def _finish_advance(self, status, reason, message):
        result = AdvanceResult(status,message,reason,self.initial_rank,self.final_rank,self.upgrades,
                               self.last_resources,self._save("result"),str(self.folder))
        self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/"result.json").write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding="utf-8")
        self.progress(message)
        return result

    def _stopped(self, reason, message):
        return self._finish_advance("success" if self.upgrades else "no_action",reason,message)

    def _open_tab(self):
        deadline, opened, tab_clicked = self.clock()+self.timeout,False,False
        while self.clock() < deadline:
            frame = self._observe()
            if self.detector.is_advance(frame):
                return frame
            if self.detector.find(frame,"hero_title"):
                tab = self.detector.find(frame,"advance_tab")
                if tab and not tab_clicked:
                    self._tap(frame,tab)
                    tab_clicked = True
            elif self.roster.find(frame,"formation_title") and self.roster.find(frame,"equipment_menu") and not opened:
                selected = [card for card in self.roster.visible_heroes(frame) if card.selected]
                if len(selected) != 1:
                    raise ValueError("Chưa xác nhận được tướng đang chọn.")
                badge = self.detector.find(frame,"main_badge",.90)
                self.is_main = bool(badge and selected[0].x <= badge.center[0] <= selected[0].x+selected[0].width
                                    and selected[0].y <= badge.center[1] <= selected[0].y+selected[0].height)
                # The hero body is the clickable formation surface specified by the user.
                target = Match("hero_body",round(frame.shape[1]*.45),round(frame.shape[0]*.64),1,1,1)
                self._tap(frame,target)
                opened = True
            self.sleeper(.6)
        raise TimeoutError("Không mở được tab Tiến cấp của tướng đang chọn.")

    def _stable_state(self):
        deadline, previous = self.clock()+self.timeout,None
        while self.clock() < deadline:
            frame = self._observe()
            state = self.detector.state(frame,self.last_png,self.folder,self.is_main)
            if state is not None and state == previous:
                return frame,state
            previous = state
            self.sleeper(.5)
        raise TimeoutError("Chưa đọc được bậc/tài nguyên ổn định; không bấm Tiến cấp.")

    def _after_click(self, old_rank):
        deadline, previous = self.clock()+self.timeout,None
        while self.clock() < deadline:
            frame = self._observe()
            state = self.detector.state(frame,self.last_png,self.folder,self.is_main)
            if state and state.rank == old_rank+1:
                if previous == state.rank:
                    return frame,state
                previous = state.rank
            elif state and state.rank != old_rank:
                raise ValueError("Bậc tiến cấp thay đổi ngoài dự kiến; giữ màn hình để kiểm tra.")
            else:
                previous = None
            self.sleeper(.6)
        raise TimeoutError("Chưa xác nhận bậc tăng sau lần bấm; đã dừng, không gửi lại lệnh.")

    def _run_in_event(self, target_rank=None):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.last_png = b""
        self.initial_rank = self.final_rank = None
        self.upgrades,self.last_resources = 0,()
        try:
            self.validate_target(target_rank)
            self._check()
            if not self.detector.ready:
                return self._finish_advance("needs_samples","missing_templates","Thiếu mẫu nhận diện tiến cấp.")
            self._open_tab()
            frame,state = self._stable_state()
            self.initial_rank = self.final_rank = state.rank
            self._save("before")
            for _ in range(self.max_steps):
                self._check()
                self.final_rank,self.last_resources = state.rank,state.resources
                if target_rank is not None and state.rank >= target_rank:
                    return self._stopped("target_reached",f"Đã đạt bậc +{state.rank}; dừng tại mốc người dùng đặt +{target_rank}.")
                if state.capped:
                    return self._stopped("max_rank",f"{self.subject_label} +{state.rank}: game báo đã đạt cấp tối đa.")
                missing = next((r for r in state.resources if r.available < r.required),None)
                if missing:
                    name = self.resource_names.get(missing.kind,missing.kind)
                    return self._stopped("missing_"+missing.kind,f"{self.subject_label} +{state.rank}: thiếu {name} ({missing.available}/{missing.required}); dừng tướng này.")
                if state.condition_blocked or not state.enabled:
                    return self._stopped("conditions_not_met",f"{self.subject_label} +{state.rank}: chưa đủ điều kiện hoặc nút tiến cấp không khả dụng.")
                button = self.detector.find(frame,"advance_button")
                if not button or state.next_rank != state.rank+1:
                    raise ValueError("Không xác nhận được nút và bậc kế tiếp.")
                self._save(f"before_step_{self.upgrades+1:03d}")
                self.progress(f"Tiến cấp +{state.rank} → +{state.next_rank}…")
                self._tap(frame,button)
                frame,state = self._after_click(state.rank)
                self.upgrades += 1
                self.final_rank = state.rank
                self._save(f"after_step_{self.upgrades:03d}")
                if target_rank is not None and state.rank >= target_rank:
                    self.last_resources = state.resources
                    return self._stopped("target_reached",f"Đã đạt bậc +{state.rank}; dừng tại mốc người dùng đặt +{target_rank}.")
                frame,state = self._stable_state()
            return self._finish_advance("blocked","step_budget","Đã hết giới hạn số lần tiến cấp của một lượt; không coi đây là giới hạn của game.")
        except InterruptedError:
            return self._finish_advance("cancelled","cancelled","Đã dừng tiến cấp theo yêu cầu.")
        except TimeoutError as exc:
            return self._finish_advance("blocked","unverified",str(exc))
        except Exception as exc:
            return self._finish_advance("error","error",f"Lỗi tiến cấp: {exc}")

    def run(self, *, target_rank=None):
        self.initial_rank = self.final_rank = None
        self.upgrades, self.last_resources, self.last_png = 0, (), b""
        self.folder = self.evidence_root/uuid.uuid4().hex
        try:
            self.validate_target(target_rank)
        except ValueError as exc:
            return self._finish_advance("error","invalid_target",str(exc))
        try:
            if not self.detector.ready or not self.roster.ready:
                return self._finish_advance("needs_samples","missing_templates","Thiếu mẫu nhận diện tiến cấp hoặc đội hình.")
            frame = self._observe()
            if self.detector.find(frame,"hero_title"):
                return self._finish_advance("blocked","choose_in_formation",
                    "Hãy quay về Đội Hình và chọn chân dung tướng muốn tiến cấp trước khi chạy chế độ một tướng.")
            frame = self.gate.enter()
            self._restore_selected(frame)
        except InterruptedError:
            return self._finish_advance("cancelled","cancelled","Đã dừng trước khi tiến cấp.")
        except Exception as exc:
            self.last_png = self.gate.last_png or self.last_png
            return self._finish_advance("blocked","event_not_verified",str(exc))
        return self._run_in_event(target_rank)

class TeamAdvanceSkill(TeamEquipmentSkill):
    name = "advance_team"
    action_name = "tiến cấp"

    def __init__(self,*args,advance_detector=None,**kwargs):
        kwargs.setdefault("evidence_root", ROOT / "runtime/advance")
        super().__init__(*args,**kwargs)
        self.advance_detector = advance_detector or AdvanceDetector()
        self.target_rank = None
        self.gate = EventFormationGate(self.device,detector=self.detector,advance_detector=self.advance_detector,
            stop=self.stop,progress=self.progress,preview=self.preview,navigation_detector=self.navigation,
            clock=self.clock,sleeper=self.sleeper,timeout=self.timeout)

    def _formation(self):
        try:
            return self.gate.enter()
        finally:
            self.last_png = self.gate.last_png or self.last_png

    def _make_hero_skill(self,index):
        return AdvanceSkill(self.device,detector=self.advance_detector,roster_detector=self.detector,
            stop=self.stop,progress=lambda text:self.progress(f"Tướng {index}/6: {text}"),
            preview=self.preview,navigation_detector=self.navigation,clock=self.clock,
            sleeper=self.sleeper,timeout=self.timeout,evidence_root=self.folder/f"hero_{index:02d}")

    def _run_hero(self,child,enhance):
        result = child._run_in_event(self.target_rank)
        if result.status in {"success","no_action"}:
            try:
                child.return_to_formation()
            except Exception as exc:
                result = replace(result,status="blocked",reason="return_failed",message=str(exc),
                                 screenshot=child._save("return_failed"))
        return result

    def _finish_team(self,status,message,heroes):
        items = tuple(HeroAdvanceResult(h.index,h.hero_id,h.result) for h in heroes)
        if status in {"success","no_action"}:
            steps = sum(h.result.upgrades for h in items)
            message = f"Đã kiểm tra {len(items)} tướng; {self.action_name} thành công {steps} bậc. Chi tiết lý do dừng được lưu riêng từng tướng."
        result = TeamAdvanceResult(status,message,items,self._save("result"),str(self.folder))
        self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/"result.json").write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding="utf-8")
        self.progress(message)
        return result

    def run(self,*,target_rank=None,max_heroes=6):
        try:
            AdvanceSkill.validate_target(target_rank)
            if not self.advance_detector.ready:
                self.folder = self.evidence_root/uuid.uuid4().hex
                return self._finish_team("needs_samples","Thiếu mẫu nhận diện tiến cấp.",[])
        except ValueError as exc:
            self.folder = self.evidence_root/uuid.uuid4().hex
            return self._finish_team("error",str(exc),[])
        self.target_rank = target_rank
        return super().run(max_heroes=max_heroes)
