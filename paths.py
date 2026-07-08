r"""
จัดการ path ให้ทำงานได้ทั้งตอนรันด้วย Python และตอนเป็น .exe (PyInstaller)

- resource_path(): หาไฟล์ที่แนบมากับโปรแกรม (เช่นโมเดล .task)
    ตอนเป็น exe ไฟล์จะถูกแตกไว้ที่ sys._MEIPASS
- appdata_dir(): โฟลเดอร์ที่เขียนได้เสมอ (%LOCALAPPDATA%\CookieRunReallife)
    ใช้เก็บ settings.json และโมเดลที่โหลดมา (เผื่อ exe อยู่ใน Program Files ที่เขียนไม่ได้)
"""

import os
import sys

APP_NAME = "CookieRunReallife"


def resource_path(name):
    """path ของไฟล์ที่แนบมากับโปรแกรม (ทำงานทั้ง .py และ .exe)"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def appdata_dir():
    """โฟลเดอร์เขียนได้สำหรับเก็บ settings/โมเดล — สร้างให้ถ้ายังไม่มี"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d
