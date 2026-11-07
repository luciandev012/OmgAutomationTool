import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import cv2
import numpy as np
from advance_skill import ResourceCount,ScreenNumbers
from evolution_skill import (EvolutionSkill,EvolutionDetector,EvolutionState,EvolutionResult,
                             TeamEvolutionSkill,validate_target)
from login_engine import Match
from test_equipment_team import ModelTeam,TeamWorld


class World:
    ready=True
    def __init__(self,kind='breakthrough',rank=None,blocked=False,fail=None,resources=None,cap=False,enabled=True):
        self.kind=kind;self.rank=rank or ((0,) if kind=='breakthrough' else (0,0))
        self.blocked,self.fail,self.cap,self.enabled=blocked,fail,cap,enabled
        self.resources=resources if resources is not None else (ResourceCount('pills',1000,100),ResourceCount('fragments',100,10))
        self.time=0;self.actions=[];self.stop=None
    def sleep(self,n):self.time+=n
    def capture(self):return cv2.imencode('.png',np.zeros((597,1061,3),np.uint8))[1].tobytes()
    def decode(self,png):return cv2.imdecode(np.frombuffer(png,np.uint8),1)
    def find(self,frame,name,*args):
        if name=='advance_button':return Match(name,790,540,50,25,1)
    def next(self):
        if self.kind=='breakthrough':return (self.rank[0]+1,)
        return (self.rank[0],self.rank[1]+1) if self.rank[1]<2 else (self.rank[0]+1,0)
    def state(self,*args):
        if self.fail=='initial_unknown' or (self.actions and self.fail=='unknown'):return None
        return EvolutionState(self.rank,self.next(),self.resources,self.blocked,self.enabled,self.cap)
    def tap(self,*args):
        self.actions.append(args)
        if self.fail not in ('unchanged','unknown'):
            self.rank=self.next()
            if self.fail=='jump':self.rank=self.next()
            self.resources=tuple(ResourceCount(r.kind,r.available-r.required,r.required) for r in self.resources)
            if self.fail=='debit':self.resources=tuple(ResourceCount(r.kind,r.available+1,r.required) for r in self.resources)
            if self.fail=='blocked_after':self.blocked=True
        if self.stop:self.stop.set()


class ModelEvolution(EvolutionSkill):
    def _open_tab(self):
        return None if self.device.fail=='no_entry' else self._observe()


class EvolutionTests(unittest.TestCase):
    def run_world(self,w,target=None,max_steps=100,stop=None):
        with tempfile.TemporaryDirectory() as folder:
            s=ModelEvolution(w,kind=w.kind,detector=w,roster_detector=w,navigation_detector=w,
                clock=lambda:w.time,sleeper=w.sleep,timeout=3,evidence_root=Path(folder),max_steps=max_steps,stop=stop)
            r=s._run_in_event(target)
            report=json.loads((Path(r.evidence_dir)/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(report['upgrades'],r.upgrades)
            return r
    def test_breakthrough_target_exact_and_costs_debited(self):
        w=World();r=self.run_world(w,(2,))
        self.assertEqual((r.final_rank,r.upgrades,r.reason),((2,),2,'target_reached'))
        self.assertEqual(w.resources,(ResourceCount('pills',800,100),ResourceCount('fragments',80,10)))
    def test_awakening_level_and_star_transition(self):
        w=World('awakening');r=self.run_world(w,(1,0))
        self.assertEqual((r.final_rank,r.upgrades),((1,0),3))
    def test_specific_awakening_lv_target(self):
        w=World('awakening');r=self.run_world(w,(0,1))
        self.assertEqual((r.final_rank,len(w.actions)),((0,1),1))
    def test_target_already_met(self):
        w=World(rank=(3,));self.assertEqual(self.run_world(w,(1,)).reason,'target_reached');self.assertFalse(w.actions)
    def test_passive_missing_each_material_for_both_skills(self):
        for kind in ('awakening','breakthrough'):
            for resource in ('pills','fragments'):
                rs=(ResourceCount('pills',0 if resource=='pills' else 1000,100),ResourceCount('fragments',0 if resource=='fragments' else 100,10))
                w=World(kind,resources=rs);r=self.run_world(w)
                self.assertEqual(r.reason,'missing_'+resource);self.assertFalse(w.actions)
    def test_red_condition_precedes_spending_even_with_resources(self):
        for kind in ('awakening','breakthrough'):
            w=World(kind,blocked=True);r=self.run_world(w)
            self.assertEqual(r.reason,'conditions_not_met');self.assertFalse(w.actions)
    def test_red_condition_with_unreadable_progress_is_normal_stop(self):
        w=World(blocked=True);w.state=lambda *args:EvolutionState(None,None,condition_blocked=True)
        self.assertEqual(self.run_world(w).status,'no_action');self.assertFalse(w.actions)
    def test_new_red_condition_stops_after_first_success(self):
        w=World(fail='blocked_after');r=self.run_world(w)
        self.assertEqual((r.upgrades,r.reason,len(w.actions)),(1,'conditions_not_met',1))
    def test_unknown_initial_state_never_clicks(self):
        w=World(fail='initial_unknown');self.assertEqual(self.run_world(w).status,'blocked');self.assertFalse(w.actions)
    def test_unknown_or_unchanged_results_are_not_retried(self):
        for fail in ('unknown','unchanged'):
            w=World(fail=fail);self.assertEqual(self.run_world(w).status,'blocked');self.assertEqual(len(w.actions),1)
    def test_unexpected_jump_or_resource_debit_stops(self):
        for fail in ('jump','debit'):
            w=World(fail=fail);self.assertEqual(self.run_world(w).status,'error');self.assertEqual(len(w.actions),1)
    def test_target_would_exceed_is_not_clicked(self):
        w=World('awakening',rank=(0,2));r=self.run_world(w,(0,3))
        self.assertEqual(r.reason,'target_would_exceed');self.assertFalse(w.actions)
    def test_cap_and_disabled_button_stop(self):
        for opts,reason in (({'cap':True},'max_rank'),({'enabled':False},'conditions_not_met')):
            w=World(**opts);self.assertEqual(self.run_world(w).reason,reason);self.assertFalse(w.actions)
    def test_no_entry_skips_unsupported_hero(self):
        w=World(fail='no_entry');self.assertEqual(self.run_world(w).reason,'not_available');self.assertFalse(w.actions)
    def test_cancel_is_honoured_before_next_action(self):
        stop=threading.Event();w=World();w.stop=stop
        self.assertEqual(self.run_world(w,stop=stop).status,'cancelled');self.assertEqual(len(w.actions),1)
    def test_step_budget_is_not_game_cap(self):
        w=World();self.assertEqual(self.run_world(w,max_steps=1).reason,'step_budget');self.assertEqual(len(w.actions),1)
    def test_invalid_targets_are_rejected_before_navigation(self):
        for kind in ('awakening','breakthrough'):
            for target in (-1,'1',(True,),(-1,),(1,2,3),(1000,)):
                w=World(kind);self.assertEqual(self.run_world(w,target).status,'error');self.assertFalse(w.actions)
    def test_public_entry_requires_event_proof(self):
        w=World()
        with tempfile.TemporaryDirectory() as folder:
            s=ModelEvolution(w,kind=w.kind,detector=w,roster_detector=w,navigation_detector=w,evidence_root=Path(folder))
            s.gate=SimpleNamespace(last_png=b'',enter=Mock(side_effect=TimeoutError('event missing')))
            self.assertEqual(s.run().reason,'event_not_verified');self.assertFalse(w.actions)


class ScreenshotTests(unittest.TestCase):
    def frame(self,kind):
        png=(Path(__file__).parent/'fixtures'/kind/'blocked.png').read_bytes()
        d=EvolutionDetector(kind)
        return d,d.decode(png),png
    def test_real_red_conditions_stop_both_skills_even_if_ocr_fails(self):
        for kind in ('breakthrough','awakening'):
            d,f,png=self.frame(kind);d.numbers.read=Mock(side_effect=AssertionError('OCR must not be needed to stop'))
            s=d.state(f,png,Path('.'))
            self.assertTrue(s.condition_blocked)
            self.assertEqual(s.rank,(0,) if kind=='breakthrough' else (0,0))
    def test_red_header_or_resource_icon_does_not_block_without_condition_text(self):
        for kind in ('breakthrough','awakening'):
            d,f,_=self.frame(kind)
            y1,y2=(502,528) if kind=='breakthrough' else (487,513)
            f[y1:y2,700:993]=0
            self.assertFalse(d.red_condition(f))
            cv2.circle(f,(910,y1+12),5,(0,0,255),-1)
            self.assertFalse(d.red_condition(f))
    def test_read_materials_when_conditions_clear(self):
        for kind in ('breakthrough','awakening'):
            d,f,png=self.frame(kind)
            y1,y2=(502,528) if kind=='breakthrough' else (487,513);f[y1:y2,700:993]=0
            words=[dict(text='6128/750' if kind=='breakthrough' else '3212/60',x=727,y=455 if kind=='breakthrough' else 442,w=50,h=17)]
            if kind=='breakthrough':words.append(dict(text='265/80',x=926,y=455,w=40,h=17))
            d.numbers.read=Mock(return_value=words)
            s=d.state(f,png,Path('.'))
            self.assertIsNotNone(s)
            self.assertEqual(len(s.resources),2 if kind=='breakthrough' else 1)
            self.assertTrue(s.enabled)
    def test_awakening_reads_fragments_when_second_material_is_present(self):
        d,f,png=self.frame('awakening');f[487:513,700:993]=0
        marker=d.templates['fragment_mark']
        # Same item "Mảnh" label, shifted with the awakening material row.
        f[448:448+marker.shape[0],855:855+marker.shape[1]]=cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
        d.numbers.read=Mock(return_value=[dict(text='3212/60',x=727,y=442,w=50,h=17),
                                        dict(text='265/80',x=926,y=442,w=40,h=17)])
        state=d.state(f,png,Path('.'))
        self.assertIsNotNone(state)
        self.assertEqual(state.resources,(ResourceCount('pills',3212,60),ResourceCount('fragments',265,80)))
        d.numbers.read=Mock(return_value=[dict(text='3212/60',x=727,y=442,w=50,h=17)])
        self.assertIsNone(d.state(f,png,Path('.')))

    def test_unreadable_counter_never_allows_click(self):
        d,f,png=self.frame('breakthrough');f[502:528,700:993]=0
        d.numbers.read=Mock(return_value=[dict(text='6128750',x=727,y=455,w=50,h=17)])
        self.assertIsNone(d.state(f,png,Path('.')))
    def test_different_hero_artwork_does_not_prevent_safe_navigation(self):
        d=EvolutionDetector('awakening')
        png=(Path(__file__).parent/'fixtures/awakening/other_hero.png').read_bytes()
        f=d.decode(png)
        self.assertTrue(d.find(f,'hero_title'))
        self.assertTrue(d.is_advance(f))
        self.assertEqual(d.state(f,png,Path('.')).rank,(0,0))
        f[400:480,650:725]=0
        self.assertIsNone(d.find(f,'hero_title'))

    def test_awakening_lv_digit_one_is_not_clipped_or_confused_with_v(self):
        d,f,_=self.frame('awakening')
        # The UI's next Lv1 glyph has a narrower bearing than Lv0.
        f[64:94,788:804]=f[64:94,1000:1016].copy()
        self.assertEqual(d._progress(f)[0],(0,1))

    def test_wrong_screen_is_not_a_skill_page(self):
        for kind in ('breakthrough','awakening'):
            d,f,png=self.frame(kind);f[0:100,110:1058]=0
            self.assertIsNone(d.state(f,png,Path('.')))


class TeamModel(TeamEvolutionSkill,ModelTeam):
    def _formation(self):self.device.proved=True;return self._observe()
    def _make_hero_skill(self,index):
        w=self.device
        class Child:
            last_png=b''
            def _run_in_event(child,target):
                assert w.proved
                w.processed.append((w.selected,target))
                return EvolutionResult('no_action','red condition','conditions_not_met')
            def return_to_formation(child):pass
        return Child()


class TeamTests(unittest.TestCase):
    def test_all_six_heroes_continue_after_prerequisite_stop(self):
        for kind in ('breakthrough','awakening'):
            w=TeamWorld(count=6)
            with tempfile.TemporaryDirectory() as folder:
                s=TeamModel(w,kind=kind,detector=w,evolution_detector=w,navigation_detector=w,
                    clock=lambda:w.time,sleeper=w.sleep,timeout=5,evidence_root=Path(folder))
                target=(1,) if kind=='breakthrough' else (1,0)
                r=s.run(target_rank=target)
                self.assertEqual(w.processed,[(i,target) for i in range(6)])
                self.assertEqual((r.processed,r.changed,r.status),(6,0,'no_action'))

if __name__=='__main__':unittest.main()