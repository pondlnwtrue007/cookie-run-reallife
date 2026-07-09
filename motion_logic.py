"""
สมองของโปรแกรม: แปลงเมตริกความสูงตัว -> เหตุการณ์ JUMP / CROUCH

หลักการ:
  offset = (baseline_y - current_y) / baseline_torso_len
  - offset > 0  แปลว่าตัวอยู่ "สูงกว่า" ตอนยืน (กระโดด)
  - offset < 0  แปลว่าตัวอยู่ "ต่ำกว่า" ตอนยืน (ย่อ)
  หาร torso_len เพื่อให้ค่าคงที่ไม่ว่าอยู่ใกล้/ไกลกล้อง

สถานะ (state):
  STAND  -> ยืนปกติ
  JUMP   -> ชั่วขณะ ตอนตรวจเจอกระโดด (ยิงปุ่มแตะครั้งเดียว แล้วกลับ STAND)
  CROUCH -> ย่อค้าง (กดปุ่มสไลด์ค้างจนกว่าจะยืนขึ้น)
"""

import time
from collections import deque

STATE_STAND = "STAND"
STATE_JUMP = "JUMP"
STATE_CROUCH = "CROUCH"
STATE_FLY = "FLY"


class MotionLogic:
    def __init__(self, cfg):
        self.cfg = cfg
        self.jump_threshold = cfg.JUMP_THRESHOLD
        self.crouch_threshold = cfg.CROUCH_THRESHOLD

        self.baseline_y = None          # torso_y ตอนยืน (ได้จาก calibrate)
        self.baseline_len = None        # torso_len ตอนยืน

        self.state = STATE_STAND
        self.crouching = False          # กำลังกดปุ่มสไลด์ค้างอยู่ไหม
        self.flying = False             # กำลังบิน (กด space ค้าง) อยู่ไหม
        self._last_jump_time = 0.0
        self._move_buf = deque()        # ประวัติ (t, wrist_lift, torso_y) จับการแกว่ง
        self._last_move_time = 0.0      # ครั้งล่าสุดที่ตรวจเจอการขยับ (กระพือ/เด้ง)

        # ตัวแปรช่วง calibrate
        self._calibrating = False
        self._calib_end = 0.0
        self._calib_y = []
        self._calib_len = []

        self.last_offset = 0.0          # ไว้โชว์ในหน้าต่าง debug

    # ---------- calibration ----------
    def start_calibration(self):
        self._calibrating = True
        self._calib_end = time.time() + self.cfg.CALIBRATION_SEC
        self._calib_y = []
        self._calib_len = []

    @property
    def is_calibrating(self):
        return self._calibrating

    @property
    def is_ready(self):
        return self.baseline_y is not None

    def calib_remaining(self):
        return max(0.0, self._calib_end - time.time())

    # ---------- ปรับความไวสดๆ ----------
    def adjust_sensitivity(self, delta):
        """ปรับ threshold ทั้งคู่พร้อมกัน (ปุ่ม [ ])"""
        self.jump_threshold = max(0.02, self.jump_threshold + delta)
        self.crouch_threshold = max(0.02, self.crouch_threshold + delta)

    def move_jump_line(self, screen_up):
        """เลื่อนเส้น JUMP: ขึ้นบนจอ = ต้องกระโดดสูงขึ้น (threshold มากขึ้น)"""
        step = self.cfg.LINE_STEP if screen_up else -self.cfg.LINE_STEP
        self.jump_threshold = max(0.02, self.jump_threshold + step)

    def move_crouch_line(self, screen_up):
        """เลื่อนเส้น CROUCH: ลงล่างจอ = ต้องย่อลึกขึ้น (threshold มากขึ้น)"""
        # เส้น crouch อยู่ใต้ baseline: เลื่อน "ลง" = threshold มากขึ้น
        step = -self.cfg.LINE_STEP if screen_up else self.cfg.LINE_STEP
        self.crouch_threshold = max(0.02, self.crouch_threshold + step)

    def move_stand_line(self, screen_up):
        """เลื่อนเส้น STAND (baseline): ขึ้นบนจอ = baseline_y ลดลง"""
        if self.baseline_y is None:
            return
        step = -self.cfg.LINE_STEP if screen_up else self.cfg.LINE_STEP
        self.baseline_y = min(1.0, max(0.0, self.baseline_y + step))

    def update(self, pose_result):
        """
        รับ PoseResult -> คืน event หนึ่งใน:
          "jump"          : เพิ่งกระโดด (ให้แตะปุ่ม)
          "crouch_start"  : เพิ่งเริ่มย่อ (ให้กดปุ่มสไลด์ค้าง)
          "crouch_end"    : เพิ่งเลิกย่อ (ให้ปล่อยปุ่มสไลด์)
          None            : ไม่มีอะไรเปลี่ยน
        """
        if not pose_result.found:
            # หลุดเฟรม/ไม่เจอคน -> ปล่อยปุ่มค้างเพื่อความปลอดภัย
            if self.flying:
                self.flying = False
                self.state = STATE_STAND
                return "fly_end"
            if self.crouching:
                self.crouching = False
                self.state = STATE_STAND
                return "crouch_end"
            return None

        # ระหว่าง calibrate: เก็บตัวอย่าง แล้วยังไม่ยิง event
        if self._calibrating:
            self._calib_y.append(pose_result.torso_y)
            self._calib_len.append(pose_result.torso_len)
            if time.time() >= self._calib_end and len(self._calib_y) > 0:
                self.baseline_y = sum(self._calib_y) / len(self._calib_y)
                self.baseline_len = sum(self._calib_len) / len(self._calib_len)
                self._calibrating = False
            return None

        if not self.is_ready:
            return None

        offset = (self.baseline_y - pose_result.torso_y) / self.baseline_len
        self.last_offset = offset

        # ---- FLY (บิน): กางแขน (T) + ขยับต่อเนื่อง (กระพือ/เด้ง) = กด space ค้าง ----
        # มีลำดับความสำคัญสูงสุด และตอนบินจะข้าม jump/crouch เพื่อเลี่ยงปุ่มชน
        now = time.time()
        if self.cfg.FLY_ENABLED:
            self._move_buf.append((now, pose_result.wrist_lift, pose_result.torso_y))
            while self._move_buf and now - self._move_buf[0][0] > self.cfg.FLY_WINDOW_SEC:
                self._move_buf.popleft()
            if len(self._move_buf) >= 2:
                lifts = [b[1] for b in self._move_buf]
                torsos = [b[2] for b in self._move_buf]
                osc = max(max(lifts) - min(lifts), max(torsos) - min(torsos))
                if osc > self.cfg.FLY_OSC_AMPLITUDE:
                    self._last_move_time = now
            wings_out = pose_result.arm_span > self.cfg.FLY_ARM_SPAN_MIN
            flying_now = wings_out and (now - self._last_move_time < self.cfg.FLY_RELEASE_DELAY)

            if self.flying:
                if not flying_now:
                    self.flying = False
                    self.state = STATE_STAND
                    return "fly_end"
                self.state = STATE_FLY
                return None
            if flying_now:
                self.flying = True
                self.crouching = False   # ออกจากสไลด์ถ้าเผลอค้าง (input layer ปล่อยให้)
                self.state = STATE_FLY
                return "fly_start"

        # ---- CROUCH (มีลำดับความสำคัญ: ถ้ากำลังย่อค้าง เช็คก่อน) ----
        if self.crouching:
            # ปล่อยเมื่อกลับขึ้นมาเกิน (threshold - margin)
            if offset > -(self.crouch_threshold - self.cfg.RELEASE_MARGIN):
                self.crouching = False
                self.state = STATE_STAND
                return "crouch_end"
            return None

        # เริ่มย่อ
        if offset < -self.crouch_threshold:
            self.crouching = True
            self.state = STATE_CROUCH
            return "crouch_start"

        # ---- JUMP (แตะครั้งเดียว + debounce) ----
        if offset > self.jump_threshold:
            now = time.time()
            if now - self._last_jump_time >= self.cfg.JUMP_DEBOUNCE_SEC:
                self._last_jump_time = now
                self.state = STATE_JUMP
                return "jump"
            return None

        # ยืนปกติ
        self.state = STATE_STAND
        return None
