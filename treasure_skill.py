"""Time Machine treasure upgrade: visual detector and shared advance contract."""
from __future__ import annotations
import re
import uuid
from pathlib import Path
import cv2
import numpy as np
from advance_skill import (AdvanceDetector, AdvanceSkill, AdvanceState, ResourceCount,
                          TeamAdvanceSkill)
from equipment_skill import EquipmentDetector
from login_engine import Match

ROOT = Path(__file__).resolve().parent

class TreasureDetector(AdvanceDetector):
    REGIONS = {
        "treasure_title": (0,0,.29,.13),
        "advance_tab": (.20,.86,.44,1),
        "advance_heading": (.52,.12,.71,.22),
        "advance_button": (.64,.74,.83,.87),
        "stone_label": (.60,.56,.91,.70),
        "silver_cost_icon": (.66,.70,.75,.80),
        "silver_unit_van": (.86,0,.99,.07),
        "rank_0": (.69,.14,.74,.21),
        "rank_1": (.69,.14,.74,.21),
        "treasure_empty": (.60,.60,.80,.87),
        "missing_copy": (.61,.62,.72,.69),
    }

    def __init__(self,asset_dir=None,numbers=None,context=None,roster=None):
        # Keep treasure-specific numeric layout separate from hero advancement.
        super().__init__(asset_dir or ROOT/"assets/treasure",numbers=numbers)
        self.context = context or AdvanceDetector()
        self.roster = roster or EquipmentDetector()
        self.rank_digits = {k:list(v) for k,v in self.roster.digits.items()}
        for path in (asset_dir or ROOT/"assets/treasure").glob("treasure_digit_*.png"):
            glyph=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),0)
            self.rank_digits[int(path.stem[-1])].append(glyph>127)

    @property
    def ready(self):
        return set(self.REGIONS) <= self.templates.keys() and self.context.ready and self.roster.ready

    def find(self,frame,name,threshold=.87):
        if name == "hero_title":
            return super().find(frame,"treasure_title",threshold) or self.context.find(frame,name,threshold)
        if name == "rank_cap":
            return self.context.find(frame,name,threshold)
        if name in {"back","event_context"}:
            return self.context.find(frame,name,threshold)
        return super().find(frame,name,threshold)

    def is_advance(self,frame):
        return bool(self.find(frame,"treasure_title") and self.find(frame,"advance_heading")
                    and self.find(frame,"advance_tab"))

    def slot(self,frame):
        if not self.roster.find(frame,"formation_title"):
            raise ValueError("Chưa xác nhận màn hình Đội Hình để mở bảo vật.")
        gear = self.roster.find(frame,"equipment_menu")
        if not gear:
            raise ValueError("Chưa xác nhận mốc Cường Hóa Trang Bị.")
        x,y = gear.center[0]+214,gear.center[1]-120
        roi = frame[y-39:y+39,x-39:x+39]
        if roi.shape[:2] != (78,78):
            raise ValueError("Ô bảo vật nằm ngoài vùng quan sát.")
        gray = cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
        if any(t.shape[0]<=78 and t.shape[1]<=78 and
               cv2.minMaxLoc(cv2.matchTemplate(gray,t,cv2.TM_CCOEFF_NORMED))[1]>=.92
               for t,_ in self.scaled["treasure_empty"]):
            return None
        if float(gray.std()) < 18:
            raise ValueError("Chưa xác nhận ô bảo vật có trang bị; chưa bấm.")
        return Match("treasure_slot",x-1,y-1,2,2,1.)

    def _rank_number(self,frame,box,green=False):
        x1,y1,x2,y2=box
        roi=frame[y1:y2,x1:x2]
        mask=(cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(35,80,100),(90,255,255))
              if green else cv2.inRange(roi,(165,165,165),(255,255,255)))
        cs,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        boxes=sorted(cv2.boundingRect(c) for c in cs if cv2.boundingRect(c)[3]>=9)
        if not 1<=len(boxes)<=3:
            return None
        text=""
        for x,y,w,h in boxes:
            glyph=cv2.resize(mask[y:y+h,x:x+w],(18,28),interpolation=cv2.INTER_NEAREST)>127
            scores=sorted((min(float(np.mean(glyph!=sample)) for sample in samples),digit)
                          for digit,samples in self.rank_digits.items())
            if scores[0][0]>.18 or scores[1][0]-scores[0][0]<.025:
                return None
            text+=str(scores[0][1])
        return int(text)

    def _balance(self,frame,words):
        offset = frame.shape[1]-1061
        items=[w for w in words if self.numbers.in_box(w,(895+offset,0,1048+offset,40))]
        digits=[w["text"] for w in items if re.fullmatch(r"[0-9]{1,12}",w["text"])]
        if len(digits)!=1:
            return None
        value=int(digits[0])
        if self.find(frame,"silver_unit_van",.92):
            # The game rounds down its display in Vạn; use the lower bound.
            return value*10000
        if len(items)!=1:
            return None
        word=items[0]
        # A missing OCR unit is not proof that the number is unscaled.
        start=max(895+offset,round(word["x"]+word["w"])+2)
        tail=frame[4:35,start:1048+offset]
        if tail.size:
            mask=cv2.inRange(tail,(165,165,165),(255,255,255))
            cs,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            if any(cv2.boundingRect(c)[3]>=8 and cv2.boundingRect(c)[2]>=2 for c in cs):
                return None
        return value

    def state(self,frame,png,folder,is_main=False):
        if not self.is_advance(frame):
            return None
        words=self.numbers.read(png,folder)
        offset=frame.shape[1]-1061
        rank=self.numbers.integer(words,(736+offset,85,770+offset,116))
        if rank is None:
            rank=self._rank_number(frame,(736+offset,85,770+offset,116))
        if rank is None:
            rank=next((n for n in (0,1) if self.find(frame,f"rank_{n}",.96)),None)
        if rank is None:
            return None
        if self.find(frame,"rank_cap",.92):
            return AdvanceState(rank,None,capped=True,enabled=False)
        next_rank=self.numbers.integer(words,(870+offset,85,904+offset,116))
        if next_rank is None:
            next_rank=self._rank_number(frame,(870+offset,85,904+offset,116),True)
        stone=self.find(frame,"stone_label")
        if not stone:
            return None
        two_items=stone.center[0]>800+offset
        stone_box=((848+offset,374,990+offset,404) if two_items
                   else (655+offset,374,838+offset,404))
        copy_box=(655+offset,374,759+offset,404)
        copies=self.numbers.resources(words,copy_box,True) if two_items else None
        if two_items and copies is None and self.find(frame,"missing_copy",.96):
            copies=(ResourceCount("copies",0,1),)
        counts=self.numbers.resources(words,stone_box,True)
        cost=self.numbers.integer(words,(765+offset,432,826+offset,463),max_digits=12)
        balance=self._balance(frame,words)
        if next_rank is None or counts is None or cost is None or balance is None or (two_items and copies is None):
            raw=cv2.imdecode(np.frombuffer(png,np.uint8),1)
            small=cv2.resize(raw,(round(raw.shape[1]*720/raw.shape[0]),720),interpolation=cv2.INTER_AREA)
            secondary=self.numbers.read(cv2.imencode(".png",small)[1].tobytes(),folder)
            if next_rank is None:
                next_rank=self.numbers.integer(secondary,(870+offset,85,904+offset,116))
            if counts is None:
                counts=self.numbers.resources(secondary,stone_box,True)
            if cost is None:
                cost=self.numbers.integer(secondary,(765+offset,432,826+offset,463),max_digits=12)
            if balance is None:
                balance=self._balance(frame,secondary)
            if two_items and copies is None:
                copies=self.numbers.resources(secondary,copy_box,True)
        if counts is None or (two_items and copies is None):
            # Some digit combinations lose the slash at 1080p and 720p.
            # Re-read a full UI frame; never split an unseparated OCR integer.
            raw=cv2.imdecode(np.frombuffer(png,np.uint8),1)
            alternative=cv2.resize(raw,(round(raw.shape[1]*900/raw.shape[0]),900),interpolation=cv2.INTER_AREA)
            third=self.numbers.read(cv2.imencode(".png",alternative)[1].tobytes(),folder)
            if counts is None:
                counts=self.numbers.resources(third,stone_box,True)
            if two_items and copies is None:
                copies=self.numbers.resources(third,copy_box,True)
        if (next_rank != rank+1 or counts is None or cost is None or cost<=0 or balance is None
                or (two_items and copies is None) or not self.find(frame,"silver_cost_icon")):
            return None
        resources=(ResourceCount("stones",counts[0].available,counts[0].required),
                   ResourceCount("silver",balance,cost))
        if two_items:
            resources+=(ResourceCount("copies",copies[0].available,copies[0].required),)
        return AdvanceState(rank,next_rank,resources,enabled=bool(self.find(frame,"advance_button")))

class TreasureSkill(AdvanceSkill):
    name = "upgrade_treasure"
    subject_label = "Bảo vật"
    resource_names = {"stones":"Đá Tiến Cấp Bảo Vật","silver":"Bạc","copies":"bảo vật trùng loại"}

    def __init__(self,device,*,detector=None,**kwargs):
        kwargs.setdefault("evidence_root",ROOT/"runtime/treasure")
        super().__init__(device,detector=detector or TreasureDetector(),**kwargs)

    def _open_tab(self):
        deadline,opened,tab_sent=self.clock()+self.timeout,False,False
        self.is_main=False
        while self.clock()<deadline:
            frame=self._observe()
            if self.detector.is_advance(frame):
                return frame
            if self.detector.find(frame,"treasure_title"):
                tab=self.detector.find(frame,"advance_tab")
                if tab and not tab_sent:
                    self._tap(frame,tab);tab_sent=True
            elif self.roster.find(frame,"formation_title") and not opened:
                selected=[c for c in self.roster.visible_heroes(frame) if c.selected]
                if len(selected)!=1:
                    raise ValueError("Chưa xác nhận đúng tướng có bảo vật cần nâng.")
                slot=self.detector.slot(frame)
                if slot is None:
                    raise ValueError("Tướng chưa trang bị bảo vật.")
                self._tap(frame,slot);opened=True
            self.sleeper(.6)
        raise TimeoutError("Không mở được tab nâng bảo vật; chưa dùng đá hoặc Bạc.")

    def _run_in_event(self,target_rank=None):
        self.folder=self.evidence_root/uuid.uuid4().hex
        self.initial_rank=self.final_rank=None
        self.upgrades,self.last_resources=0,()
        self.last_png=b""
        try:
            self.validate_target(target_rank)
            self._check()
            if not self.detector.ready:
                return self._finish_advance("needs_samples","missing_templates","Thiếu mẫu nhận diện Bảo Vật.")
            frame=self._observe()
            if self.roster.find(frame,"formation_title") and self.detector.slot(frame) is None:
                return self._finish_advance("no_action","no_treasure","Tướng chưa trang bị bảo vật; bỏ qua.")
        except InterruptedError:
            return self._finish_advance("cancelled","cancelled","Đã dừng trước khi nâng bảo vật.")
        except Exception as exc:
            return self._finish_advance("blocked","unverified",str(exc))
        return super()._run_in_event(target_rank)

    def _after_click(self,old_rank):
        frame,state=super()._after_click(old_rank)
        old=next((r for r in self.last_resources if r.kind=="stones"),None)
        new=next((r for r in state.resources if r.kind=="stones"),None)
        if old is not None and new is not None and old.available-new.available != old.required:
            raise ValueError("Bậc đã thay đổi nhưng số đá chưa khớp chi phí; dừng trước thao tác tiếp theo.")
        return frame,state

class TeamTreasureSkill(TeamAdvanceSkill):
    name = "upgrade_team_treasure"
    action_name = "cường hóa bảo vật"

    def __init__(self,*args,treasure_detector=None,**kwargs):
        kwargs.setdefault("evidence_root",ROOT/"runtime/treasure")
        super().__init__(*args,advance_detector=treasure_detector or TreasureDetector(),**kwargs)

    def _make_hero_skill(self,index):
        return TreasureSkill(self.device,detector=self.advance_detector,roster_detector=self.detector,
            stop=self.stop,progress=lambda text:self.progress(f"Tướng {index}/6: {text}"),
            preview=self.preview,navigation_detector=self.navigation,clock=self.clock,
            sleeper=self.sleeper,timeout=self.timeout,evidence_root=self.folder/f"hero_{index:02d}")

