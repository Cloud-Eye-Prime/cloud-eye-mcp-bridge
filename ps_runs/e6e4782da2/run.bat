@echo off
setlocal
set RUNDIR=C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge\ps_runs\e6e4782da2
set SESSIONID=e6e4782da2
set ERRORSTRATEGY=halt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUNDIR%\run.ps1" -RunDir "%RUNDIR%" -SessionId "%SESSIONID%" -ErrorStrategy "%ERRORSTRATEGY%"
exit /b %ERRORLEVEL%
