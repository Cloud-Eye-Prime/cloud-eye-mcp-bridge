
param(
    [Parameter(Mandatory=$true)][string]$RunDir,
    [Parameter(Mandatory=$true)][string]$SessionId,
    [Parameter(Mandatory=$true)][string]$ErrorStrategy
)
$ErrorActionPreference = 'Stop'
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
