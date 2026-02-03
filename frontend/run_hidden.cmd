@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist "..\logs" mkdir "..\logs" >nul 2>&1
set "NO_COLOR=1"
set "FORCE_COLOR=0"
set "CI=1"
set "TERM=dumb"
npm run dev 1>>"..\logs\vite.log" 2>&1
