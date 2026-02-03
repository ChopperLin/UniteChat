@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "ROOT_DIR=%ROOT:~0,-1%"

set "SILENT=0"
if /I "%~1"=="/silent" set "SILENT=1"

if "%SILENT%"=="0" (
    echo ========================================
    echo   GPT Chat Browser 停止服务脚本
    echo ========================================
    echo.
)

REM 优先关闭由本脚本启动的进程（通过 PID 文件，避免误伤其他程序）
if "%SILENT%"=="0" (
    if exist "%ROOT%logs\backend.pid" echo   正在终止 PID 文件: backend.pid
    if exist "%ROOT%logs\frontend.pid" echo   正在终止 PID 文件: frontend.pid
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -Root "%ROOT_DIR%" -TargetPidFiles "%ROOT%logs\backend.pid" "%ROOT%logs\frontend.pid" >nul 2>&1

if "%SILENT%"=="0" echo [1/3] 正在关闭后端服务 (端口 5000/5001)...
REM 使用 PortsCsv 一次性传参，减少 PowerShell 启动开销
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -Root "%ROOT_DIR%" -PortsCsv "5000,5001" >nul 2>&1

if "%SILENT%"=="0" echo.
if "%SILENT%"=="0" echo [2/3] 正在关闭前端服务 (端口 3000)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -Root "%ROOT_DIR%" -PortsCsv "3000" >nul 2>&1

if "%SILENT%"=="0" echo.
if "%SILENT%"=="0" echo [3/3] 正在关闭相关终端窗口...
taskkill /FI "WindowTitle eq Backend - Flask Server*" /F >nul 2>&1
taskkill /FI "WindowTitle eq Frontend - Vite Dev Server*" /F >nul 2>&1

timeout /t 1 /nobreak >nul

if "%SILENT%"=="0" (
  echo.
  echo ========================================
  echo   ✓ 所有服务已停止
  echo ========================================
  echo.
  pause
)

endlocal
exit /b
