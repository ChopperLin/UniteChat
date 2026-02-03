@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist "..\logs" mkdir "..\logs" >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"%~dp0venv\Scripts\python.exe" run.py 1>>"..\logs\flask.log" 2>&1
