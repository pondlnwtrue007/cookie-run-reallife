@echo off
REM ทดสอบส่งปุ่มเข้าเกม (คลิกขวา -> Run as administrator)
cd /d "%~dp0"
title ทดสอบส่งปุ่ม
py test_key.py %*
