import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np

from advance_skill import ScreenNumbers
from chest_skill import ChestDetector, ChestSkill, ChestState
from login_engine import Match


class World:
    ready = True

    def __init__(self,counts=(253,4,0,7),failure=None):
        self.states = [ChestState(i,n,1,0,1000,5,100,True,False) for i,n in enumerate(counts)]
        self.kind,self.time,self.reward = 0,0,False
        self.failure,self.actions = failure,[]
        self.proved = False
        self.stop = None

    def capture(self):
        return cv2.imencode(".png",np.zeros((597,1061,3),np.uint8))[1].tobytes()

    def decode(self,png):
        return cv2.imdecode(np.frombuffer(png,np.uint8),1)

    def sleep(self,n):
        self.time+=n

    def find(self,frame,name,*args):
        if name=="reward_title":
            return Match(name,400,80,200,40,1) if self.reward else None
        return Match(name,500,500,20,20,1)

    def state(self,*args):
        if self.reward or self.failure=="initial_unknown" or (self.actions and self.failure=="unknown"):
            return None
        return self.states[self.kind]

    def apply(self,name):
        if name=="entry":
            self.kind=0
            return
        if name.startswith("tab_"):
            self.kind=int(name[-1])
            return
        assert self.proved
        self.actions.append((self.kind,name))
        if self.failure=="unchanged":
            return
        old=self.states[self.kind]
        if name=="open_label":
            amount=old.expected_open
            xp=min(old.exp_needed,old.exp+amount*old.exp_per_chest)
            quantity=old.quantity-amount
            if self.failure=="wrong_debit":
                quantity-=1
            if self.failure=="wrong_exp":
                xp+=1
            self.states[self.kind]=replace(old,quantity=quantity,exp=xp,upgrade_enabled=xp==old.exp_needed)
            self.reward=True
        elif name=="upgrade_on":
            self.states[self.kind]=replace(old,level=old.level+1,exp_needed=old.exp_needed+2000,
                                           batch=150,upgrade_enabled=False)
        if self.stop:
            self.stop.set()


class ModelChest(ChestSkill):
    def _event_lobby(self):
        if self.device.failure=="event_missing":
            raise TimeoutError("event not verified")
        self.device.proved=True
        return self._observe()

    def _tap(self,frame,match):
        self._check()
        self.device.apply(match.name)

    def _dismiss_reward(self,frame):
        self.device.reward=False


class ChestTests(unittest.TestCase):
    def run_world(self,w,**kwargs):
        with tempfile.TemporaryDirectory() as folder:
            skill=ModelChest(w,detector=w,navigation_detector=w,clock=lambda:w.time,sleeper=w.sleep,
                timeout=3,evidence_root=Path(folder),stop=w.stop)
            result=skill.run(**kwargs)
            report=json.loads((Path(result.evidence_dir)/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(report["opened"],result.opened)
            return result

    def test_all_four_chests_exhausted_and_levels_upgraded(self):
        w=World();r=self.run_world(w)
        self.assertEqual((r.status,r.opened,r.level_ups),("success",264,1))
        self.assertEqual([t.remaining for t in r.types],[0]*4)
        self.assertEqual([t.reason for t in r.types],["exhausted"]*4)
        self.assertEqual(w.actions[:4],[(0,"open_label"),(0,"open_label"),(0,"upgrade_on"),(0,"open_label")])

    def test_full_exp_is_upgraded_before_any_open(self):
        w=World((2,0,0,0));w.states[0]=replace(w.states[0],exp=1000,upgrade_enabled=True)
        r=self.run_world(w)
        self.assertEqual(w.actions[0],(0,"upgrade_on"))
        self.assertEqual((r.opened,r.level_ups),(2,1))

    def test_full_exp_can_upgrade_even_with_zero_chests(self):
        w=World((0,0,0,0));w.states[0]=replace(w.states[0],exp=1000,upgrade_enabled=True)
        r=self.run_world(w)
        self.assertEqual((r.status,r.opened,r.level_ups),("success",0,1))

    def test_empty_inventory_does_not_open_or_purchase_anything(self):
        w=World((0,0,0,0));r=self.run_world(w)
        self.assertEqual((r.status,r.opened),("success",0))
        self.assertFalse(w.actions)

    def test_last_batch_uses_only_remaining_chests(self):
        w=World((3,0,0,0));r=self.run_world(w)
        self.assertEqual((r.opened,len(w.actions)),(3,1))

    def test_batch_stops_at_exp_threshold_instead_of_assuming_label_count(self):
        w=World((120,0,0,0));w.states[0]=replace(w.states[0],exp=995)
        r=self.run_world(w)
        self.assertEqual((r.opened,r.level_ups),(120,1))
        self.assertEqual(w.actions[:2],[(0,"open_label"),(0,"upgrade_on")])

    def test_fractional_exp_threshold_uses_ceiling_and_clamps_exp(self):
        w=World((1,0,0,0));w.states[0]=replace(w.states[0],exp=999,exp_per_chest=6)
        r=self.run_world(w)
        self.assertEqual((r.opened,r.level_ups),(1,1))

    def test_overflow_exp_is_preserved_when_native_game_keeps_the_remainder(self):
        w=World((1,0,0,0));w.states[0]=replace(w.states[0],exp=999,exp_per_chest=6)
        original=w.apply
        def apply(name):
            original(name)
            if name=="open_label":
                w.states[0]=replace(w.states[0],exp=1005)
        w.apply=apply
        r=self.run_world(w)
        self.assertEqual((r.status,r.opened,r.level_ups),("success",1,1))
        self.assertEqual(w.states[0].exp,1005)

    def test_different_batch_and_exp_per_type_are_used(self):
        w=World((0,5,7,9))
        for i in range(1,4):
            w.states[i]=replace(w.states[i],batch=2+i,exp_per_chest=6+i)
        r=self.run_world(w)
        self.assertEqual((r.opened,[t.open_actions for t in r.types]),(21,[0,2,2,2]))

    def test_disabled_open_continues_other_types_and_reports_remaining(self):
        w=World((3,4,0,0));w.states[0]=replace(w.states[0],open_enabled=False)
        r=self.run_world(w)
        self.assertEqual((r.status,r.opened,r.types[0].remaining),("partial",4,3))
        self.assertEqual(r.types[0].reason,"cannot_open")
        self.assertTrue(all(kind!=0 for kind,name in w.actions))

    def test_full_exp_with_disabled_upgrade_never_wastes_open(self):
        w=World((3,0,0,0));w.states[0]=replace(w.states[0],exp=1000,upgrade_enabled=False)
        r=self.run_world(w)
        self.assertEqual((r.status,r.types[0].reason),("partial","cannot_upgrade"))
        self.assertFalse(w.actions)

    def test_unavailable_upgrade_is_reported_even_if_inventory_empty(self):
        w=World((0,0,0,0));w.states[0]=replace(w.states[0],exp=1000,upgrade_enabled=False)
        r=self.run_world(w)
        self.assertEqual((r.status,r.types[0].reason),("partial","cannot_upgrade"))

    def test_smaller_native_batch_is_validated_by_actual_quantity_and_exp(self):
        w=World((10,0,0,0));original=w.apply
        first=[True]
        def apply(name):
            original(name)
            if name=="open_label" and first[0]:
                w.states[0]=replace(w.states[0],quantity=5,exp=25)
                first[0]=False
        w.apply=apply
        r=self.run_world(w)
        self.assertEqual((r.status,r.opened,r.types[0].open_actions),("success",10,2))

    def test_no_progress_or_unreadable_result_is_never_retried(self):
        for failure in ("unchanged","unknown"):
            w=World((3,0,0,0),failure);r=self.run_world(w)
            self.assertEqual(r.status,"blocked")
            self.assertEqual(len(w.actions),1)
            self.assertEqual(r.pending_action,"open:type_0")

    def test_wrong_debit_or_exp_stops_before_any_other_open(self):
        for failure in ("wrong_debit","wrong_exp"):
            w=World((3,4,0,0),failure);r=self.run_world(w)
            self.assertEqual(r.status,"error")
            self.assertEqual(len(w.actions),1)

    def test_event_must_be_proved_before_resource_input(self):
        w=World(failure="event_missing");r=self.run_world(w)
        self.assertEqual(r.status,"blocked")
        self.assertFalse(w.actions)

    def test_unknown_initial_state_does_not_open(self):
        w=World(failure="initial_unknown");r=self.run_world(w)
        self.assertEqual(r.status,"blocked")
        self.assertFalse(w.actions)

    def test_stop_after_input_preserves_pending_state_without_repeating(self):
        w=World();w.stop=threading.Event();r=self.run_world(w)
        self.assertEqual((r.status,r.pending_action,len(w.actions)),("cancelled","open:type_0",1))

    def test_action_budget_is_not_reported_as_exhausted(self):
        w=World();r=self.run_world(w,max_actions=1)
        self.assertEqual(r.status,"blocked")
        self.assertEqual(r.opened,100)

    def test_invalid_budget_is_rejected_without_input(self):
        for maximum in (0,-1,True,1.5):
            w=World();self.assertEqual(self.run_world(w,max_actions=maximum).status,"error")
            self.assertFalse(w.actions)


class ScreenshotTests(unittest.TestCase):
    def load(self,name):
        png=(Path(__file__).parent/"fixtures/chest"/(name+".png")).read_bytes()
        d=ChestDetector()
        return d,d.decode(png),png

    def test_four_types_and_quantities_use_real_images(self):
        for i,quantity in enumerate((305,2010,215,210)):
            d,f,png=self.load(f"type_{i}")
            self.assertEqual((d.page_kind(f),d.quantity(f)),(i,quantity))
            self.assertTrue(d.find(f,f"tab_{i}"))

    def test_real_numbers_cover_different_levels_batch_sizes_and_exp(self):
        expected=((3,10000,18000,5,150),(1,0,4000,6,50),(3,12825,18000,15,60),(3,12000,18000,20,60))
        for i,(level,xp,needed,per,batch) in enumerate(expected):
            d,f,png=self.load(f"type_{i}")
            d.numbers.read=Mock(return_value=[dict(text=f"{xp}/{needed}",x=580,y=462,w=75,h=15)])
            s=d.state(f,png,Path("."))
            self.assertIsNotNone(s)
            self.assertEqual((s.level,s.exp,s.exp_needed,s.exp_per_chest,s.batch),(level,xp,needed,per,batch))
            self.assertTrue(s.open_enabled)
            self.assertFalse(s.upgrade_enabled)

    def test_full_exp_and_orange_upgrade_are_distinct_from_gray_button(self):
        d,f,png=self.load("chest_ready_upgrade")
        d.numbers.read=Mock(return_value=[dict(text="10000/10000",x=580,y=462,w=75,h=15)])
        s=d.state(f,png,Path("."))
        self.assertTrue(s.upgrade_enabled)
        self.assertIsNone(d.find(f,"upgrade_off"))
        self.assertEqual(s.expected_open,0)

    def test_reward_overlay_is_not_a_ready_chest_page(self):
        d,f,png=self.load("chest_reward_first")
        self.assertTrue(d.find(f,"reward_title"))
        self.assertIsNone(d.state(f,png,Path(".")))

    def test_exp_counter_without_separator_is_not_guessed(self):
        d,f,png=self.load("type_0")
        d.numbers.read=Mock(return_value=[dict(text="1000018000",x=580,y=462,w=75,h=15)])
        self.assertIsNone(d.state(f,png,Path(".")))

    def test_partial_or_punctuated_ocr_ratio_is_rejected_before_fallback(self):
        d,f,png=self.load("quantity_1860")
        bad=[dict(text="900/400();;;;",x=580,y=462,w=75,h=15)]
        good=[dict(text="900/4000",x=580,y=462,w=75,h=15)]
        d.numbers.read=Mock(side_effect=[bad,good])
        state=d.state(f,png,Path("."))
        self.assertEqual((state.exp,state.exp_needed),(900,4000))
        self.assertEqual(d.numbers.read.call_count,2)

    def test_unknown_quantity_never_allows_an_open(self):
        d,f,png=self.load("type_0");f[345:386,745:850]=0
        self.assertIsNone(d.state(f,png,Path(".")))

    def test_real_digit_nine_does_not_get_read_as_zero(self):
        for quantity,xp in ((1960,300),(1860,900)):
            d,f,png=self.load(f"quantity_{quantity}")
            d.numbers.read=Mock(return_value=[dict(text=f"{xp}/4000",x=580,y=462,w=75,h=15)])
            state=d.state(f,png,Path("."))
            self.assertEqual((state.kind,state.quantity,state.exp),(1,quantity,xp))

    def test_native_quantity_keeps_three_distinct_from_eight(self):
        d,f,png=self.load("native_1360")
        d.numbers.read=Mock(return_value=[dict(text="3900/4000",x=580,y=462,w=75,h=15)])
        self.assertEqual(d.quantity(f,png),1360)
        self.assertEqual(d.state(f,png,Path(".")).quantity,1360)

    def test_real_exp_can_exceed_threshold_before_upgrade(self):
        d,f,png=self.load("overflow_4002")
        d.numbers.read=Mock(return_value=[dict(text="4002/4000",x=580,y=462,w=75,h=15)])
        state=d.state(f,png,Path("."))
        self.assertEqual((state.quantity,state.exp,state.exp_needed),(1343,4002,4000))
        self.assertTrue(state.upgrade_enabled)
        self.assertEqual(state.expected_open,0)


if __name__=="__main__":
    unittest.main()
