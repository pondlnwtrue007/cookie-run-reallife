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
    True ถ้าหน้าต่าง active "ตรงกับ" substr (เช่น 'MuMu' หรือชื่อเต็มที่เลือกจาก dropdown)
    - substr ว่าง = ปิดการกรอง (ส่งตลอด แบบเดิม)
    - แมตช์แบบสองทาง (เผื่อชื่อหน้าต่างเปลี่ยนไปเล็กน้อย) เพื่อความทน
    """
    if not substr:
        return True
    t = foreground_title().lower()
    s = substr.lower()
    return (s in t) or (len(t) >= 4 and t in s)


def list_windows():
    """รายชื่อหน้าต่างที่เปิดอยู่ (มองเห็น + มีชื่อ) เรียงตามตัวอักษร ไม่ซ้ำ"""
    u = ctypes.windll.user32
    titles = []
    seen = set()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        try:
            if not u.IsWindowVisible(hwnd):
                return True
            n = u.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            t = (buf.value or "").strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                titles.append(t)
        except Exception:
            pass
        return True

    try:
        u.EnumWindows(_cb, 0)
    except Exception:
        pass
    return sorted(titles, key=str.lower)
