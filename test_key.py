"""
ทดสอบส่งปุ่มเข้าเกมตรงๆ (ไม่ใช้กล้อง) เพื่อหาสาเหตุที่ปุ่มไม่เข้า MuMu

วิธีใช้:
    py test_key.py            (ทดสอบปุ่ม space = กระโดด)
    py test_key.py ctrl       (ทดสอบปุ่มอื่น เช่น สไลด์)

จะนับถอยหลัง 5 วิ ให้เอาเมาส์ไปคลิกหน้าต่าง MuMu ก่อน แล้วมันจะกดปุ่มให้ 5 ครั้ง
ดูว่าตัวละครในเกมกระโดด/ขยับไหม
"""

import ctypes
import sys
import time

import pydirectinput

pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = False

KEY = sys.argv[1] if len(sys.argv) > 1 else "space"
HOLD = 0.05  # กดค้างสั้นๆ ก่อนปล่อย ให้เกมอ่านทัน


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def main():
    print("=" * 50)
    print(f"ทดสอบส่งปุ่ม: {KEY}")
    print(f"รันแบบ Administrator: {'ใช่ ✅' if is_admin() else 'ไม่ ❌ (อาจเป็นสาเหตุ!)'}")
    print("=" * 50)
    print("\n>>> เอาเมาส์ไปคลิกหน้าต่าง MuMu เดี๋ยวนี้! <<<\n")
    for i in range(5, 0, -1):
        print(f"  เริ่มใน {i}...", flush=True)
        time.sleep(1)

    print(f"\n--- กด {KEY} 5 ครั้ง (กดค้าง {int(HOLD*1000)}ms แล้วปล่อย) ---")
    for n in range(5):
        pydirectinput.keyDown(KEY)
        time.sleep(HOLD)
        pydirectinput.keyUp(KEY)
        print(f"  กด {KEY} ครั้งที่ {n+1}", flush=True)
        time.sleep(0.8)

    print("\nเสร็จ! ตัวละครในเกมขยับไหม?")
    print("  - ขยับ = ส่งปุ่มได้ ปัญหาอยู่ที่โหมด/การจับท่า")
    print("  - ไม่ขยับ = ปุ่มไม่เข้าเกม (ดูว่า admin ไหม + keymapping MuMu ถูกไหม)")


if __name__ == "__main__":
    main()
    input("\nกด Enter เพื่อปิด...")
