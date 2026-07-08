"""
ค่าตั้งค่าแบบจำได้ (persistent) — โหลด/เซฟลง settings.json ในโฟลเดอร์ appdata
แอปเลยจำกล้อง/ปุ่ม/เส้นที่ตั้งไว้ ครั้งหน้าเปิดมาไม่ต้องตั้งใหม่

ชื่อ attribute ตั้งให้ตรงกับที่ MotionLogic / InputSender / camera อ่าน
เพื่อให้ส่ง object นี้แทน config module ได้เลย
"""

import json
import os

from paths import appdata_dir

SETTINGS_FILE = os.path.join(appdata_dir(), "settings.json")

# ค่าเริ่มต้น (ตรงกับที่จูนมาแล้ว)
DEFAULTS = {
    # กล้อง
    "CAMERA_INDEX": 0,
    "CAMERA_WIDTH": 640,
    "CAMERA_HEIGHT": 480,
    "CAMERA_FPS": 30,
    "CAMERA_BACKEND": "DSHOW",
    "USE_MJPG": True,
    "FLIP_HORIZONTAL": True,
    # ปุ่มที่ส่งเข้าเกม
    "JUMP_KEY": "space",
    "CROUCH_KEY": "ctrl",
    # ความไว / เส้น
    "JUMP_THRESHOLD": 0.18,
    "CROUCH_THRESHOLD": 0.18,
    "RELEASE_MARGIN": 0.06,
    "LINE_STEP": 0.01,
    # จังหวะเวลา
    "JUMP_DEBOUNCE_SEC": 0.35,
    "CALIBRATION_SEC": 2.0,
    # โหมด
    "DRY_RUN": True,
}


class Settings:
    def __init__(self, data=None):
        merged = dict(DEFAULTS)
        if data:
            merged.update({k: v for k, v in data.items() if k in DEFAULTS})
        for k, v in merged.items():
            setattr(self, k, v)

    def to_dict(self):
        return {k: getattr(self, k) for k in DEFAULTS}

    def save(self, path=SETTINGS_FILE):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("เซฟ settings ไม่ได้:", e)

    @classmethod
    def load(cls, path=SETTINGS_FILE):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return cls(json.load(f))
        except Exception as e:
            print("โหลด settings ไม่ได้ ใช้ค่าเริ่มต้น:", e)
        return cls()
