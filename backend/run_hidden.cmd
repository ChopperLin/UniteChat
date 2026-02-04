@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist "..\logs" mkdir "..\logs" >nul 2>&1
if exist "..\logs\ports.cmd" call "..\logs\ports.cmd"
if not defined BACKEND_HOST set "BACKEND_HOST=127.0.0.1"
if not defined BACKEND_PORT set "BACKEND_PORT=5000"
set "FLASK_LOG=..\logs\flask.log"
if defined FLASK_LOG_PATH set "FLASK_LOG=%FLASK_LOG_PATH%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"%~dp0venv\Scripts\python.exe" run.py 1>>"%FLASK_LOG%" 2>&1
