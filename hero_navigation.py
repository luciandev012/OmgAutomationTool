"""Verified shared navigation for event hero skills."""
from equipment_skill import TeamEquipmentSkill

class HeroNavigationMixin:
    def return_to_formation(self):
        deadline, sent = self.clock()+self.timeout,False
        while self.clock() < deadline:
            frame = self._observe()
            if self.roster.find(frame,"formation_title") and self.roster.find(frame,"equipment_menu"):
                return frame
            back = self.detector.find(frame,"back")
            if self.detector.find(frame,"hero_title") and back and not sent:
                self._tap(frame,back)
                sent = True
            self.sleeper(.6)
        raise TimeoutError("Chưa trở về Đội Hình sau nâng cấp; dừng trước khi chọn tướng khác.")

    def _restore_selected(self, frame):
        target = self.gate.selected_card
        if target is None:
            return
        walker = TeamEquipmentSkill(self.device, detector=self.roster, stop=self.stop,
            clock=self.clock, sleeper=self.sleeper, timeout=self.timeout)
        frame = walker._close_menu(frame)
        for direction in ("up","down"):
            for _ in range(9):
                cards = self.roster.visible_heroes(frame)
                found = next((c for c in cards if c.same_hero(target)),None)
                if found:
                    if not found.selected:
                        walker._select_hero(frame,found)
                    return
                old = cards
                frame = walker._scroll(frame,direction)
                if walker._same_view(old,self.roster.visible_heroes(frame)):
                    break
        raise ValueError("Không tìm lại được tướng đã chọn sau khi xác minh sự kiện; chưa nâng cấp.")

