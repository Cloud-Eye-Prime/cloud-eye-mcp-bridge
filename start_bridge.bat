@echo off
rem ── Cloud-Eye MCP Bridge — Startup Script ────────────────────────────────
rem Starts the FastAPI bridge server on port 8002 (background, detached)
rem Dragon constellation service: git/fs/railway/powershell/orient endpoints
setlocal

set BRIDGE_DIR=C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge
set PYTHON=%BRIDGE_DIR%\.venv\Scripts\python.exe
set PORT=8002
set CLOUD_EYE_API_TOKEN=wuji-neigong-2026
set LOG=%BRIDGE_DIR%\bridge_server.log

echo [%date% %time%] Starting Cloud-Eye MCP Bridge on port %PORT% >> %LOG%

start "CloudEye-MCP-Bridge" /B cmd /c "set PORT=%PORT%&& set CLOUD_EYE_API_TOKEN=%CLOUD_EYE_API_TOKEN%&& "%PYTHON%" "%BRIDGE_DIR%\cloud_eye_mcp_bridge.py"" >> %LOG% 2>&1

timeout /t 4 /nobreak >nul
echo Bridge start command issued. Check %LOG% for output.
exit /b 0
