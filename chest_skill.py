"""Open the four Time Machine chest types, upgrading full EXP bars first."""
from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from advance_skill import AdvanceDetector, ScreenNumbers
from dungeon_engine import DungeonDetector
from equipment_skill import EquipmentDetector, EquipmentSkill
from login_engine import Match

ROOT = Path(__file__).resolve().parent
CHESTS = ("Nguyên Liệu", "Tăng Phẩm Chất", "Tướng", "Thần Binh")


@dataclass(frozen=True)
class ChestState:
    kind: int
    quantity: int
    level: int
    exp: int
    exp_needed: int
    exp_per_chest: int
    batch: int
    open_enabled: bool
    upgrade_enabled: bool

    @property
    def expected_open(self):
        if self.exp >= self.exp_needed or self.exp_per_chest <= 0:
            return 0
        return min(self.quantity, self.batch, math.ceil((self.exp_needed-self.exp)/self.exp_per_chest))


@dataclass
class ChestTypeResult:
    kind: int
    name: str
    initial_count: int
    remaining: int
    initial_level: int
    final_level: int
    opened: int = 0
    open_actions: int = 0
    level_ups: int = 0
    reason: str = ""


@dataclass(frozen=True)
class ChestResult:
    status: str
    message: str
    types: tuple[ChestTypeResult, ...] = ()
    opened: int = 0
    level_ups: int = 0
    pending_action: str = ""
    screenshot: str = ""
    evidence_dir: str = ""


class ChestDetector(DungeonDetector):
    REGIONS = {
        "chest_title": (.10, 0, .22, .10),
        "entry": (.20, .82, .40, 1),
        "open_label": (.43, .87, .67, .99),
        "upgrade_on": (.72, .70, .90, .83),
        "upgrade_off": (.72, .70, .90, .83),
        "reward_title": (.30, .09, .71, .29),
        **{f"heading_{i}": (.42, .05, .71, .13) for i in range(4)},
        **{f"tab_{i}": (0, .13+i*.20, .14, .34+i*.20) for i in range(4)},
    }

    def __init__(self, asset_dir=None, numbers=None, context=None):
        folder = Path(asset_dir or ROOT/"assets/chest")
        super().__init__(folder)
        self.numbers = numbers or ScreenNumbers()
        self.context = context or AdvanceDetector()
        self.digits = {k:list(v) for k,v in EquipmentDetector().digits.items()}
        for path in folder.glob("count_digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),0)
            self.digits[int(path.stem.split("_")[2])].append(glyph>127)
        self.native_digits = {}
        for path in folder.glob("quantity_native_digit_*.png"):
            glyph = cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),0)
            self.native_digits.setdefault(int(path.stem.split("_")[3]),[]).append(glyph>127)

    @property
    def ready(self):
        return (set(self.REGIONS) <= self.templates.keys() and self.context.ready
                and set(self.native_digits)==set(range(10)))

    def find(self, frame, name, threshold=.87):
        if name in {"back", "event_context", "hero_title"}:
            return self.context.find(frame,name,threshold)
        match = super().find(frame,name,threshold)
        if match and name in {"upgrade_on", "upgrade_off"}:
            crop = frame[match.y:match.y+match.height,match.x:match.x+match.width]
            hsv = cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
            orange = float((cv2.inRange(hsv,(3,100,90),(28,255,255))>0).mean())
            if (name == "upgrade_on" and orange < .25) or (name == "upgrade_off" and orange > .12):
                return None
        return match

    def page_kind(self, frame):
        if self.find(frame,"reward_title") or not self.find(frame,"chest_title"):
            return None
        kinds = [i for i in range(4) if self.find(frame,f"heading_{i}",.90)]
        return kinds[0] if len(kinds)==1 else None

    def _number(self, frame, box, minimum_height):
        offset = frame.shape[1]-1061
        x1,y1,x2,y2 = box
        crop = frame[y1:y2,x1+offset:x2+offset]
        mask = cv2.inRange(crop,(185,185,185),(255,255,255))
        return self._read_mask(mask,minimum_height,self.digits)

    @staticmethod
    def _read_mask(mask,minimum_height,digits):
        contours,_ = cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        boxes = sorted(cv2.boundingRect(c) for c in contours if cv2.boundingRect(c)[3]>=minimum_height)
        if not 1 <= len(boxes) <= 8:
            return None
        result = ""
        for x,y,w,h in boxes:
            glyph = cv2.resize(mask[y:y+h,x:x+w],(18,28),interpolation=cv2.INTER_NEAREST)>127
            scores = sorted((min(float(np.mean(glyph!=g)) for g in samples),digit)
                            for digit,samples in digits.items())
            if scores[0][0]>.18 or scores[1][0]-scores[0][0]<.025:
                return None
            result += str(scores[0][1])
        return int(result)

    def quantity(self, frame, png=None):
        if png:
            raw = cv2.imdecode(np.frombuffer(png,np.uint8),1)
            if raw.shape[0]>=900:
                scale = raw.shape[0]/597
                offset = raw.shape[1]-round(1061*scale)
                x1,y1,x2,y2 = [round(v*scale) for v in (763,345,850,386)]
                mask = cv2.inRange(raw[y1:y2,x1+offset:x2+offset],(185,185,185),(255,255,255))
                return self._read_mask(mask,18*scale,self.native_digits)
        return self._number(frame,(745,345,850,386),18)

    def _text(self,words,box):
        return "".join(w["text"] for w in sorted(words,key=lambda w:w["x"]) if self.numbers.in_box(w,box))

    def state(self, frame, png, folder):
        kind = self.page_kind(frame)
        if kind is None:
            return None
        quantity = self.quantity(frame,png)
        if quantity is None:
            return None
        offset = frame.shape[1]-1061
        level = self._number(frame,(425,447,442,478),18)
        per = self._number(frame,(733,487,755,512),10)
        batch = self._number(frame,(557,538,605,574),23)
        exp = needed = None
        for height in (None,720,900):
            image = png
            if height:
                raw = cv2.imdecode(np.frombuffer(png,np.uint8),1)
                small = cv2.resize(raw,(round(raw.shape[1]*height/raw.shape[0]),height),interpolation=cv2.INTER_AREA)
                image = cv2.imencode(".png",small)[1].tobytes()
            words = self.numbers.read(image,folder)
            text = self._text(words,(200+offset,445,445+offset,480))
            match = re.search(r"[lLiI][vV][:：]?([0-9]{1,3})$",text)
            if level is None and match:
                level = int(match[1])
            ratio = re.fullmatch(r"([0-9]{1,12})/([0-9]{1,12})",
                                 self._text(words,(480+offset,458,755+offset,479)))
            if exp is None and ratio:
                current,total = int(ratio[1]),int(ratio[2])
                if total>0:
                    exp,needed = current,total
            text = self._text(words,(435+offset,487,755+offset,512))
            match = re.search(r"EXP[:：]?([0-9]{1,4})$",text,re.I)
            if per is None and match:
                per = int(match[1])
            text = self._text(words,(455+offset,531,738+offset,580))
            values = re.findall(r"[0-9]{1,6}",text)
            if batch is None and len(values)==1:
                batch = int(values[0])
            if level is not None and exp is not None and (quantity==0 or (per and batch)):
                break
        if level is None or level<=0 or exp is None or (quantity and (not per or not batch)):
            return None
        upgrade_on,upgrade_off = self.find(frame,"upgrade_on"),self.find(frame,"upgrade_off")
        if bool(upgrade_on)==bool(upgrade_off):
            return None
        label = self.find(frame,"open_label")
        if quantity and not label:
            return None
        crop = frame[530:579,455+offset:735+offset]
        hsv = cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        orange = float((cv2.inRange(hsv,(3,100,90),(28,255,255))>0).mean())
        return ChestState(kind,quantity,level,exp,needed,per or 0,batch or 0,
                          bool(label and orange>.25),bool(upgrade_on))


class ChestSkill(EquipmentSkill):
    name = "open_event_chests"

    def __init__(self,device,*,detector=None,**kwargs):
        kwargs.setdefault("evidence_root",ROOT/"runtime/chest")
        super().__init__(device,detector=detector or ChestDetector(),**kwargs)
        self.roster = EquipmentDetector()
        self.records = {}
        self.pending_action = ""

    def _finish_chest(self,status,message):
        items = tuple(self.records[i] for i in sorted(self.records))
        result = ChestResult(status,message,items,sum(r.opened for r in items),sum(r.level_ups for r in items),
                             self.pending_action,self._save("result"),str(self.folder))
        self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/"result.json").write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding="utf-8")
        self.progress(message)
        return result

    def _dismiss_reward(self, frame):
        # A known reward banner owns this overlay; the observed blank lower-right
        # area dismisses it without touching an item or the open button behind it.
        self._tap(frame,Match("reward_close",frame.shape[1]-65,frame.shape[0]-35,2,2,1))

    def _event_lobby(self):
        deadline = self.clock()+90
        stable, last = 0,None
        while self.clock()<deadline:
            frame = self._observe()
            if self.detector.find(frame,"event_context",.90) and self.navigation.find(frame,"event_home"):
                stable += 1
                if stable>=2:
                    self.progress("Đã xác minh sảnh Cỗ Máy Thời Gian; mở Rương…")
                    return frame
            else:
                stable = 0
                if self.detector.find(frame,"chest_title") or self.roster.find(frame,"formation_title") or self.detector.find(frame,"hero_title"):
                    action,target = "back",self.detector.find(frame,"back")
                elif self.navigation.find(frame,"event_intro"):
                    action,target = "intro",self.navigation.find(frame,"intro_dismiss")
                else:
                    action,target = "event",self.navigation.find(frame,"time_machine")
                if target and action!=last:
                    self._tap(frame,target);last=action
            self.sleeper(.6)
        raise TimeoutError("Chưa xác minh được sảnh Cỗ Máy Thời Gian; chưa mở rương.")

    def _open_page(self):
        frame = self._event_lobby()
        entry = self.detector.find(frame,"entry")
        if not entry:
            raise ValueError("Không thấy nút Rương ở sảnh sự kiện.")
        self._tap(frame,entry)
        return self._stable_state()

    def _stable_state(self,expected_kind=None):
        deadline,previous = self.clock()+self.timeout,None
        while self.clock()<deadline:
            frame = self._observe()
            state = self.detector.state(frame,self.last_png,self.folder)
            if state is not None and (expected_kind is None or state.kind==expected_kind):
                if state==previous:
                    return frame,state
                previous = state
            else:
                previous = None
            self.sleeper(.4)
        raise TimeoutError("Chưa đọc ổn định loại rương, số lượng, level hoặc EXP; không gửi thêm thao tác.")

    def _select_type(self,kind):
        frame,state = self._stable_state()
        if state.kind!=kind:
            tab = self.detector.find(frame,f"tab_{kind}")
            if not tab:
                raise ValueError("Không xác nhận được tab rương cần chọn.")
            self._tap(frame,tab)
            frame,state = self._stable_state(kind)
        return frame,state

    def _after_action(self,old,action):
        deadline,previous = self.clock()+self.timeout,None
        reward_streak,closed = 0,False
        while self.clock()<deadline:
            frame = self._observe()
            if self.detector.find(frame,"reward_title"):
                previous = None
                reward_streak += 1
                if reward_streak>=2 and not closed:
                    self._save("reward_last")
                    self._dismiss_reward(frame);closed=True
                self.sleeper(.4)
                continue
            reward_streak = 0
            state = self.detector.state(frame,self.last_png,self.folder)
            if state is not None:
                if state.kind!=old.kind:
                    raise ValueError("Loại rương thay đổi ngoài dự kiến; dừng.")
                if state==old:
                    previous = None
                else:
                    if state!=previous:
                        previous=state
                        self.sleeper(.4)
                        continue
                    if action=="open":
                        expected = old.expected_open
                        consumed = old.quantity-state.quantity
                        gained = old.exp+consumed*old.exp_per_chest
                        if (not 0<consumed<=expected or state.level!=old.level or
                                state.exp not in {gained,min(old.exp_needed,gained)}):
                            raise ValueError("Số rương/EXP thay đổi chưa khớp lần mở; dừng trước lệnh tiếp theo.")
                    elif state.level!=old.level+1 or state.quantity!=old.quantity or state.exp!=old.exp:
                        raise ValueError("Chưa xác minh level rương tăng đúng một và số rương giữ nguyên; dừng.")
                    return frame,state
            else:
                previous = None
            self.sleeper(.4)
        raise TimeoutError("Chưa xác nhận kết quả mở/nâng level rương; không gửi lại lệnh.")

    def run(self,*,max_actions=500):
        self.folder = self.evidence_root/uuid.uuid4().hex
        self.records,self.pending_action,self.last_png = {},"",b""
        actions = 0
        try:
            if not isinstance(max_actions,int) or isinstance(max_actions,bool) or max_actions<1:
                raise ValueError("Giới hạn thao tác phải là số nguyên dương.")
            self._check()
            if not self.detector.ready:
                return self._finish_chest("needs_samples","Thiếu mẫu nhận diện rương.")
            self._open_page()
            stopped = set()
            for _ in range(10):
                actions_before = actions
                for kind in range(4):
                    frame,state = self._select_type(kind)
                    record = self.records.setdefault(kind,ChestTypeResult(kind,CHESTS[kind],state.quantity,state.quantity,state.level,state.level))
                    record.remaining,record.final_level = state.quantity,state.level
                    if kind in stopped:
                        continue
                    self._save(f"type_{kind}_before")
                    while True:
                        self._check()
                        record.remaining,record.final_level = state.quantity,state.level
                        if state.exp>=state.exp_needed:
                            action,target = "upgrade",self.detector.find(frame,"upgrade_on")
                            if not state.upgrade_enabled or not target:
                                record.reason="cannot_upgrade";stopped.add(kind);break
                        elif state.quantity==0:
                            record.reason="exhausted";break
                        elif not state.open_enabled:
                            record.reason="cannot_open";stopped.add(kind);break
                        else:
                            action,target = "open",self.detector.find(frame,"open_label")
                            if not target or state.expected_open<=0:
                                raise ValueError("Chưa xác nhận được số rương cần mở hoặc nút Mở.")
                        if actions>=max_actions:
                            return self._finish_chest("blocked","Đã hết giới hạn thao tác của lượt; chưa coi là hết rương.")
                        self._save(f"type_{kind}_before_action_{actions+1:03d}")
                        self.progress(f"Rương {CHESTS[kind]}: " + (f"tăng level {state.level} → {state.level+1}…" if action=="upgrade"
                            else f"mở tối đa {state.expected_open}/{state.quantity}, level {state.level}…"))
                        old = state
                        self.pending_action = f"{action}:type_{kind}"
                        self._tap(frame,target);actions+=1
                        frame,state = self._after_action(old,action)
                        if action=="open":
                            record.opened += old.quantity-state.quantity;record.open_actions+=1
                        else:
                            record.level_ups+=1
                        record.remaining,record.final_level = state.quantity,state.level
                        self.pending_action = ""
                        self._save(f"type_{kind}_after_action_{actions:03d}")
                    reason_text = {"exhausted":"đã hết rương", "cannot_open":"nút Mở không khả dụng",
                                   "cannot_upgrade":"đủ EXP nhưng chưa thể tăng level"}[record.reason]
                    self.progress(f"Rương {CHESTS[kind]}: còn {record.remaining}, level {record.final_level}; {reason_text}.")
                    self._save(f"type_{kind}_result")
                if actions==actions_before:
                    remaining = sum(r.remaining for r in self.records.values())
                    complete = remaining==0 and not stopped
                    status = "success" if complete else "partial"
                    opened = sum(r.opened for r in self.records.values())
                    return self._finish_chest(status,f"Đã kiểm tra 4 loại rương; mở {opened} rương, còn {remaining}." +
                        (" Đã hết rương." if complete else " Một số loại không thể mở/nâng level theo trạng thái hiện tại."))
            return self._finish_chest("blocked","Đã hết giới hạn kiểm tra lại rương mới; giữ ảnh để kiểm tra.")
        except InterruptedError:
            return self._finish_chest("cancelled","Đã dừng mở rương theo yêu cầu.")
        except TimeoutError as exc:
            return self._finish_chest("blocked",str(exc))
        except Exception as exc:
            return self._finish_chest("error",str(exc))
