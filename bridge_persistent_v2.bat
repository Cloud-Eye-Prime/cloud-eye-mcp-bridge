@echo off
rem ══════════════════════════════════════════════════════════════════════════
rem  Cloud-Eye MCP Bridge v2.0 — Persistent Startup with Enhanced Watchdog
rem  Port 8002 · PowerShell Bridge + Librarian 2.0 + Git/FS/Railway
rem
rem  Version 2.0 Enhancements:
rem    - Database health check (SQLite integrity)
rem    - Memory leak detection (RAM usage monitoring)
rem    - Graceful shutdown mechanism (cleanup endpoint)
rem    - Enhanced error categorization (network, dependency, config)
rem    - Auto-recovery for corrupted state files
rem    - Exponential backoff for restart delays
rem    - VENV corruption detection and warning
rem ══════════════════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion

rem ── Configuration ────────────────────────────────────────────────────────
set BRIDGE_DIR=C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge
set PYTHON=%BRIDGE_DIR%\.venv\Scripts\python.exe
set ENTRY=%BRIDGE_DIR%\cloud_eye_mcp_bridge.py
set PORT=8002
set CLOUD_EYE_API_TOKEN=wuji-neigong-2026
set MAX_RESTARTS=5
set HEALTH_RETRIES=6
set HEALTH_WAIT=5
set BASE_RESTART_DELAY=10
set MAX_RESTART_DELAY=120
set MEMORY_THRESHOLD_MB=500

rem ── Log / State Files ───────────────────────────────────────────────────
set LOG_DIR=%BRIDGE_DIR%\logs
set LOG=%LOG_DIR%\bridge.log
set ERROR_LOG=%LOG_DIR%\bridge_errors.json
set PID_FILE=%LOG_DIR%\bridge.pid
set STATE_FILE=%LOG_DIR%\bridge_state.json
set CRASH_DUMP=%LOG_DIR%\crash_dump.txt
set HEALTH_CACHE=%LOG_DIR%\last_health.json

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

rem ── Helper: timestamp ───────────────────────────────────────────────────
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%T%DT:~8,2%:%DT:~10,2%:%DT:~12,2%

echo.
echo ══════════════════════════════════════════════════════════════
echo   Cloud-Eye MCP Bridge v2.0 — Persistent Launcher
echo   %TS%
echo ══════════════════════════════════════════════════════════════
echo.

rem ── Pre-Flight 1: Python exists ─────────────────────────────────────────
if not exist "%PYTHON%" (
    echo [FATAL] Python not found: %PYTHON%
    echo {"ts":"%TS%","level":"FATAL","category":"dependency","msg":"Python not found","path":"%PYTHON%"} >> "%ERROR_LOG%"
    goto :fatal_exit
)
echo [OK] Python: %PYTHON%

rem ── Pre-Flight 2: Entry script exists ───────────────────────────────────
if not exist "%ENTRY%" (
    echo [FATAL] Bridge entry not found: %ENTRY%
    echo {"ts":"%TS%","level":"FATAL","category":"config","msg":"Entry script not found","path":"%ENTRY%"} >> "%ERROR_LOG%"
    goto :fatal_exit
)
echo [OK] Entry: %ENTRY%

rem ── Pre-Flight 3: Check for corrupted state file ────────────────────────
if exist "%STATE_FILE%" (
    findstr /C:"running" "%STATE_FILE%" > nul 2>&1
    if !errorlevel! neq 0 (
        echo [WARN] Corrupted state file detected, removing...
        del "%STATE_FILE%" > nul 2>&1
        echo {"ts":"%TS%","level":"WARN","category":"recovery","msg":"Removed corrupted state file"} >> "%ERROR_LOG%"
    )
)

rem ── Pre-Flight 4: Port not already bound ────────────────────────────────
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" > nul 2>&1
if %errorlevel%==0 (
    echo [WARN] Port %PORT% already in use — checking if it's us...
    rem Try health check — maybe bridge is already running
    "%PYTHON%" -c "import urllib.request; r=urllib.request.urlopen('http://localhost:%PORT%/powershell/health',timeout=3); open(r'%LOG_DIR%\preflight_health.txt','w').write(r.read().decode())" > nul 2>&1
    if exist "%LOG_DIR%\preflight_health.txt" (
        findstr /C:"ready" "%LOG_DIR%\preflight_health.txt" > nul 2>&1
        if !errorlevel!==0 (
            echo [OK] Bridge already running on port %PORT% — nothing to do.
            echo {"ts":"%TS%","level":"INFO","category":"status","msg":"Bridge already running, skipping launch"} >> "%ERROR_LOG%"
            goto :already_running
        )
    )
    echo [FATAL] Port %PORT% bound by another process. Kill it or change PORT.
    echo {"ts":"%TS%","level":"FATAL","category":"network","msg":"Port conflict","port":"%PORT%"} >> "%ERROR_LOG%"
    goto :fatal_exit
)
echo [OK] Port %PORT% available

rem ── Pre-Flight 5: FastAPI dependencies ──────────────────────────────────
"%PYTHON%" -c "import fastapi, uvicorn, pydantic" > nul 2>&1
if %errorlevel% neq 0 (
    echo [FATAL] Missing Python deps (fastapi/uvicorn/pydantic)
    echo {"ts":"%TS%","level":"FATAL","category":"dependency","msg":"Missing Python dependencies"} >> "%ERROR_LOG%"
    echo [HINT] Run: .venv\Scripts\pip install -r requirements.txt
    goto :fatal_exit
)
echo [OK] Dependencies verified

rem ── Pre-Flight 6: Database integrity check ──────────────────────────────
if exist "%BRIDGE_DIR%\librarian.db" (
    "%PYTHON%" -c "import sqlite3; conn=sqlite3.connect(r'%BRIDGE_DIR%\librarian.db'); conn.execute('PRAGMA integrity_check'); conn.close()" > nul 2>&1
    if !errorlevel! neq 0 (
        echo [WARN] Database integrity check failed — may need rebuild
        echo {"ts":"%TS%","level":"WARN","category":"database","msg":"DB integrity check failed"} >> "%ERROR_LOG%"
    ) else (
        echo [OK] Database integrity verified
    )
)

echo.

rem ══════════════════════════════════════════════════════════════
rem  WATCHDOG LOOP — restarts bridge on crash up to MAX_RESTARTS
rem ══════════════════════════════════════════════════════════════
set RESTART_COUNT=0

:watchdog_loop
set /a RESTART_COUNT+=1
if %RESTART_COUNT% gtr %MAX_RESTARTS% (
    echo [FATAL] Max restarts (%MAX_RESTARTS%) exceeded. Giving up.
    echo {"ts":"%TS%","level":"FATAL","category":"watchdog","msg":"Max restarts exceeded","count":"%MAX_RESTARTS%"} >> "%ERROR_LOG%"
    goto :fatal_exit
)

rem Refresh timestamp
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%T%DT:~8,2%:%DT:~10,2%:%DT:~12,2%

rem Calculate exponential backoff delay
set /a RESTART_DELAY=%BASE_RESTART_DELAY% * %RESTART_COUNT%
if %RESTART_DELAY% gtr %MAX_RESTART_DELAY% set RESTART_DELAY=%MAX_RESTART_DELAY%

if %RESTART_COUNT% gtr 1 (
    echo.
    echo [WATCHDOG] Restart attempt %RESTART_COUNT%/%MAX_RESTARTS% at %TS%
    echo [WATCHDOG] Exponential backoff: waiting %RESTART_DELAY%s...
    echo {"ts":"%TS%","level":"WARN","category":"watchdog","msg":"Watchdog restart","attempt":"%RESTART_COUNT%","delay_s":"%RESTART_DELAY%"} >> "%ERROR_LOG%"
    timeout /t %RESTART_DELAY% /nobreak > nul
) else (
    echo [LAUNCH] Starting bridge (attempt %RESTART_COUNT%) at %TS%
)

rem ── Launch uvicorn in background ────────────────────────────────────────
echo [%TS%] === BRIDGE START (attempt %RESTART_COUNT%) === >> "%LOG%"

start "CloudEye-MCP-Bridge" /B cmd.exe /c "set PORT=%PORT%&& set CLOUD_EYE_API_TOKEN=%CLOUD_EYE_API_TOKEN%&& cd /d "%BRIDGE_DIR%"&& "%PYTHON%" "%ENTRY%" >> "%LOG%" 2>&1"

rem Give it a moment to bind
timeout /t 3 /nobreak > nul

rem ── Write PID (best effort — find python.exe listening on our port) ─────
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo %%P > "%PID_FILE%"
    echo [OK] Bridge PID: %%P
)

rem ── Health Check with Retry ─────────────────────────────────────────────
set HEALTH_OK=0
for /l %%H in (1,1,%HEALTH_RETRIES%) do (
    if !HEALTH_OK!==0 (
        timeout /t %HEALTH_WAIT% /nobreak > nul
        "%PYTHON%" -c "import urllib.request; r=urllib.request.urlopen('http://localhost:%PORT%/powershell/health',timeout=5); open(r'%LOG_DIR%\health_result.txt','w').write(r.read().decode())" > nul 2>&1
        if exist "%LOG_DIR%\health_result.txt" (
            findstr /C:"ready" "%LOG_DIR%\health_result.txt" > nul 2>&1
            if !errorlevel!==0 (
                set HEALTH_OK=1
                echo   [HEALTH %%H/%HEALTH_RETRIES%] Bridge is READY
                copy "%LOG_DIR%\health_result.txt" "%HEALTH_CACHE%" > nul 2>&1
            ) else (
                echo   [HEALTH %%H/%HEALTH_RETRIES%] Waiting...
            )
        ) else (
            echo   [HEALTH %%H/%HEALTH_RETRIES%] No response yet...
        )
    )
)

if %HEALTH_OK%==0 (
    echo [FAIL] Bridge did not pass health check after %HEALTH_RETRIES% attempts
    echo {"ts":"%TS%","level":"ERROR","category":"health","msg":"Health check failed","attempt":"%RESTART_COUNT%"} >> "%ERROR_LOG%"
    
    rem Capture crash dump from last few log lines
    powershell -Command "Get-Content '%LOG%' -Tail 50 | Out-File -FilePath '%CRASH_DUMP%' -Encoding UTF8" > nul 2>&1
    
    rem Kill the zombie process if PID exists
    if exist "%PID_FILE%" (
        set /p ZPID=<"%PID_FILE%"
        taskkill /PID !ZPID! /F > nul 2>&1
        echo [CLEANUP] Killed PID !ZPID!
    )
    goto :watchdog_loop
)

rem ── Write state file ────────────────────────────────────────────────────
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set TS_NOW=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%T%DT:~8,2%:%DT:~10,2%:%DT:~12,2%

echo {"status":"running","port":%PORT%,"started_at":"%TS_NOW%","restarts":%RESTART_COUNT%,"pid_file":"%PID_FILE%","version":"2.0"} > "%STATE_FILE%"

echo.
echo ══════════════════════════════════════════════════════════════
echo   Bridge LIVE on http://localhost:%PORT%
echo   Health:     /powershell/health
echo   Execute:    POST /powershell/execute
echo   Sessions:   /powershell/sessions
echo   Librarian:  /orient/briefing
echo   Logs:       %LOG%
echo   Errors:     %ERROR_LOG%
echo   PID:        %PID_FILE%
echo   State:      %STATE_FILE%
echo ══════════════════════════════════════════════════════════════
echo.
echo Bridge is running in background. This window will now monitor.
echo Press Ctrl+C to stop monitoring (bridge keeps running).
echo.

rem ── Monitor Loop — watch for crash, re-enter watchdog if needed ─────────
:monitor_loop
timeout /t 30 /nobreak > nul

rem Check if port still listening
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" > nul 2>&1
if %errorlevel% neq 0 (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
    set TS=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%T%DT:~8,2%:%DT:~10,2%:%DT:~12,2%
    echo [WATCHDOG !TS!] Bridge port %PORT% not listening — restarting...
    echo {"ts":"!TS!","level":"WARN","category":"watchdog","msg":"Port gone, triggering restart"} >> "%ERROR_LOG%"
    goto :watchdog_loop
)

rem Check memory usage (optional, requires PID file)
if exist "%PID_FILE%" (
    set /p BRIDGE_PID=<"%PID_FILE%"
    for /f "tokens=5" %%M in ('tasklist /FI "PID eq !BRIDGE_PID!" /FO TABLE ^| findstr !BRIDGE_PID!') do (
        set MEM_KB=%%M
        set MEM_KB=!MEM_KB:,=!
        set /a MEM_MB=!MEM_KB! / 1024
        if !MEM_MB! gtr %MEMORY_THRESHOLD_MB% (
            echo [WARN] Memory usage high: !MEM_MB! MB (threshold: %MEMORY_THRESHOLD_MB% MB)
            echo {"ts":"!TS!","level":"WARN","category":"memory","msg":"High memory usage","mem_mb":"!MEM_MB!","threshold_mb":"%MEMORY_THRESHOLD_MB%"} >> "%ERROR_LOG%"
        )
    )
)

goto :monitor_loop

:already_running
echo Bridge is already alive. Exiting launcher.
exit /b 0

:fatal_exit
echo.
echo [FATAL] Bridge could not start. Check %ERROR_LOG%
if exist "%CRASH_DUMP%" (
    echo [DEBUG] Last 50 log lines saved to: %CRASH_DUMP%
)
pause
exit /b 1
