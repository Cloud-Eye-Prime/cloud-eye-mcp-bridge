@echo off
setlocal
set RUNDIR=C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge\ps_runs\7ed263ee4e
set SESSIONID=7ed263ee4e
set ERRORSTRATEGY=halt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUNDIR%\run.ps1" -RunDir "%RUNDIR%" -SessionId "%SESSIONID%" -ErrorStrategy "%ERRORSTRATEGY%"
exit /b %ERRORLEVEL%
