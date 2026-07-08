"""
ทดสอบส่งปุ่มเข้าเกมตรงๆ (ไม่ใช้กล้อง) เพื่อหาสาเหตุที่ปุ่มไม่เข้า MuMu

วิธีใช้:
    py test_key.py            (ทดสอบปุ่ม space = กระโดด)
    py test_key.py ctrl       (ทดสอบปุ่มอื่น เช่น สไลด์)

จะนับถอยหลัง 5 วิ ให้เอาเมาส์ไปคลิกหน้าต่าง MuMu ก่อน แล้วมันจะกดปุ่มให้ 6 ครั้ง
ดูว่าตัวละครในเกมกระโดด/ขยับไหม
"""

import ctypes
import sys
import time

import pydirectinput

pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = False

KEY = sys.argv[1] if len(sys.argv) > 1 else "space"

# scancode สำหรับวิธีที่ 2 (raw SendInput)
SCAN = {"space": 0x39, "ctrl": 0x1D, "down": 0x50, "up": 0x48,
        "left": 0x4B, "right": 0x4D, "z": 0x2C, "x": 0x2D, "shift": 0x2A}


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


# ---------- วิธีที่ 2: raw Win32 SendInput (scancode + กดค้าง 45ms) ----------
SendInput = ctypes.windll.user32.SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)


class KBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]


class _I(ctypes.Union):
    _fields_ = [("ki", KBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", _I)]


def _send_scan(scan, keyup):
    flags = 0x0008 | (0x0002 if keyup else 0)  # SCANCODE | (KEYUP)
    inp = INPUT(1, _I(KBDINPUT(0, scan, flags, 0, ctypes.pointer(ctypes.c_ulong(0)))))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def tap_raw(scan, hold=0.045):
    _send_scan(scan, False)
    time.sleep(hold)
    _send_scan(scan, True)


def main():
    print("=" * 50)
    print(f"ทดสอบส่งปุ่ม: {KEY}")
    print(f"รันแบบ Administrator: {'ใช่ ✅' if is_admin() else 'ไม่ ❌ (อาจเป็นสาเหตุ!)'}")
    print("=" * 50)
    print("\n>>> เอาเมาส์ไปคลิกหน้าต่าง MuMu เดี๋ยวนี้! <<<\n")
    for i in range(5, 0, -1):
        print(f"  เริ่มใน {i}...", flush=True)
        time.sleep(1)

    print("\n--- วิธีที่ 1: pydirectinput (กดค้าง 45ms) ---")
    for n in range(3):
        pydirectinput.keyDown(KEY)
        time.sleep(0.045)
        pydirectinput.keyUp(KEY)
        print(f"  กด {KEY} ครั้งที่ {n+1}", flush=True)
        time.sleep(0.8)

    scan = SCAN.get(KEY)
    if scan:
        print("\n--- วิธีที่ 2: raw SendInput (scancode) ---")
        for n in range(3):
            tap_raw(scan)
            print(f"  กด {KEY} (raw) ครั้งที่ {n+1}", flush=True)
            time.sleep(0.8)

    print("\nเสร็จ! ตัวละครในเกมขยับไหม?")
    print("  - ขยับ = ส่งปุ่มได้ ปัญหาอยู่ที่โหมด/การจับท่า")
    print("  - ไม่ขยับ = ปุ่มไม่เข้าเกม (ดูว่า admin ไหม + keymapping MuMu ถูกไหม)")


if __name__ == "__main__":
    main()
    input("\nกด Enter เพื่อปิด...")
