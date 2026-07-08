@echo off
REM ===============================================
REM  Cookie Run Real-Life — ตัวเปิดแอป (รันผ่าน Python)
REM  ขอสิทธิ์ Administrator อัตโนมัติ (จำเป็นต่อการส่งปุ่มเข้า MuMu)
REM  ครั้งแรกต้องลง: py -m pip install -r requirements.txt
REM ===============================================
cd /d "%~dp0"

REM --- เช็คว่าเป็น admin หรือยัง ถ้ายัง ให้เปิดใหม่แบบ admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

title Cookie Run Real-Life
py app.py
if errorlevel 1 (
    echo.
    echo [!] เปิดแอปไม่สำเร็จ - ตรวจว่าลง Python และ dependencies แล้ว:
    echo     py -m pip install -r requirements.txt
    echo.
    pause
)
