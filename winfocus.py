"""
เช็คว่าหน้าต่างที่กำลังโฟกัส (foreground) อยู่ตอนนี้คือหน้าต่างเกมไหม
ใช้กันปุ่ม "รั่ว" ไปโปรแกรมอื่น (OBS/เบราว์เซอร์) ตอนโหมดเล่นจริง
"""

import ctypes


def foreground_title():
    """ชื่อหน้าต่างที่ active อยู่ตอนนี้ (คืน '' ถ้าอ่านไม่ได้)"""
    try:
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or ""
    except Exception:
        return ""


def target_focused(substr):
    """
    True ถ้าหน้าต่าง active มีคำว่า substr (เช่น 'MuMu') อยู่ในชื่อ
    - substr ว่าง = ปิดการกรอง (ส่งตลอด แบบเดิม)
    - อ่านชื่อไม่ได้/ไม่ตรง = False (ไม่ส่ง) เพื่อกันปุ่มรั่ว
    """
    if not substr:
        return True
    return substr.lower() in foreground_title().lower()
