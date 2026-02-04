@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "VERBOSE=0"
if /I "%~1"=="/verbose" set "VERBOSE=1"

call :NowCs _T0
call :NowCs _TLAST
call :Log "start.bat begin"

set "ROOT=%~dp0"
set "ROOT_DIR=%ROOT:~0,-1%"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=5847"
set "FRONTEND_PORT=3847"

set "FLASK_LOG=%ROOT%logs\flask.log"
set "VITE_LOG=%ROOT%logs\vite.log"

REM If previous run used different ports, load them so we can stop correctly.
if exist "%ROOT%logs\ports.cmd" call "%ROOT%logs\ports.cmd"
call :EnsurePort BACKEND_PORT 5847
call :EnsurePort FRONTEND_PORT 3847

if not exist "%ROOT%logs" mkdir "%ROOT%logs" >nul 2>&1

REM If previous run is still releasing log handles, wait a bit.
call :Step "ensure logs writable / rotate if locked"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait_file_writable.ps1" -Path "%FLASK_LOG%" -Retries 10 -DelayMilliseconds 200 -CreateIfMissing >nul 2>&1
if errorlevel 1 (
    for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"`) do set "_TS=%%T"
    set "FLASK_LOG=%ROOT%logs\flask_!_TS!.log"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait_file_writable.ps1" -Path "%VITE_LOG%" -Retries 10 -DelayMilliseconds 200 -CreateIfMissing >nul 2>&1
if errorlevel 1 (
    if not defined _TS for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"`) do set "_TS=%%T"
    set "VITE_LOG=%ROOT%logs\vite_!_TS!.log"
)

echo ========================================
echo   GPT Chat Browser
echo ========================================
echo.
echo [1/3] Stopping old processes...

call :Step "kill old processes (pid files)"
if "%VERBOSE%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -Root "%ROOT_DIR%" -TargetPidFiles "%ROOT%logs\backend.pid" "%ROOT%logs\frontend.pid"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -Root "%ROOT_DIR%" -TargetPidFiles "%ROOT%logs\backend.pid" "%ROOT%logs\frontend.pid" >nul 2>&1
)
REM Stop anything still listening on current/last-known ports.
call :Step "kill listeners (ports %BACKEND_PORT%,%FRONTEND_PORT%)"
if "%VERBOSE%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_project_process.ps1" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%" >nul 2>&1
)

REM Wait for ports to be released only if needed.
call :Step "check ports free/bindable"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\assert_ports_free.ps1" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%" >nul 2>&1
if errorlevel 1 (
    call :Step "wait ports free/bindable"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait_ports_free.ps1" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%" -Retries 20 -DelayMilliseconds 250 >nul 2>&1
)

REM If the persisted ports are bindable, reuse them (stable ports).
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\assert_ports_free.ps1" -PortsCsv "%BACKEND_PORT%,%FRONTEND_PORT%" >nul 2>&1
if errorlevel 1 (
    REM Pick ports that are actually bindable (handles Windows excluded port ranges / policy blocks).
        call :Step "pick backend port"
    set "BACKEND_PORT="
    for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\pick_free_port.ps1" -PreferredPortsCsv "5847,5848,5849,5850,14540,14541,14542,14543,14544,14545" -BindHost "%BACKEND_HOST%" -AllowEphemeral`) do set "BACKEND_PORT=%%P"
    if "%BACKEND_PORT%"=="" (
        echo.
        echo [ERROR] Could not select a bindable backend port.
        powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\pick_free_port.ps1" -PreferredPortsCsv "5847,5848,5849,5850,14540,14541,14542,14543,14544,14545" -BindHost "%BACKEND_HOST%" -ShowDetails
        echo.
        endlocal
        exit /b 1
    )

    call :Step "pick frontend port"
    set "FRONTEND_PORT="
    for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\pick_free_port.ps1" -PreferredPortsCsv "3847,3848,3849,3850,14546,14547,14548,14549,14550,14551" -BindHost "127.0.0.1" -AllowEphemeral`) do set "FRONTEND_PORT=%%P"
    if "%FRONTEND_PORT%"=="" (
        echo.
        echo [ERROR] Could not select a bindable frontend port.
        powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\pick_free_port.ps1" -PreferredPortsCsv "3847,3848,3849,3850,14546,14547,14548,14549,14550,14551" -BindHost "127.0.0.1" -ShowDetails
        echo.
        endlocal
        exit /b 1
    )
)

REM Persist chosen ports so stop.bat and subsequent starts can clean up reliably.
(
  echo set BACKEND_HOST=%BACKEND_HOST%
  echo set BACKEND_PORT=%BACKEND_PORT%
  echo set FRONTEND_PORT=%FRONTEND_PORT%
) > "%ROOT%logs\ports.cmd"

timeout /t 1 /nobreak >nul

echo [2/3] Starting backend...
call :Step "spawn backend"
powershell -NoProfile -WindowStyle Hidden -Command "$p=Start-Process -WindowStyle Hidden -PassThru -FilePath cmd.exe -WorkingDirectory '%BACKEND%' -ArgumentList '/c','set BACKEND_HOST=%BACKEND_HOST%&& set BACKEND_PORT=%BACKEND_PORT%&& set FLASK_LOG_PATH=%FLASK_LOG%&& run_hidden.cmd'; Set-Content -Encoding ASCII -Path '%ROOT%logs\backend.pid' -Value $p.Id" >nul 2>&1

set "BACKEND_URL=http://%BACKEND_HOST%:%BACKEND_PORT%/api/health"
call :Step "wait backend health"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait_http_ok.ps1" -Url "%BACKEND_URL%" -Retries 40 -DelaySeconds 1 -TimeoutSec 2 >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Backend failed to start. Check %FLASK_LOG%
    echo         Picked backend: %BACKEND_HOST%:%BACKEND_PORT%
    echo         Picked frontend port: %FRONTEND_PORT%
    echo.
    echo ---- flask log tail ----
    powershell -NoProfile -Command "if (Test-Path -LiteralPath '%FLASK_LOG%') { Get-Content -LiteralPath '%FLASK_LOG%' -Encoding UTF8 -Tail 60 } else { 'No flask log found' }"
    echo ---- end ----
    echo.
    endlocal
    exit /b 1
)

echo [3/3] Starting frontend...
call :Step "spawn frontend"
powershell -NoProfile -WindowStyle Hidden -Command "$p=Start-Process -WindowStyle Hidden -PassThru -FilePath cmd.exe -WorkingDirectory '%FRONTEND%' -ArgumentList '/c','set VITE_PORT=%FRONTEND_PORT%&& set BACKEND_HOST=%BACKEND_HOST%&& set BACKEND_PORT=%BACKEND_PORT%&& set VITE_LOG_PATH=%VITE_LOG%&& run_hidden.cmd'; Set-Content -Encoding ASCII -Path '%ROOT%logs\frontend.pid' -Value $p.Id" >nul 2>&1

call :Step "wait frontend port open"
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
echo Logs (legacy): logs\flask.log, logs\vite.log
echo Logs (this run): %FLASK_LOG%  and  %VITE_LOG%
call :Log "start.bat done"
echo.
endlocal
exit /b

:NowCs
set "_t=%time: =0%"
set "_t=%_t:,=.%"
for /f "tokens=1-4 delims=:." %%a in ("%_t%") do (
    set /a "_cs=(1%%a-100)*360000 + (1%%b-100)*6000 + (1%%c-100)*100 + (1%%d-100)"
)
set "%~1=%_cs%"
exit /b 0

:Log
call :NowCs _TN
set /a "_dt=_TN-_T0"
if !_dt! lss 0 set /a "_dt+=8640000"
echo [TIME +!_dt!cs] %~1
exit /b 0

:Step
call :NowCs _TN
set /a "_dt=_TN-_TLAST"
if !_dt! lss 0 set /a "_dt+=8640000"
echo   - %~1  (+!_dt!cs)
set "_TLAST=!_TN!"
exit /b 0

:EnsurePort
set "_var=%~1"
set "_def=%~2"
set "_val=!%_var%!"
if "!_val!"=="" (
    set "%_var%=%_def%"
    exit /b 0
)
for /f "delims=0123456789" %%A in ("!_val!") do (
    set "%_var%=%_def%"
    exit /b 0
)
exit /b 0
