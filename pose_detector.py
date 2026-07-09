"""
หุ้ม MediaPipe Pose (Tasks API — PoseLandmarker): รับเฟรม -> landmark + เมตริกความสูงตัว

หมายเหตุ: mediapipe เวอร์ชันใหม่ (0.10.3x+) ตัด legacy `mp.solutions` ออกแล้ว
จึงใช้ Tasks API ซึ่งต้องมีไฟล์โมเดล .task (ดาวน์โหลดอัตโนมัติถ้ายังไม่มี)

เมตริกหลักที่ใช้ตัดสิน:
  - torso_y  : ตำแหน่งแนวตั้งเฉลี่ยของ (ไหล่ + สะโพก)  (0=บน, 1=ล่าง)
  - torso_len: ความยาวลำตัว = ระยะไหล่ถึงสะโพก (normalize ให้ไม่ขึ้นกับระยะกล้อง)
"""

import os
import time
import urllib.request

import cv2
import mediapipe as mp

from paths import resource_path, appdata_dir

_V = mp.tasks.vision

# ไฟล์โมเดล + ที่มา (ถ้าไม่มีจะโหลดให้อัตโนมัติ)
MODEL_FILE = "pose_landmarker_lite.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)

# index ของ landmark (ตาม MediaPipe Pose 33 จุด)
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24

# คู่จุดสำหรับวาดโครงลำตัว + แขน ในหน้าต่าง debug
_TORSO_CONNECTIONS = [
    (L_SHOULDER, R_SHOULDER),
    (L_HIP, R_HIP),
    (L_SHOULDER, L_HIP),
    (R_SHOULDER, R_HIP),
]
_ARM_CONNECTIONS = [
    (L_SHOULDER, L_ELBOW), (L_ELBOW, L_WRIST),
    (R_SHOULDER, R_ELBOW), (R_ELBOW, R_WRIST),
]


def ensure_model():
    """
    หาไฟล์โมเดล ตามลำดับ:
      1) ไฟล์ที่แนบมากับโปรแกรม (bundled ใน exe หรืออยู่ข้างสคริปต์)
      2) ไฟล์ที่เคยโหลดไว้ในโฟลเดอร์ appdata
      3) โหลดใหม่ลง appdata
    """
    bundled = resource_path(MODEL_FILE)
    if os.path.exists(bundled):
        return bundled

    cached = os.path.join(appdata_dir(), MODEL_FILE)
    if os.path.exists(cached):
        return cached

    print(f"กำลังดาวน์โหลดโมเดล {MODEL_FILE} ...")
    urllib.request.urlretrieve(MODEL_URL, cached)
    print("ดาวน์โหลดโมเดลเสร็จ")
    return cached


class PoseResult:
    """ผลลัพธ์ต่อ 1 เฟรม"""

    def __init__(self, found, torso_y=None, torso_len=None, landmarks=None,
                 wrist_lift=0.0, arm_span=0.0):
        self.found = found          # เจอคนในเฟรมไหม
        self.torso_y = torso_y      # ตำแหน่งแนวตั้งของลำตัว (normalized 0..1)
        self.torso_len = torso_len  # ความยาวลำตัว (normalized)
        self.landmarks = landmarks  # list ของ landmark คนแรก (ไว้วาด)
        self.wrist_lift = wrist_lift  # ข้อมือสูง/ต่ำเทียบไหล่ (หาร torso_len) — จับการกระพือ
        self.arm_span = arm_span      # ระยะแขนกางซ้าย-ขวา (หาร torso_len) — จับท่า T


class PoseDetector:
    def __init__(self, model_path=None):
        model_path = model_path or ensure_model()
        options = _V.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=_V.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = _V.PoseLandmarker.create_from_options(options)
        self._t0 = time.perf_counter()
        self._last_ts = -1

    def _timestamp_ms(self):
        # ต้องเพิ่มขึ้นเรื่อยๆ อย่างเคร่งครัด ไม่งั้น detect_for_video จะ error
        ts = int((time.perf_counter() - self._t0) * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts
        return ts

    def process(self, rgb_frame) -> PoseResult:
        """รับภาพ RGB (uint8, HxWx3) -> PoseResult"""
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect_for_video(mp_image, self._timestamp_ms())

        if not result.pose_landmarks:
            return PoseResult(found=False)

        pts = result.pose_landmarks[0]
        shoulder_y = (pts[L_SHOULDER].y + pts[R_SHOULDER].y) / 2.0
        hip_y = (pts[L_HIP].y + pts[R_HIP].y) / 2.0

        torso_y = (shoulder_y + hip_y) / 2.0
        torso_len = abs(hip_y - shoulder_y)
        if torso_len < 1e-3:
            torso_len = 1e-3

        # ท่าแขน (ไว้จับ "บิน") — normalize ด้วย torso_len ให้ไม่ขึ้นกับระยะกล้อง
        wrist_y = (pts[L_WRIST].y + pts[R_WRIST].y) / 2.0
        wrist_lift = (shoulder_y - wrist_y) / torso_len       # + = ข้อมือสูงกว่าไหล่
        arm_span = abs(pts[L_WRIST].x - pts[R_WRIST].x) / torso_len

        return PoseResult(found=True, torso_y=torso_y, torso_len=torso_len,
                          landmarks=pts, wrist_lift=wrist_lift, arm_span=arm_span)

    def draw(self, bgr_frame, pose_result: PoseResult):
        """วาด landmark + โครงลำตัวคร่าวๆ ลงบนภาพ BGR (หน้าต่าง debug)"""
        if not pose_result.found or pose_result.landmarks is None:
            return bgr_frame
        h, w = bgr_frame.shape[:2]
        pts = pose_result.landmarks

        # เส้นเชื่อมลำตัว
        for a, b in _TORSO_CONNECTIONS:
            ax, ay = int(pts[a].x * w), int(pts[a].y * h)
            bx, by = int(pts[b].x * w), int(pts[b].y * h)
            cv2.line(bgr_frame, (ax, ay), (bx, by), (0, 255, 0), 2)

        # เส้นแขน (ไหล่-ศอก-ข้อมือ) — สีฟ้า ให้เห็นการจับปีกตอนบิน
        for a, b in _ARM_CONNECTIONS:
            ax, ay = int(pts[a].x * w), int(pts[a].y * h)
            bx, by = int(pts[b].x * w), int(pts[b].y * h)
            cv2.line(bgr_frame, (ax, ay), (bx, by), (255, 200, 0), 2)

        # จุด landmark ทั้งหมด
        for lm in pts:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(bgr_frame, (cx, cy), 3, (0, 200, 255), -1)
        return bgr_frame

    def close(self):
        self._landmarker.close()
