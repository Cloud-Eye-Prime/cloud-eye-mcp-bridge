@echo off
setlocal
set RUNDIR=C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge\ps_runs\aee9242e2d
set SESSIONID=aee9242e2d
set ERRORSTRATEGY=continue
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUNDIR%\run.ps1" -RunDir "%RUNDIR%" -SessionId "%SESSIONID%" -ErrorStrategy "%ERRORSTRATEGY%"
exit /b %ERRORLEVEL%
