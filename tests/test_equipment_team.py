import tempfile
import json
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

from equipment_skill import EquipmentDetector, EquipmentResult, HeroCard, TeamEquipmentSkill
from login_engine import Match


class TeamWorld:
    def __init__(self, count=6, selected=4, ignore_selection=False):
        self.count, self.selected = count, selected
        self.start = max(0, count - 4)
        self.menu = False
        self.ignore_selection = ignore_selection
        self.processed = []
        self.actions = []
        self.time = 0

    def cards(self):
        return [HeroCard(20, 90 + (i-self.start)*100, 91, 90,
                         bytes([10+i*30])*960, i == self.selected)
                for i in range(self.start, min(self.start+4, self.count))]

    def sleep(self, duration):
        self.time += duration

    @property
    def ready(self):
        return True

    def find(self, frame, name):
        if name in ('formation_title', 'equipment_menu', 'roster_up', 'roster_down') or (self.menu and name == 'quick_equip'):
            return Match(name, 20, 20, 2, 2, 1.)
        return None

    def visible_heroes(self, frame):
        return self.cards()


class ModelTeam(TeamEquipmentSkill):
    """Model only device observations/input; run the actual traversal logic."""
    def _observe(self):
        self._check()
        frame = np.zeros((597, 1061, 3), np.uint8)
        self.last_png = cv2.imencode('.png', frame)[1].tobytes()
        return frame

    def _tap(self, frame, target):
        self._check()
        world = self.device
        if isinstance(target, HeroCard):
            index = (target.fingerprint[0] - 10)//30
            world.actions.append(('hero', index))
            if not world.ignore_selection:
                world.selected = index
        else:
            world.actions.append((target.name,))
            if target.name == 'roster_up':
                world.start = max(0, world.start-1)
            elif target.name == 'roster_down':
                world.start = min(max(0, world.count-4), world.start+1)
            elif target.name == 'equipment_menu':
                world.menu = False

    def _swipe_roster(self, frame, direction):
        self._check()
        world = self.device
        world.actions.append(('swipe', direction))
        world.start = max(0, world.start-1) if direction == 'up' else min(max(0, world.count-4), world.start+1)


class TeamTests(unittest.TestCase):
    def run_team(self, count=6, limit=6, statuses=None, ignore_selection=False, cancel_after=None):
        world, stop = TeamWorld(count, ignore_selection=ignore_selection), threading.Event()
        statuses = statuses or {}

        class Child:
            last_png = b''

            def __init__(self, *args, **kwargs):
                pass

            def run(self, **kwargs):
                world.processed.append(world.selected)
                world.menu = True
                if cancel_after == len(world.processed):
                    stop.set()
                status = statuses.get(world.selected, 'no_action')
                return EquipmentResult(status, 'test result')

        with tempfile.TemporaryDirectory() as folder:
            skill = ModelTeam(world, detector=world, navigation_detector=world, stop=stop,
                              hero_skill_factory=Child, clock=lambda: world.time, sleeper=world.sleep,
                              timeout=8, evidence_root=Path(folder))
            result = skill.run(max_heroes=limit)
            self.assertTrue((Path(result.evidence_dir) / 'result.json').is_file())
        return result, world

    def test_scrolls_to_start_then_visits_six_distinct_heroes(self):
        result, world = self.run_team(statuses={1: 'success', 5: 'success'})
        self.assertEqual(world.processed, list(range(6)))
        self.assertEqual((result.status, result.processed, result.changed), ('success', 6, 2))

    def test_fewer_than_six_finishes_at_end_of_roster(self):
        result, world = self.run_team(count=3)
        self.assertEqual(world.processed, [0, 1, 2])
        self.assertEqual((result.status, result.processed), ('no_action', 3))

    def test_hard_limit_of_six_even_if_roster_has_more(self):
        result, world = self.run_team(count=8)
        self.assertEqual(world.processed, list(range(6)))
        self.assertEqual(result.processed, 6)

    def test_failed_selection_never_runs_child_on_wrong_hero(self):
        result, world = self.run_team(ignore_selection=True)
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(world.processed, [])

    def test_blocked_child_stops_and_preserves_previous_results(self):
        result, world = self.run_team(statuses={2: 'blocked'})
        self.assertEqual(world.processed, [0, 1, 2])
        self.assertEqual((result.status, result.processed), ('blocked', 3))

    def test_cancel_between_heroes_preserves_completed_results(self):
        result, world = self.run_team(cancel_after=2)
        self.assertEqual((result.status, result.processed), ('cancelled', 2))
        self.assertEqual(world.processed, [0, 1])

    def test_invalid_limit_performs_no_actions(self):
        result, world = self.run_team(limit=7)
        self.assertEqual(result.status, 'error')
        self.assertEqual(world.actions, [])

    def test_portrait_fingerprints_tolerate_minor_rendering_changes(self):
        a = HeroCard(0, 0, 90, 90, bytes([20])*960)
        b = HeroCard(0, 100, 90, 90, bytes([23])*960)
        c = HeroCard(0, 200, 90, 90, bytes([80])*960)
        self.assertTrue(a.same_hero(b))
        self.assertFalse(a.same_hero(c))

    def test_real_roster_selected_glow_and_partially_clipped_cards(self):
        detector = EquipmentDetector()
        folder = Path(__file__).parent / 'fixtures/equipment'
        top = cv2.imdecode(np.frombuffer((folder/'roster_ton_sach_before.png').read_bytes(), np.uint8), 1)
        scrolled = cv2.imdecode(np.frombuffer((folder/'roster_team_initial.png').read_bytes(), np.uint8), 1)
        cards = detector.visible_heroes(top)
        self.assertEqual(len(cards), 4)
        self.assertEqual([i for i, c in enumerate(cards) if c.selected], [1])
        lower = detector.visible_heroes(scrolled)
        self.assertEqual(len(lower), 3)
        self.assertTrue(cards[2].same_hero(lower[0]))
        self.assertTrue(cards[3].same_hero(lower[1]))

        bottom = cv2.imdecode(np.frombuffer((folder/'roster_bottom_roster.png').read_bytes(), np.uint8), 1)
        last = detector.visible_heroes(bottom)
        self.assertEqual(len(last), 4)
        unique = []
        for card in cards + last:
            if not any(card.same_hero(other) for other in unique):
                unique.append(card)
        self.assertEqual(len(unique), 6)

    def test_real_green_plus_slots_are_not_treated_as_heroes(self):
        detector = EquipmentDetector()
        path = Path(__file__).parent / 'fixtures/equipment/roster_empty_slots.png'
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 1)
        cards = detector.visible_heroes(frame)
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0].selected)

    def test_empty_slot_when_plus_is_invisible_has_no_portrait_detail(self):
        detector = EquipmentDetector()
        path = Path(__file__).parent / 'fixtures/equipment/roster_hidden_plus.png'
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 1)
        self.assertEqual(len(detector.visible_heroes(frame)), 3)

    def test_dim_pulsing_empty_slot_is_not_a_sixth_hero(self):
        detector = EquipmentDetector()
        path = Path(__file__).parent / 'fixtures/equipment/roster_dim_empty.png'
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 1)
        self.assertEqual(len(detector.visible_heroes(frame)), 3)

    def test_team_stat_samples_remain_readable_after_adding_glyph_variants(self):
        detector = EquipmentDetector()
        folder = Path(__file__).parent / 'fixtures/equipment'
        cases = json.loads((folder/'team_stats.json').read_text(encoding='utf-8'))
        for name, expected in cases.items():
            with self.subTest(sample=name):
                crop = cv2.imdecode(np.frombuffer((folder/(name+'.png')).read_bytes(), np.uint8), 1)
                frame = np.zeros((597, 1061, 3), np.uint8)
                frame[189:314, 923:1000] = crop
                self.assertEqual(detector.read_stats(frame), tuple(expected))


if __name__ == '__main__':
    unittest.main()
