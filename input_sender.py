"""
หุ้ม pydirectinput: ส่งปุ่มจริงเข้าหน้าต่างที่ focus อยู่ (MuMuPlayer)

ใช้ scancode ผ่าน SendInput ซึ่ง emulator รับได้ดีกว่า pynput
รองรับ DRY_RUN: ถ้าเปิดไว้จะแค่ print ไม่ส่งปุ่มจริง (ไว้ทดสอบ)
"""

import time

import pydirectinput

# ปิด delay ในตัวของ pydirectinput เพื่อลด latency (สำคัญกับเกมเร็ว)
pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = False

# กด "แตะ" ต้องกดค้างสั้นๆ ก่อนปล่อย ไม่งั้น emulator (อ่าน input ~60Hz) จะพลาด
# ถ้ากดปล่อยเร็วเกิน 16ms เกมจะมองไม่เห็นการกดเลย
TAP_HOLD_SEC = 0.05


class InputSender:
    def __init__(self, cfg):
        self.cfg = cfg
        self.dry_run = cfg.DRY_RUN
        self._crouch_held = False
        self._fly_held = False
        # ตัวนับ ให้ UI โชว์ว่าตรวจจับ/ส่งปุ่มไปกี่ครั้ง (นับทั้งโหมดทดสอบและจริง)
        self.jump_count = 0
        self.crouch_count = 0
        self.fly_count = 0

    def toggle_dry_run(self):
        # ถ้ากำลังกดค้างอยู่ ให้ปล่อยก่อนสลับโหมด กันปุ่มค้าง
        if self._crouch_held:
            self.crouch_end()
        if self._fly_held:
            self.fly_end()
        self.dry_run = not self.dry_run
        return self.dry_run

    def jump(self):
        if self._fly_held:
            return  # กำลังบิน (space ค้างอยู่) ห้ามแตะซ้ำ = กันร่วงกลางคัน
        self.jump_count += 1
        if self.dry_run:
            print("[DRY] JUMP  -> tap", self.cfg.JUMP_KEY)
            return
        # กดค้างสั้นๆ แล้วปล่อย เพื่อให้เกมอ่านทัน (แทน press ที่กดปล่อยทันที)
        pydirectinput.keyDown(self.cfg.JUMP_KEY)
        time.sleep(TAP_HOLD_SEC)
        pydirectinput.keyUp(self.cfg.JUMP_KEY)

    def crouch_start(self):
        if self._crouch_held:
            return
        self._crouch_held = True
        self.crouch_count += 1
        if self.dry_run:
            print("[DRY] CROUCH start -> hold", self.cfg.CROUCH_KEY)
            return
        pydirectinput.keyDown(self.cfg.CROUCH_KEY)

    def crouch_end(self):
        if not self._crouch_held:
            return
        self._crouch_held = False
        if self.dry_run:
            print("[DRY] CROUCH end   -> release", self.cfg.CROUCH_KEY)
            return
        pydirectinput.keyUp(self.cfg.CROUCH_KEY)

    # ---------- บิน: กด "ปุ่มกระโดด (space)" ค้าง ----------
    def fly_start(self):
        if self._fly_held:
            return
        # ถ้ากำลังสไลด์ค้างอยู่ ปล่อยก่อน กัน ctrl ค้าง
        if self._crouch_held:
            self.crouch_end()
        self._fly_held = True
        self.fly_count += 1
        if self.dry_run:
            print("[DRY] FLY start -> hold", self.cfg.JUMP_KEY)
            return
        pydirectinput.keyDown(self.cfg.JUMP_KEY)

    def fly_end(self):
        if not self._fly_held:
            return
        self._fly_held = False
        if self.dry_run:
            print("[DRY] FLY end   -> release", self.cfg.JUMP_KEY)
            return
        pydirectinput.keyUp(self.cfg.JUMP_KEY)

    def cleanup(self):
        """ปล่อยปุ่มค้างทั้งหมดตอนปิดโปรแกรม กันปุ่มค้าง"""
        if self._fly_held and not self.dry_run:
            pydirectinput.keyUp(self.cfg.JUMP_KEY)
        self._fly_held = False
        if self._crouch_held and not self.dry_run:
            pydirectinput.keyUp(self.cfg.CROUCH_KEY)
        self._crouch_held = False
