<#
.SYNOPSIS
    Cloud-Eye Sync Bridge v2.0 - Git → Google Drive Sync with Error Handling

.DESCRIPTION
    Syncs documentation files from the cloud-eye-mcp-bridge repository to a Google Drive folder
    for automatic indexing in Perplexity Spaces via the Google Drive Connector.
    
    Features:
    - Pre-flight validation (source files exist, destination accessible)
    - Selective file sync (*.md, *.docx, *.pdf)
    - Structured error logging (JSON)
    - Retry logic for transient failures
    - Timestamp tracking for audit trail

.NOTES
    Author: Cloud-Eye Prime
    Version: 2.0
    Date: 2026-02-18
#>

[CmdletBinding()]
param(
    [string]$SourceDir = "C:\Users\grego\Desktop\CloudEye\production\cloud-eye-mcp-bridge",
    [string]$DestDir = "G:\My Drive\Cloud-Eye-Sync-Slot",
    [int]$MaxRetries = 3,
    [int]$RetryDelay = 5
)

# ── Configuration ────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"
$LogDir = Join-Path $SourceDir "logs"
$ErrorLog = Join-Path $LogDir "sync_errors.json"
$SyncLog = Join-Path $LogDir "sync_history.json"

# File patterns to sync
$SyncPatterns = @("*.md", "*.docx", "*.pdf")

# ── Helper Functions ─────────────────────────────────────────────────────────
function Get-Timestamp {
    return (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
}

function Write-StructuredLog {
    param(
        [string]$Level,
        [string]$Message,
        [hashtable]$Context = @{}
    )
    
    $entry = @{
        timestamp = Get-Timestamp
        level = $Level
        message = $Message
        context = $Context
    }
    
    $json = $entry | ConvertTo-Json -Compress
    Add-Content -Path $ErrorLog -Value $json
    
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        "INFO" { "Cyan" }
        default { "White" }
    }
    
    Write-Host "[$Level] $Message" -ForegroundColor $color
}

function Test-GoogleDriveAccess {
    param([string]$Path)
    
    try {
        # Test by creating and removing a marker file
        $testFile = Join-Path $Path ".sync_test_$(Get-Date -Format 'yyyyMMddHHmmss')"
        "test" | Out-File -FilePath $testFile -Force
        Remove-Item -Path $testFile -Force
        return $true
    }
    catch {
        return $false
    }
}

function Copy-FileWithRetry {
    param(
        [string]$Source,
        [string]$Destination,
        [int]$Retries = $MaxRetries
    )
    
    $attempt = 0
    $success = $false
    $lastError = $null
    
    while (-not $success -and $attempt -lt $Retries) {
        $attempt++
        try {
            Copy-Item -Path $Source -Destination $Destination -Force -ErrorAction Stop
            $success = $true
            Write-StructuredLog -Level "INFO" -Message "Synced: $(Split-Path $Source -Leaf)" -Context @{
                source = $Source
                destination = $Destination
                attempt = $attempt
            }
        }
        catch {
            $lastError = $_
            if ($attempt -lt $Retries) {
                Write-StructuredLog -Level "WARN" -Message "Retry $attempt/$Retries failed, waiting ${RetryDelay}s..." -Context @{
                    file = (Split-Path $Source -Leaf)
                    error = $_.Exception.Message
                }
                Start-Sleep -Seconds $RetryDelay
            }
        }
    }
    
    if (-not $success) {
        Write-StructuredLog -Level "ERROR" -Message "Failed to sync after $Retries attempts" -Context @{
            file = (Split-Path $Source -Leaf)
            error = $lastError.Exception.Message
        }
        return $false
    }
    
    return $true
}

# ── Main Execution ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Cloud-Eye Sync Bridge v2.0" -ForegroundColor Cyan
Write-Host "  $(Get-Timestamp)" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── Pre-Flight 1: Ensure log directory exists ────────────────────────────────
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Host "[OK] Created log directory: $LogDir" -ForegroundColor Green
}

# ── Pre-Flight 2: Validate source directory ──────────────────────────────────
if (-not (Test-Path $SourceDir)) {
    Write-StructuredLog -Level "ERROR" -Message "Source directory not found" -Context @{
        path = $SourceDir
    }
    exit 1
}
Write-Host "[OK] Source directory: $SourceDir" -ForegroundColor Green

# ── Pre-Flight 3: Validate destination directory ─────────────────────────────
if (-not (Test-Path $DestDir)) {
    Write-StructuredLog -Level "ERROR" -Message "Destination directory not found (Google Drive not mounted?)" -Context @{
        path = $DestDir
    }
    exit 1
}
Write-Host "[OK] Destination directory: $DestDir" -ForegroundColor Green

# ── Pre-Flight 4: Test write access to Google Drive ──────────────────────────
if (-not (Test-GoogleDriveAccess -Path $DestDir)) {
    Write-StructuredLog -Level "ERROR" -Message "Cannot write to Google Drive (permissions issue?)" -Context @{
        path = $DestDir
    }
    exit 1
}
Write-Host "[OK] Google Drive write access confirmed" -ForegroundColor Green
Write-Host ""

# ── Sync Files ───────────────────────────────────────────────────────────────
$syncStartTime = Get-Date
$filesProcessed = 0
$filesSucceeded = 0
$filesFailed = 0

Write-Host "[SYNC] Starting file sync..." -ForegroundColor Yellow
Write-Host ""

foreach ($pattern in $SyncPatterns) {
    $files = Get-ChildItem -Path $SourceDir -Filter $pattern -File -ErrorAction SilentlyContinue
    
    foreach ($file in $files) {
        $filesProcessed++
        $destPath = Join-Path $DestDir $file.Name
        
        if (Copy-FileWithRetry -Source $file.FullName -Destination $destPath) {
            $filesSucceeded++
        } else {
            $filesFailed++
        }
    }
}

$syncEndTime = Get-Date
$duration = ($syncEndTime - $syncStartTime).TotalSeconds

# ── Write Sync Summary ───────────────────────────────────────────────────────
$summary = @{
    timestamp = Get-Timestamp
    duration_seconds = [math]::Round($duration, 2)
    files_processed = $filesProcessed
    files_succeeded = $filesSucceeded
    files_failed = $filesFailed
    source_dir = $SourceDir
    dest_dir = $DestDir
}

$summaryJson = $summary | ConvertTo-Json -Compress
Add-Content -Path $SyncLog -Value $summaryJson

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Sync Complete" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Files Processed: $filesProcessed" -ForegroundColor White
Write-Host "  Succeeded: $filesSucceeded" -ForegroundColor Green
Write-Host "  Failed: $filesFailed" -ForegroundColor $(if ($filesFailed -gt 0) { "Red" } else { "Green" })
Write-Host "  Duration: $([math]::Round($duration, 2))s" -ForegroundColor White
Write-Host "  Logs: $ErrorLog" -ForegroundColor Gray
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

if ($filesFailed -gt 0) {
    Write-Host "[WARN] Some files failed to sync. Check error log for details." -ForegroundColor Yellow
    exit 1
}

exit 0
