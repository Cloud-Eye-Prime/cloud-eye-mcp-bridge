@echo off
setlocal
set RUNDIR=C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge\ps_runs\670d0328b1
set SESSIONID=670d0328b1
set ERRORSTRATEGY=continue
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUNDIR%\run.ps1" -RunDir "%RUNDIR%" -SessionId "%SESSIONID%" -ErrorStrategy "%ERRORSTRATEGY%"
exit /b %ERRORLEVEL%
