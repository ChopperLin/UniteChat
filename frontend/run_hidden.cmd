@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist "..\logs" mkdir "..\logs" >nul 2>&1
if exist "..\logs\ports.cmd" call "..\logs\ports.cmd"
if not defined VITE_PORT if defined FRONTEND_PORT set "VITE_PORT=%FRONTEND_PORT%"
if not defined BACKEND_HOST set "BACKEND_HOST=127.0.0.1"
if not defined BACKEND_PORT set "BACKEND_PORT=5000"
set "VITE_LOG=..\logs\vite.log"
if defined VITE_LOG_PATH set "VITE_LOG=%VITE_LOG_PATH%"
set "NO_COLOR=1"
set "FORCE_COLOR=0"
set "CI=1"
set "TERM=dumb"
npm run dev 1>>"%VITE_LOG%" 2>&1
