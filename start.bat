@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "ROOT_DIR=%ROOT:~0,-1%"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=5847"
set "FRONTEND_PORT=3847"

if not exist "%ROOT%logs" mkdir "%ROOT%logs" >nul 2>&1

echo ========================================
echo   GPT Chat Browser
echo ========================================
echo.
echo [1/3] Stopping old processes...

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -Root "%ROOT_DIR%" -TargetPidFiles "%ROOT%logs\backend.pid" "%ROOT%logs\frontend.pid" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -Root "%ROOT_DIR%" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%" >nul 2>&1

REM Ensure ports are actually free; otherwise start.bat can accidentally succeed
REM by talking to a stale server that survived the kill attempt.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\assert_ports_free.ps1" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Ports are still in use: %BACKEND_PORT% or %FRONTEND_PORT%.
    echo         Please run stop.bat again, or kill the listening PIDs on these ports.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\assert_ports_free.ps1" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%" -ShowDetails
    echo.
    endlocal
    exit /b 1
)

timeout /t 1 /nobreak >nul

echo [2/3] Starting backend...
powershell -NoProfile -WindowStyle Hidden -Command "$p=Start-Process -WindowStyle Hidden -PassThru -FilePath cmd.exe -WorkingDirectory '%BACKEND%' -ArgumentList '/c','set BACKEND_HOST=%BACKEND_HOST%&& set BACKEND_PORT=%BACKEND_PORT%&& run_hidden.cmd'; Set-Content -Encoding ASCII -Path '%ROOT%logs\backend.pid' -Value $p.Id" >nul 2>&1

set "BACKEND_URL=http://%BACKEND_HOST%:%BACKEND_PORT%/api/health"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait_http_ok.ps1" -Url "%BACKEND_URL%" -Retries 20 -DelaySeconds 1 -TimeoutSec 1 >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Backend failed to start. Check logs\flask.log
    echo.
    endlocal
    exit /b 1
)

echo [3/3] Starting frontend...
powershell -NoProfile -WindowStyle Hidden -Command "$p=Start-Process -WindowStyle Hidden -PassThru -FilePath cmd.exe -WorkingDirectory '%FRONTEND%' -ArgumentList '/c','set VITE_PORT=%FRONTEND_PORT%&& run_hidden.cmd'; Set-Content -Encoding ASCII -Path '%ROOT%logs\frontend.pid' -Value $p.Id" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait_tcp_open.ps1" -HostName "localhost" -Port %FRONTEND_PORT% -Retries 20 -DelayMilliseconds 500 >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Frontend failed to start on port %FRONTEND_PORT%.
    echo         Check logs\vite.log
    echo.
    call "%ROOT%stop.bat" /silent >nul 2>&1
    endlocal
    exit /b 1
)

echo.
echo [OK] Started
echo Backend:  http://%BACKEND_HOST%:%BACKEND_PORT%
echo Frontend: http://localhost:%FRONTEND_PORT%
echo Logs: logs\flask.log, logs\vite.log
echo.
endlocal
exit /b
