import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import cv2
import numpy as np

from advance_skill import AdvanceResult,AdvanceState,ResourceCount,ScreenNumbers
from treasure_skill import TreasureDetector,TreasureSkill,TeamTreasureSkill
from login_engine import Match
from test_advance_skill import World
from test_equipment_team import ModelTeam,TeamWorld

class TreasureWorld(World):
    def __init__(self,stones=500,silver=100000,empty=False,**kwargs):
        super().__init__(rank=0,resources=(ResourceCount("stones",stones,50),
                                         ResourceCount("silver",silver,5000)),**kwargs)
        self.empty=empty

    def find(self,frame,name,*args):
        if name=="formation_title" and self.empty:
            return Match(name,10,10,20,20,1)
        return super().find(frame,name,*args)

    def slot(self,frame):
        return None if self.empty else Match("treasure_slot",745,453,2,2,1)

class ModelTreasure(TreasureSkill):
    def _open_tab(self):
        self.is_main=False
        return self._observe()

class TreasureTests(unittest.TestCase):
    def run_world(self,w,target=None,stop=None):
        with tempfile.TemporaryDirectory() as folder:
            skill=ModelTreasure(w,detector=w,roster_detector=w,navigation_detector=w,
                clock=lambda:w.time,sleeper=w.sleep,timeout=3,evidence_root=Path(folder),stop=stop)
            result=skill._run_in_event(target)
            data=json.loads((Path(result.evidence_dir)/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["upgrades"],result.upgrades)
            return result

    def test_upgrade_consumes_stones_and_silver_then_stops_at_target(self):
        w=TreasureWorld()
        r=self.run_world(w,1)
        self.assertEqual((r.initial_rank,r.final_rank,r.upgrades,r.reason),(0,1,1,"target_reached"))
        self.assertEqual((w.resources[0].available,w.resources[1].available),(450,95000))
        self.assertEqual(len(w.actions),1)

    def test_repeated_upgrades_do_not_overshoot(self):
        w=TreasureWorld()
        r=self.run_world(w,2)
        self.assertEqual((r.final_rank,r.upgrades,len(w.actions)),(2,2,2))

    def test_passive_stops_when_stones_run_out(self):
        w=TreasureWorld(stones=100)
        r=self.run_world(w)
        self.assertEqual((r.reason,r.upgrades),("missing_stones",2))
        self.assertIn("Đá Tiến Cấp Bảo Vật",r.message)

    def test_missing_silver_is_not_mislabelled_as_hero_fragments(self):
        w=TreasureWorld(silver=4999)
        r=self.run_world(w)
        self.assertEqual(r.reason,"missing_silver")
        self.assertIn("Bạc",r.message)
        self.assertFalse(w.actions)

    def test_missing_stones_never_clicks_purchase_or_upgrade(self):
        w=TreasureWorld(stones=49)
        self.assertEqual(self.run_world(w).reason,"missing_stones")
        self.assertFalse(w.actions)

    def test_missing_duplicate_stops_without_spending(self):
        w=TreasureWorld()
        w.resources+=(ResourceCount("copies",0,1),)
        r=self.run_world(w)
        self.assertEqual(r.reason,"missing_copies")
        self.assertIn("bảo vật trùng loại",r.message)
        self.assertFalse(w.actions)

    def test_empty_equipment_slot_is_skipped(self):
        w=TreasureWorld(empty=True)
        self.assertEqual(self.run_world(w).reason,"no_treasure")
        self.assertFalse(w.actions)

    def test_already_at_target_does_not_spend(self):
        w=TreasureWorld()
        self.assertEqual(self.run_world(w,0).reason,"target_reached")
        self.assertFalse(w.actions)

    def test_game_cap_even_with_bright_button_does_not_spend(self):
        w=TreasureWorld(cap=True)
        self.assertEqual(self.run_world(w).reason,"max_rank")
        self.assertFalse(w.actions)

    def test_unknown_or_unchanged_result_never_retries(self):
        for fail in ("unknown","unchanged"):
            w=TreasureWorld(fail=fail)
            self.assertEqual(self.run_world(w).status,"blocked")
            self.assertEqual(len(w.actions),1)

    def test_stone_decrement_must_match_cost_before_second_input(self):
        w=TreasureWorld()
        original=w.tap
        def tap(*args):
            original(*args)
            w.resources=(ResourceCount("stones",460,50),w.resources[1])
        w.tap=tap
        self.assertEqual(self.run_world(w,2).status,"error")
        self.assertEqual(len(w.actions),1)

    def test_costs_can_increase_between_ranks(self):
        w=TreasureWorld()
        original=w.tap
        def tap(*args):
            original(*args)
            w.resources=tuple(ResourceCount(r.kind,r.available,r.required+(50 if r.kind=="stones" else 5000))
                              for r in w.resources)
        w.tap=tap
        r=self.run_world(w,2)
        self.assertEqual((r.final_rank,w.resources[0].available,w.resources[1].available),(2,350,85000))

    def test_cancel_interrupts_before_another_input(self):
        stop=threading.Event();w=TreasureWorld();w.stop=stop
        self.assertEqual(self.run_world(w,2,stop).status,"cancelled")
        self.assertEqual(len(w.actions),1)

    def test_public_entry_requires_event_verification(self):
        w=TreasureWorld()
        with tempfile.TemporaryDirectory() as folder:
            skill=ModelTreasure(w,detector=w,roster_detector=w,navigation_detector=w,evidence_root=Path(folder))
            skill.gate=SimpleNamespace(last_png=b"",enter=Mock(side_effect=TimeoutError("event not verified")))
            self.assertEqual(skill.run(target_rank=1).reason,"event_not_verified")
            self.assertFalse(w.actions)

class TreasureTeamModel(TeamTreasureSkill,ModelTeam):
    def _formation(self):
        self.device.proved=True
        return self._observe()

    def _make_hero_skill(self,index):
        w=self.device
        class Child:
            last_png=b""
            def _run_in_event(child,target):
                assert w.proved
                w.processed.append((w.selected,target))
                if w.selected==2:
                    return AdvanceResult("no_action","empty","no_treasure")
                return AdvanceResult("success","done","target_reached",0,1,1)
            def return_to_formation(child): pass
        return Child()

class TreasureTeamTests(unittest.TestCase):
    def test_six_heroes_include_main_skip_empty_and_use_same_target(self):
        w=TeamWorld(count=6)
        with tempfile.TemporaryDirectory() as folder:
            skill=TreasureTeamModel(w,detector=w,treasure_detector=w,navigation_detector=w,
                clock=lambda:w.time,sleeper=w.sleep,timeout=5,evidence_root=Path(folder))
            r=skill.run(target_rank=1)
            self.assertEqual(w.processed,[(i,1) for i in range(6)])
            self.assertEqual((r.processed,r.changed,r.status),(6,5,"success"))
            self.assertIn("cường hóa bảo vật",r.message)

class TreasureScreenshotTests(unittest.TestCase):
    def frame(self,name):
        png=(Path(__file__).parent/"fixtures/treasure"/(name+".png")).read_bytes()
        d=TreasureDetector()
        return d,d.decode(png),png

    def test_materials_rank_and_displayed_silver_lower_bound(self):
        d,f,png=self.frame("upgrade_before")
        class Numbers(ScreenNumbers):
            def read(self,*args):
                return [dict(text="12139/50",x=663,y=379,w=60,h=18),
                        dict(text="5000",x=768,y=439,w=36,h=18),
                        dict(text="14759",x=954,y=12,w=35,h=18),
                        dict(text="vpn",x=992,y=12,w=25,h=18)]
        d.numbers=Numbers()
        s=d.state(f,png,Path("."))
        self.assertEqual((s.rank,s.next_rank),(0,1))
        self.assertEqual(s.resources,(ResourceCount("stones",12139,50),
                                     ResourceCount("silver",147590000,5000)))
        self.assertTrue(s.enabled)

    def test_after_rank_one_reads_five_digit_cost_and_van_unit_even_if_ocr_omits_unit(self):
        d,f,png=self.frame("upgrade_after_1")
        class Numbers(ScreenNumbers):
            def read(self,*args):
                return [dict(text="1",x=746,y=91,w=10,h=18),
                        dict(text="12089/100",x=663,y=379,w=70,h=18),
                        dict(text="10000",x=768,y=438,w=42,h=18),
                        dict(text="14758",x=955,y=12,w=33,h=18)]
        d.numbers=Numbers()
        s=d.state(f,png,Path("."))
        self.assertEqual((s.rank,s.next_rank),(1,2))
        self.assertEqual(s.resources,(ResourceCount("stones",12089,100),
                                     ResourceCount("silver",147580000,10000)))

    def test_unrecognized_unit_cannot_be_treated_as_plain_silver_when_ocr_drops_it(self):
        d,f,_=self.frame("upgrade_before")
        original=d.find
        d.find=lambda frame,name,*args: None if name=="silver_unit_van" else original(frame,name,*args)
        word=dict(text="14759",x=954,y=12,w=35,h=18)
        self.assertIsNone(d._balance(f,[word]))

    def copy_words(self):
        return [dict(text="18",x=746,y=91,w=16,h=19),
                dict(text="19",x=876,y=90,w=17,h=19),
                dict(text="12089/950",x=855,y=379,w=60,h=16),
                dict(text="95000",x=768,y=439,w=42,h=17),
                dict(text="14758",x=954,y=12,w=33,h=15)]

    def test_duplicate_treasure_requirement_missing_is_detected(self):
        d,f,png=self.frame("upgrade_requires_copy")
        d.numbers=ScreenNumbers();d.numbers.read=Mock(return_value=self.copy_words())
        s=d.state(f,png,Path("."))
        self.assertEqual((s.rank,s.next_rank),(18,19))
        self.assertEqual(s.resources,(ResourceCount("stones",12089,950),
                                     ResourceCount("silver",147580000,95000),
                                     ResourceCount("copies",0,1)))

    def test_unreadable_extra_requirement_never_allows_upgrade(self):
        d,f,png=self.frame("upgrade_requires_copy")
        f[375:402,655:759]=0
        d.numbers=ScreenNumbers();d.numbers.read=Mock(return_value=self.copy_words())
        self.assertIsNone(d.state(f,png,Path(".")))

    def test_sufficient_duplicate_count_can_be_read_from_ocr(self):
        d,f,png=self.frame("upgrade_requires_copy")
        f[375:402,655:759]=0
        d.numbers=ScreenNumbers();d.numbers.read=Mock(return_value=self.copy_words()+
            [dict(text="2/1",x=663,y=379,w=25,h=17)])
        s=d.state(f,png,Path("."))
        self.assertEqual(s.resources[-1],ResourceCount("copies",2,1))

    def test_slash_must_be_confirmed_in_alternative_full_frame(self):
        d,f,png=self.frame("upgrade_after_1")
        good=[dict(text="1",x=746,y=91,w=10,h=18),
              dict(text="11989/100",x=663,y=379,w=70,h=18),
              dict(text="10000",x=768,y=438,w=42,h=18),
              dict(text="14758",x=955,y=12,w=33,h=18)]
        bad=[dict(w,text="11989100") if "/" in w["text"] else w for w in good]
        d.numbers=ScreenNumbers();d.numbers.read=Mock(side_effect=[bad,bad,good])
        s=d.state(f,png,Path("."))
        self.assertEqual(s.resources[0],ResourceCount("stones",11989,100))
        self.assertEqual(d.numbers.read.call_count,3)
        d.numbers.read=Mock(return_value=bad)
        self.assertIsNone(d.state(f,png,Path(".")))

    def test_filled_slot_is_lower_right_equipment_not_skill_icon(self):
        d,f,_=self.frame("formation_filled")
        slot=d.slot(f)
        self.assertTrue(735<slot.center[0]<755 and 440<slot.center[1]<470)

    def test_known_unequipped_placeholder_is_skipped(self):
        d,f,_=self.frame("formation_empty")
        self.assertIsNone(d.slot(f))

    def test_unknown_money_unit_is_not_guessed(self):
        d,f,_=self.frame("upgrade_before")
        f[0:40,895:1048]=0
        words=[dict(text="2",x=954,y=12,w=10,h=18),
               dict(text="unknown",x=992,y=12,w=30,h=18)]
        self.assertIsNone(d._balance(f,words))

if __name__=="__main__":
    unittest.main()
