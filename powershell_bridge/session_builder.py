"""
PowerShell Bridge — Session builder.
Writes commands.json, run.ps1, and the defensive run.bat shim.
"""
import json
import uuid
from pathlib import Path
from datetime import datetime


def new_session_id() -> str:
    return uuid.uuid4().hex[:10]


def ensure_run_dir(runs_dir: Path, session_id: str) -> Path:
    d = (runs_dir / session_id).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_commands_json(run_dir: Path, payload: dict) -> Path:
    p = run_dir / "commands.json"
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def write_ps1(run_dir: Path) -> Path:
    """Write run.ps1 — reads commands.json, executes sequentially, writes report.json + run.log."""
    ps1 = run_dir / "run.ps1"
    ps1.write_text(r"""
param(
    [Parameter(Mandatory=$true)][string]$RunDir,
    [Parameter(Mandatory=$true)][string]$SessionId,
    [Parameter(Mandatory=$true)][string]$ErrorStrategy
)
$ErrorActionPreference = 'Continue'
$globalStart = Get-Date
$commandsPath = Join-Path $RunDir 'commands.json'
$reportPath   = Join-Path $RunDir 'report.json'
$logPath      = Join-Path $RunDir 'run.log'

function LogLine([string]$line) {
    $entry = ("{0} {1}" -f (Get-Date).ToString('s'), $line)
    Add-Content -Path $logPath -Value $entry -Encoding utf8
}

LogLine "START session=$SessionId"
$payload = Get-Content -Path $commandsPath -Raw -Encoding utf8 | ConvertFrom-Json
$results = @()

foreach ($c in $payload.commands) {
    $started = Get-Date
    $cmdText = [string]$c.command
    $wd = $null
    if ($c.PSObject.Properties.Name -contains 'working_dir') { $wd = $c.working_dir }
    try {
        if ($wd -and $wd.Trim().Length -gt 0) { Set-Location -Path $wd }
        LogLine "CMD $cmdText"
        $out = Invoke-Expression "$cmdText" 2>&1 | Out-String
        $results += [PSCustomObject]@{
            ok          = $true
            command     = $cmdText
            working_dir = $wd
            started_at  = $started.ToString('o')
            ended_at    = (Get-Date).ToString('o')
            output      = $out
        }
        LogLine "OK  $cmdText"
    } catch {
        $msg = $_.Exception.Message
        $results += [PSCustomObject]@{
            ok          = $false
            command     = $cmdText
            working_dir = $wd
            started_at  = $started.ToString('o')
            ended_at    = (Get-Date).ToString('o')
            error       = $msg
        }
        LogLine "FAIL $msg"
        if ($ErrorStrategy -eq 'halt') { break }
    }
}

$failed = ($results | Where-Object { $_.ok -ne $true }).Count
$status = if ($failed -gt 0) { 'failed' } else { 'success' }
$report = [PSCustomObject]@{
    session_id = $SessionId
    status     = $status
    started_at = $globalStart.ToString('o')
    ended_at   = (Get-Date).ToString('o')
    failed     = $failed
    results    = $results
}
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $reportPath -Encoding utf8
LogLine "END status=$status"
exit $(if ($failed -gt 0) { 1 } else { 0 })
""", encoding="utf-8")
    return ps1


def write_bat(run_dir: Path, session_id: str, error_strategy: str, powershell_exe: str) -> Path:
    """Write run.bat — the Windows-native filter shim that calls run.ps1."""
    bat = run_dir / "run.bat"
    bat.write_text(
        f"@echo off\n"
        f"setlocal\n"
        f"set RUNDIR={run_dir}\n"
        f"set SESSIONID={session_id}\n"
        f"set ERRORSTRATEGY={error_strategy}\n"
        f"{powershell_exe} -NoProfile -ExecutionPolicy Bypass "
        f"-File \"%RUNDIR%\\run.ps1\" "
        f"-RunDir \"%RUNDIR%\" "
        f"-SessionId \"%SESSIONID%\" "
        f"-ErrorStrategy \"%ERRORSTRATEGY%\"\n"
        f"exit /b %ERRORLEVEL%\n",
        encoding="utf-8"
    )
    return bat
