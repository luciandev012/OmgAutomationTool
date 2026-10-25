import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import cv2
import numpy as np
from advance_skill import (AdvanceSkill,AdvanceState,AdvanceDetector,ResourceCount,
                           ScreenNumbers,TeamAdvanceSkill,AdvanceResult,EventFormationGate)
from login_engine import Match
from test_equipment_team import ModelTeam,TeamWorld

PILL=ResourceCount("pills",10000,150)
SHARD=ResourceCount("fragments",100,40)

class World:
    ready=True
    def __init__(self,rank=1,resources=(PILL,),cap=False,condition=False,enabled=True,fail=None):
        self.rank,self.resources,self.cap=rank,resources,cap
        self.condition,self.enabled,self.fail=condition,enabled,fail
        self.time,self.actions=0,[]
        self.stop=None
    def sleep(self,n): self.time+=n
    def capture(self):
        return cv2.imencode(".png",np.zeros((597,1061,3),np.uint8))[1].tobytes()
    @staticmethod
    def decode(png): return cv2.imdecode(np.frombuffer(png,np.uint8),1)
    def find(self,frame,name,*args):
        if name=="advance_button": return Match(name,700,480,80,20,1)
    def state(self,*args):
        if self.fail=="unknown" and self.actions: return None
        if self.fail=="initial_unknown": return None
        return AdvanceState(self.rank,None if self.cap else self.rank+1,self.resources,
                            self.cap,self.enabled,self.condition)
    def tap(self,*args):
        self.actions.append(args)
        if self.fail not in ("unchanged","unknown"):
            self.rank += 2 if self.fail=="jump" else 1
            self.resources=tuple(ResourceCount(r.kind,r.available-r.required,r.required) for r in self.resources)
        if self.stop: self.stop.set()

class ModelAdvance(AdvanceSkill):
    def _open_tab(self):
        self.is_main=True
        return self._observe()

class AdvanceTests(unittest.TestCase):
    def run_world(self,world,target=None,stop=None,max_steps=100):
        with tempfile.TemporaryDirectory() as folder:
            skill=ModelAdvance(world,detector=world,roster_detector=world,navigation_detector=world,
                clock=lambda:world.time,sleeper=world.sleep,timeout=3,stop=stop,
                evidence_root=Path(folder),max_steps=max_steps)
            result=skill._run_in_event(target)
            report=json.loads((Path(result.evidence_dir)/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(report["upgrades"],result.upgrades)
            return result

    def test_target_stops_exactly_and_never_overshoots(self):
        w=World()
        r=self.run_world(w,3)
        self.assertEqual((r.reason,r.initial_rank,r.final_rank,r.upgrades),("target_reached",1,3,2))
        self.assertEqual(len(w.actions),2)

    def test_already_at_or_above_target_does_not_spend(self):
        for target in (0,7,10):
            w=World(rank=10,cap=True)
            r=self.run_world(w,target)
            self.assertEqual(r.reason,"target_reached")
            self.assertEqual(w.actions,[])

    def test_passive_stops_when_pills_run_out(self):
        w=World(resources=(ResourceCount("pills",300,150),))
        r=self.run_world(w)
        self.assertEqual((r.reason,r.upgrades),("missing_pills",2))

    def test_fragments_missing_stops_without_click(self):
        w=World(resources=(PILL,ResourceCount("fragments",265,640)))
        r=self.run_world(w)
        self.assertEqual(r.reason,"missing_fragments")
        self.assertEqual(w.actions,[])

    def test_orange_button_at_cap_is_never_clicked(self):
        w=World(rank=10,cap=True)
        self.assertEqual(self.run_world(w).reason,"max_rank")
        self.assertFalse(w.actions)

    def test_unmet_level_or_disabled_button_stops(self):
        for kw in ({"condition":True},{"enabled":False}):
            w=World(**kw)
            self.assertEqual(self.run_world(w).reason,"conditions_not_met")
            self.assertFalse(w.actions)

    def test_unchanged_rank_is_not_retried(self):
        w=World(fail="unchanged")
        r=self.run_world(w)
        self.assertEqual((r.status,len(w.actions)),("blocked",1))

    def test_unknown_result_is_not_retried(self):
        w=World(fail="unknown")
        self.assertEqual(self.run_world(w).status,"blocked")
        self.assertEqual(len(w.actions),1)

    def test_unexpected_rank_jump_is_an_error(self):
        w=World(fail="jump")
        self.assertEqual(self.run_world(w).status,"error")
        self.assertEqual(len(w.actions),1)

    def test_unknown_initial_screen_has_no_input(self):
        w=World(fail="initial_unknown")
        self.assertEqual(self.run_world(w).status,"blocked")
        self.assertFalse(w.actions)

    def test_stop_is_checked_after_one_input(self):
        stop=threading.Event()
        w=World()
        w.stop=stop
        self.assertEqual(self.run_world(w,stop=stop).status,"cancelled")
        self.assertEqual(len(w.actions),1)

    def test_budget_is_not_reported_as_game_cap(self):
        w=World()
        r=self.run_world(w,max_steps=2)
        self.assertEqual((r.reason,r.upgrades),("step_budget",2))

    def test_invalid_targets_never_send_input(self):
        for target in (-1,1000,True,1.5,"10"):
            w=World()
            self.assertEqual(self.run_world(w,target).status,"error")
            self.assertFalse(w.actions)

    def test_public_invalid_target_is_reported_before_navigation(self):
        w=World()
        with tempfile.TemporaryDirectory() as folder:
            skill=ModelAdvance(w,detector=w,roster_detector=w,navigation_detector=w,evidence_root=Path(folder))
            skill.gate=SimpleNamespace(enter=Mock())
            self.assertEqual(skill.run(target_rank=-1).reason,"invalid_target")
            skill.gate.enter.assert_not_called()
            self.assertFalse(w.actions)

    def test_public_run_requires_verified_event(self):
        w=World()
        with tempfile.TemporaryDirectory() as folder:
            skill=ModelAdvance(w,detector=w,roster_detector=w,navigation_detector=w,evidence_root=Path(folder))
            skill.gate=SimpleNamespace(last_png=b"",enter=Mock(side_effect=TimeoutError("event unavailable")))
            r=skill.run()
            self.assertEqual(r.reason,"event_not_verified")
            self.assertFalse(w.actions)

class NumberTests(unittest.TestCase):
    @staticmethod
    def word(text,x=650,y=392):
        return dict(text=text,x=x,y=y,w=40,h=15)
    def test_resources_distinguish_main_and_other_hero(self):
        words=[self.word("159860/12000"),self.word("265/640",875)]
        resources=ScreenNumbers.resources(words,(565,345,998,434),False)
        self.assertEqual(resources,(ResourceCount("pills",159860,12000),ResourceCount("fragments",265,640)))
        self.assertIsNone(ScreenNumbers.resources(words,(565,345,998,434),True))
        self.assertEqual(ScreenNumbers.resources(words[:1],(565,345,998,434),True)[0].kind,"pills")
    def test_ambiguous_numbers_and_zero_cost_are_rejected(self):
        self.assertIsNone(ScreenNumbers.integer([self.word("IO")],(0,0,1000,500)))
        self.assertIsNone(ScreenNumbers.resources([self.word("91643/0")],(0,0,1000,500),True))
        self.assertIsNone(ScreenNumbers.resources([self.word("I50/150")],(0,0,1000,500),True))
    def test_numeric_word_box_excludes_stats_and_inventory(self):
        words=[self.word("7",739,92),self.word("100",300,90)]
        self.assertEqual(ScreenNumbers.integer(words,(726,86,769,119)),7)

class TeamModel(TeamAdvanceSkill,ModelTeam):
    def _formation(self):
        self.device.event_verified=True
        return self._observe()
    def _make_hero_skill(self,index):
        world=self.device
        class Child:
            last_png=b""
            def _run_in_event(child,target):
                assert world.event_verified
                world.processed.append((world.selected,target))
                return AdvanceResult("no_action","at target","target_reached",10,10)
            def return_to_formation(child): pass
        return Child()

class TeamAdvanceTests(unittest.TestCase):
    def test_six_distinct_heroes_share_user_target(self):
        w=TeamWorld(count=6,selected=4)
        with tempfile.TemporaryDirectory() as folder:
            skill=TeamModel(w,detector=w,advance_detector=w,navigation_detector=w,
                clock=lambda:w.time,sleeper=w.sleep,timeout=5,evidence_root=Path(folder))
            r=skill.run(target_rank=10)
            self.assertEqual(w.processed,[(i,10) for i in range(6)])
            self.assertEqual((r.processed,r.status,r.changed),(6,"no_action",0))
    def test_gate_does_not_tap_unknown_screen(self):
        w=World()
        gate=EventFormationGate(w,detector=w,advance_detector=w,navigation_detector=w,
                               clock=lambda:w.time,sleeper=w.sleep)
        with self.assertRaises(TimeoutError): gate.enter()
        self.assertFalse(w.actions)


class ScreenshotTests(unittest.TestCase):
    def detect(self,name,is_main,rank,next_rank=None,counts=()):
        words=[dict(text=str(rank),x=739,y=92,w=20,h=20)]
        if next_rank is not None: words.append(dict(text=str(next_rank),x=876,y=92,w=12,h=20))
        for i,value in enumerate(counts):
            words.append(dict(text=value,x=659+214*i,y=392,w=90,h=18))
        class Numbers(ScreenNumbers):
            def read(self,*args): return words
        d=AdvanceDetector(numbers=Numbers())
        png=(Path(__file__).parent/"fixtures/advance"/(name+".png")).read_bytes()
        frame=d.decode(png)
        return d,frame,d.state(frame,png,Path("."),is_main)

    def test_main_pills_only_and_normal_layout_tab(self):
        d,f,s=self.detect("main_ready",True,1,2,("91643/150",))
        self.assertEqual(s.resources,(ResourceCount("pills",91643,150),))
        self.assertTrue(d.find(f,"advance_tab"))

    def test_capped_main_uses_exact_rank_template_for_ambiguous_ocr(self):
        d,f,s=self.detect("main_cap",True,"IO")
        self.assertEqual((s.rank,s.capped,s.enabled),(10,True,False))
        self.assertTrue(d.find(f,"advance_button"))

    def test_other_hero_shifted_tab_and_two_resource_costs(self):
        d,f,s=self.detect("other_blocked",False,7,8,("159860/12000","265/640"))
        self.assertEqual(s.resources[1],ResourceCount("fragments",265,640))
        self.assertTrue(d.find(f,"advance_tab").center[0]>390)


class RealmWorld(World):
    def __init__(self):
        super().__init__()
        self.scene="normal_formation"
        self.event_observations=0
    def find(self,frame,name,*args):
        shown={
            "normal_formation":("formation_title","equipment_menu","back"),
            "normal_lobby":("time_machine",),
            "event_lobby":("event_context","event_home","formation_entry"),
            "event_formation":("formation_title","equipment_menu","back"),
        }[self.scene]
        if name in shown: return Match(name,10,10,5,5,1)
    def capture(self):
        if self.scene=="event_lobby": self.event_observations+=1
        return super().capture()
    def visible_heroes(self,frame): return []
    def tap(self,*args):
        self.actions.append(self.scene)
        self.scene={"normal_formation":"normal_lobby","normal_lobby":"event_lobby",
                    "event_lobby":"event_formation"}[self.scene]

class RealmTests(unittest.TestCase):
    def test_normal_formation_must_return_and_verify_event_before_entering_formation(self):
        w=RealmWorld()
        gate=EventFormationGate(w,detector=w,advance_detector=w,navigation_detector=w,
                               clock=lambda:w.time,sleeper=w.sleep)
        gate.enter()
        self.assertEqual(w.actions,["normal_formation","normal_lobby","event_lobby"])
        self.assertGreaterEqual(w.event_observations,2)
        self.assertEqual(w.scene,"event_formation")

    def test_one_event_image_cannot_authorize_formation_entry(self):
        w=RealmWorld()
        w.scene="event_lobby"
        original=w.capture
        def capture():
            png=original()
            if w.event_observations>1: w.scene="normal_lobby"
            return png
        w.capture=capture
        # Remove all actionable navigation from normal lobby so it stays unknown.
        original_find=w.find
        w.find=lambda frame,name,*args: None if w.scene=="normal_lobby" else original_find(frame,name,*args)
        gate=EventFormationGate(w,detector=w,advance_detector=w,navigation_detector=w,
                               clock=lambda:w.time,sleeper=w.sleep)
        with self.assertRaises(TimeoutError): gate.enter()
        self.assertFalse(w.actions)

if __name__=="__main__": unittest.main()
