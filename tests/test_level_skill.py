import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np

from level_skill import LevelDetector,LevelSkill,LevelState,LevelResult,TeamLevelSkill
from login_engine import Match
from test_equipment_team import ModelTeam,TeamWorld

class LevelWorld:
    ready = True
    def __init__(self,level=50,books=(0,0,0,12),exp=5690,mode="normal",cap=False,enabled=True):
        self.level,self.books,self.exp = level,books,exp
        self.mode,self.cap,self.enabled = mode,cap,enabled
        self.time,self.actions = 0,[]
        self.stop = None
        self.button = "level_button"
        self.button_names = []

    def sleep(self,n):
        self.time += n

    def capture(self):
        return cv2.imencode(".png",np.zeros((597,1061,3),np.uint8))[1].tobytes()

    @staticmethod
    def decode(png):
        return cv2.imdecode(np.frombuffer(png,np.uint8),1)

    def find(self,frame,name,*args):
        if name in {"level_button","level_batch_button"}:
            self.button = name
            return Match(name,600 if name == "level_batch_button" else 780,465,95,30,1)

    def state(self,*args):
        if self.mode == "initial_unknown" or (self.mode == "unknown" and self.actions):
            return None
        return LevelState(self.level,self.exp,33320,self.books,self.cap,self.enabled)

    def tap(self,*args):
        self.actions.append(args)
        self.button_names.append(self.button)
        size = 5 if self.button == "level_batch_button" else 1
        gain = min(size,self.books[3]//3)
        if self.mode == "late_cap":
            self.cap = True
        elif self.mode not in ("unchanged","unknown"):
            if self.mode == "partial" and len(self.actions)%2:
                self.exp += 100
            else:
                self.level += size+1 if self.mode == "jump" else gain
                self.exp = 3910
            if self.mode != "no_books_used":
                self.books = tuple(n-(3*gain if i==3 else 0) for i,n in enumerate(self.books))
        if self.mode == "upgrade_then_cap":
            self.cap = True
        if self.stop:
            self.stop.set()

class ModelLevel(LevelSkill):
    def _open_tab(self):
        return None if self.device.mode == "main" else self._observe()

class LevelTests(unittest.TestCase):
    def run_world(self,w,target=None,stop=None,limit=None,max_steps=300):
        with tempfile.TemporaryDirectory() as folder:
            skill = ModelLevel(w,detector=w,roster_detector=w,context_detector=w,navigation_detector=w,
                clock=lambda:w.time,sleeper=w.sleep,timeout=3,evidence_root=Path(folder),
                stop=stop,level_limit=limit,max_steps=max_steps)
            result = skill._run_in_event(target)
            data = json.loads((Path(result.evidence_dir)/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["actions"],result.actions)
            return result

    def test_one_button_can_consume_multiple_books_to_gain_exactly_one_level(self):
        w=LevelWorld()
        r=self.run_world(w,51)
        self.assertEqual((r.initial_level,r.final_level,r.actions,r.books_used),(50,51,1,(0,0,0,3)))
        self.assertEqual(r.reason,"target_reached")

    def test_target_at_last_budget_step_is_success(self):
        w=LevelWorld()
        self.assertEqual(self.run_world(w,51,max_steps=1).reason,"target_reached")

    def test_final_upgrade_that_reaches_cap_is_still_counted(self):
        w=LevelWorld(mode="upgrade_then_cap",books=(0,0,0,3))
        r=self.run_world(w)
        self.assertEqual((r.reason,r.actions,r.levels_gained,r.books_used),
                         ("level_cap",1,1,(0,0,0,3)))

    def test_prefers_five_button_when_five_levels_remain(self):
        w=LevelWorld(books=(0,0,0,30))
        r=self.run_world(w,55)
        self.assertEqual((r.final_level,r.actions,r.batch_actions,r.single_actions),(55,1,1,0))
        self.assertEqual(w.button_names,["level_batch_button"])

    def test_batch_then_single_inputs_stop_at_exact_target(self):
        w=LevelWorld(books=(0,0,0,30))
        r=self.run_world(w,57)
        self.assertEqual((r.final_level,r.actions,r.batch_actions,r.single_actions),(57,3,1,2))
        self.assertEqual(w.button_names,["level_batch_button","level_button","level_button"])

    def test_passive_uses_batches_until_books_are_empty(self):
        w=LevelWorld(books=(0,0,0,30))
        r=self.run_world(w)
        self.assertEqual((r.reason,r.actions,r.levels_gained),("missing_books",2,10))
        self.assertEqual(w.button_names,["level_batch_button","level_batch_button"])

    def test_partial_batch_is_recorded_when_only_two_levels_are_affordable(self):
        w=LevelWorld(books=(0,0,0,6))
        r=self.run_world(w,55)
        self.assertEqual((r.reason,r.levels_gained,r.batch_actions),("missing_books",2,1))

    def test_repeated_levels_stop_at_user_target(self):
        w=LevelWorld()
        r=self.run_world(w,53)
        self.assertEqual((r.final_level,r.levels_gained,len(w.actions)),(53,3,3))

    def test_already_at_or_above_target_sends_no_input(self):
        for target in (0,49,50):
            w=LevelWorld()
            self.assertEqual(self.run_world(w,target).reason,"target_reached")
            self.assertFalse(w.actions)

    def test_passive_stops_when_books_run_out(self):
        w=LevelWorld(books=(0,0,0,6))
        r=self.run_world(w)
        self.assertEqual((r.reason,r.actions,r.books_used),("missing_books",1,(0,0,0,6)))

    def test_no_books_never_opens_obtain_or_purchase(self):
        w=LevelWorld(books=(0,0,0,0))
        self.assertEqual(self.run_world(w).reason,"missing_books")
        self.assertFalse(w.actions)

    def test_main_hero_has_no_book_tab(self):
        w=LevelWorld(mode="main")
        self.assertEqual(self.run_world(w).reason,"main_hero")
        self.assertFalse(w.actions)

    def test_verified_cap_or_disabled_button_prevents_spending(self):
        for kw,reason in (({"cap":True},"level_cap"),({"enabled":False},"conditions_not_met")):
            w=LevelWorld(**kw)
            self.assertEqual(self.run_world(w).reason,reason)
            self.assertFalse(w.actions)

    def test_orchestrator_supplied_cap_is_respected(self):
        w=LevelWorld()
        self.assertEqual(self.run_world(w,limit=50).reason,"level_cap")
        self.assertFalse(w.actions)

    def test_partial_exp_progress_is_verified_before_next_input(self):
        w=LevelWorld(mode="partial")
        r=self.run_world(w,51)
        self.assertEqual((r.final_level,r.actions,r.books_used),(51,2,(0,0,0,6)))

    def test_level_change_without_book_decrease_is_not_confirmed(self):
        w=LevelWorld(mode="no_books_used")
        self.assertEqual(self.run_world(w,51).status,"blocked")
        self.assertEqual(len(w.actions),1)

    def test_unchanged_and_unknown_results_never_repeat_input(self):
        for mode in ("unchanged","unknown"):
            w=LevelWorld(mode=mode)
            self.assertEqual(self.run_world(w).status,"blocked")
            self.assertEqual(len(w.actions),1)

    def test_unexpected_multi_level_jump_stops_before_next_input(self):
        w=LevelWorld(mode="jump")
        self.assertEqual(self.run_world(w,51).status,"error")
        self.assertEqual(len(w.actions),1)

    def test_explicit_cap_after_input_stops(self):
        w=LevelWorld(mode="late_cap")
        self.assertEqual(self.run_world(w).reason,"level_cap")
        self.assertEqual(len(w.actions),1)

    def test_unknown_initial_numbers_do_not_spend(self):
        w=LevelWorld(mode="initial_unknown")
        self.assertEqual(self.run_world(w).status,"blocked")
        self.assertFalse(w.actions)

    def test_stop_checked_after_input(self):
        stop=threading.Event()
        w=LevelWorld();w.stop=stop
        self.assertEqual(self.run_world(w,stop=stop).status,"cancelled")
        self.assertEqual(len(w.actions),1)

    def test_input_budget_is_separate_from_game_limit(self):
        w=LevelWorld(books=(0,0,0,30))
        self.assertEqual(self.run_world(w,max_steps=1).reason,"step_budget")

    def test_invalid_targets_never_navigate(self):
        for target in (-1,True,1000,51.5,"51"):
            w=LevelWorld()
            with tempfile.TemporaryDirectory() as folder:
                skill=ModelLevel(w,detector=w,roster_detector=w,context_detector=w,
                    navigation_detector=w,evidence_root=Path(folder))
                skill.gate=SimpleNamespace(enter=Mock())
                self.assertEqual(skill.run(target_level=target).reason,"invalid_target")
                skill.gate.enter.assert_not_called()

    def test_public_entry_requires_event_proof(self):
        w=LevelWorld()
        with tempfile.TemporaryDirectory() as folder:
            skill=ModelLevel(w,detector=w,roster_detector=w,context_detector=w,navigation_detector=w,
                evidence_root=Path(folder))
            skill.gate=SimpleNamespace(last_png=b"",enter=Mock(side_effect=TimeoutError("event not verified")))
            self.assertEqual(skill.run().reason,"event_not_verified")
            self.assertFalse(w.actions)

class TeamLevelModel(TeamLevelSkill,ModelTeam):
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
                if w.selected==0:
                    return LevelResult("no_action","main","main_hero")
                if w.selected==2:
                    return LevelResult("no_action","empty","missing_books",50,50)
                return LevelResult("success","done","target_reached",50,51,1,1,(0,0,0,3))
            def return_to_formation(child): pass
        return Child()

class TeamLevelTests(unittest.TestCase):
    def test_team_skips_main_and_missing_books_and_visits_six_distinct_heroes(self):
        w=TeamWorld(count=6,selected=3)
        with tempfile.TemporaryDirectory() as folder:
            skill=TeamLevelModel(w,detector=w,level_detector=w,context_detector=w,navigation_detector=w,
                clock=lambda:w.time,sleeper=w.sleep,timeout=5,evidence_root=Path(folder))
            r=skill.run(target_level=51)
            self.assertEqual(w.processed,[(i,51) for i in range(6)])
            self.assertEqual((r.processed,r.changed,r.status),(6,4,"success"))

class LevelScreenshotTests(unittest.TestCase):
    def test_gold_six_after_batch_is_not_confused_with_zero(self):
        from advance_skill import ScreenNumbers
        class Numbers(ScreenNumbers):
            def read(self,*args):
                return [dict(text="56",x=606,y=89,w=18,h=17),
                        dict(text="150/63610",x=769,y=90,w=70,h=17)]
        d=LevelDetector(numbers=Numbers())
        png=(Path(__file__).parent/"fixtures/level/batch_after_56.png").read_bytes()
        f=d.decode(png)
        self.assertEqual(d._level_number(f),56)
        state=d.state(f,png,Path("."))
        self.assertEqual((state.level,state.books),(56,(0,0,0,1980)))

    def test_gold_level_can_be_read_when_ocr_omits_it(self):
        from advance_skill import ScreenNumbers
        class Numbers(ScreenNumbers):
            def read(self,*args):
                return [dict(text="5690/31780",x=765,y=90,w=70,h=17)]
        d=LevelDetector(numbers=Numbers())
        png=(Path(__file__).parent/"fixtures/level/gia_before.png").read_bytes()
        state=d.state(d.decode(png),png,Path("."))
        self.assertEqual((state.level,state.books),(50,(0,0,0,2002)))

    def test_before_and_after_inventory_numbers_from_real_game(self):
        cases=(("before",50,5690,31780,2008),("after",51,3910,33320,2005))
        for name,level,exp,needed,books in cases:
            with self.subTest(name=name):
                class Numbers:
                    @staticmethod
                    def read(*args):
                        return [dict(text=str(level),x=606,y=89,w=18,h=17),
                                dict(text=f"{exp}/{needed}",x=765,y=90,w=70,h=17)]
                    from advance_skill import ScreenNumbers
                    integer=staticmethod(ScreenNumbers.integer)
                    in_box=staticmethod(ScreenNumbers.in_box)
                d=LevelDetector(numbers=Numbers())
                png=(Path(__file__).parent/"fixtures/level"/(name+".png")).read_bytes()
                f=d.decode(png)
                state=d.state(f,png,Path("."))
                self.assertEqual((state.level,state.exp,state.exp_needed,state.books),
                                 (level,exp,needed,(0,0,0,books)))
                self.assertTrue(d.find(f,"level_button"))

if __name__=="__main__":
    unittest.main()
