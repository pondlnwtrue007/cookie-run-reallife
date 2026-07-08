# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — สร้าง Cookie Run Real-Life.exe (ไฟล์เดียวจบ)
build ด้วย:  py -m PyInstaller CookieRunReallife.spec
ผลลัพธ์อยู่ที่  dist/Cookie Run Real-Life.exe

ตั้ง CONSOLE = True ถ้าต้องการเห็น log ตอน debug, False สำหรับแจกจริง
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

CONSOLE = False      # True = เห็น log (debug), False = แจกจริง
UAC_ADMIN = True     # True = exe ขอ admin เอง (แจกจริง), False = สำหรับทดสอบ

datas = [
    ("pose_landmarker_lite.task", "."),  # แนบไฟล์โมเดลไว้ในตัว
    ("app_icon.ico", "."),               # แนบไอคอนไว้ให้หน้าต่างแอปใช้
]
binaries = []
hiddenimports = []

# mediapipe มีไฟล์ข้อมูลเยอะ + numpy 2.x/cv2 ต้องเก็บ C-extension ให้ครบ
for pkg in ("mediapipe", "pygrabber", "numpy", "cv2"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# comtypes (ที่ pygrabber ใช้) สร้างโมดูลตอนรัน ต้องดึง submodule มาให้ครบ
hiddenimports += collect_submodules("comtypes")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tensorflow", "torch", "matplotlib.tests"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Cookie Run Real-Life",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=CONSOLE,
    icon="app_icon.ico",  # ไอคอนของไฟล์ .exe
    uac_admin=UAC_ADMIN,  # ขอสิทธิ์ admin อัตโนมัติ (จำเป็นต่อการส่งปุ่มเข้า MuMu)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
