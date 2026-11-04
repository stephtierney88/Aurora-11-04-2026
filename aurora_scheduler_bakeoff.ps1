param(
    [string[]]$Profiles = @("balanced", "responsive", "conservative"),
    [double]$DurationMinutes = 1.0,
    [bool]$LiveMode = $true,
    [bool]$WithUi = $false,
    [ValidateSet("", "firered", "blue")]
    [string]$GameProfile = "firered",
    [string]$InitMode = "test",
    [switch]$EnableOperatorDiagnostics,
    [ValidateSet("default", "interrogation")]
    [string]$OperatorDiagnosticProfile = "default",
    [double]$OperatorDiagnosticStartDelaySeconds = 10.0,
    [double]$OperatorDiagnosticIntervalSeconds = 20.0,
    [switch]$StopExistingRuntime
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$harnessPath = Join-Path $repoRoot "aurora_soak_harness.ps1"
$runRoot = Join-Path $repoRoot "soak_runs"
$summaryId = "aurora-scheduler-bakeoff-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$summaryDir = Join-Path $runRoot $summaryId
$summaryPath = Join-Path $summaryDir "summary.json"
$harnessDurationMinutes = [Math]::Max(1, [int][Math]::Ceiling($DurationMinutes))

function Get-RuntimeRows {
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*aurora2.py*" } |
        Select-Object ProcessId, CommandLine
}

function Stop-ExistingRuntimeRows {
    $rows = @(Get-RuntimeRows)
    foreach ($row in $rows) {
        try {
            Stop-Process -Id ([int]$row.ProcessId) -Force -ErrorAction Stop
        } catch {
            Write-Warning ("Failed to stop Aurora runtime PID {0}: {1}" -f $row.ProcessId, $_.Exception.Message)
        }
    }
    if ($rows.Count -gt 0) {
        Start-Sleep -Seconds 2
    }
}

function Get-LatestSoakRunPath {
    if (-not (Test-Path -LiteralPath $runRoot)) {
        return ""
    }
    $latest = Get-ChildItem -Path $runRoot -Directory |
        Where-Object { $_.Name -like "aurora-soak-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) {
        return $latest.FullName
    }
    return ""
}

function Get-RunDerivedMetrics {
    param($Report)

    $samples = @($Report.samples)
    $visibilityCounts = [ordered]@{}
    $screenshotHashes = New-Object 'System.Collections.Generic.HashSet[string]'
    $foregrounds = New-Object 'System.Collections.Generic.HashSet[string]'

    foreach ($sample in $samples) {
        $visibility = [string]$sample.gameplay_visibility
        if ([string]::IsNullOrWhiteSpace($visibility)) {
            $visibility = "unknown"
        }
        if (-not $visibilityCounts.Contains($visibility)) {
            $visibilityCounts[$visibility] = 0
        }
        $visibilityCounts[$visibility] = [int]$visibilityCounts[$visibility] + 1

        $hash = [string]$sample.screenshot_sha1
        if (-not [string]::IsNullOrWhiteSpace($hash)) {
            [void]$screenshotHashes.Add($hash)
        }

        $foreground = [string]$sample.gameplay_foreground_window
        if (-not [string]::IsNullOrWhiteSpace($foreground)) {
            [void]$foregrounds.Add($foreground)
        }
    }

    return [ordered]@{
        sample_count = $samples.Count
        unique_screenshot_hashes = $screenshotHashes.Count
        visibility_counts = $visibilityCounts
        distinct_foregrounds = @($foregrounds)
    }
}

if (-not (Test-Path -LiteralPath $harnessPath)) {
    throw "Harness not found at $harnessPath"
}

New-Item -ItemType Directory -Path $summaryDir -Force | Out-Null

if ($StopExistingRuntime) {
    Stop-ExistingRuntimeRows
}

$results = @()

foreach ($profile in $Profiles) {
    $normalizedProfile = ([string]$profile).Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($normalizedProfile)) {
        continue
    }

    Write-Host ("Running scheduler bakeoff profile: {0}" -f $normalizedProfile)

    $beforeLatest = Get-LatestSoakRunPath
    & $harnessPath `
        -Preset custom `
        -Launch `
        -DurationMinutes $harnessDurationMinutes `
        -WithUi:$WithUi `
        -LiveMode:$LiveMode `
        -LoadLiveInit:$false `
        -BattleProfile:$false `
        -GameProfile $GameProfile `
        -InitMode $InitMode `
        -TurnSchedulerProfile $normalizedProfile `
        -EnableUiStress:$false `
        -GameplayObstructionGraceSeconds 0 `
        -ForegroundMismatchGraceSeconds 0 `
        -EnableOperatorDiagnostics:$EnableOperatorDiagnostics `
        -OperatorDiagnosticProfile $OperatorDiagnosticProfile `
        -OperatorDiagnosticStartDelaySeconds $OperatorDiagnosticStartDelaySeconds `
        -OperatorDiagnosticIntervalSeconds $OperatorDiagnosticIntervalSeconds `
        -StopOnTimeout

    $afterLatest = Get-LatestSoakRunPath
    if (-not $afterLatest -or $afterLatest -eq $beforeLatest) {
        throw "Unable to find a new soak run directory after profile '$normalizedProfile'."
    }

    $reportPath = Join-Path $afterLatest "report.json"
    if (-not (Test-Path -LiteralPath $reportPath)) {
        throw "Missing report.json for profile '$normalizedProfile' at $afterLatest"
    }

    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $latestSample = $null
    if ($report.samples -and $report.samples.Count -gt 0) {
        $latestSample = $report.samples[-1]
    }
    $derivedMetrics = Get-RunDerivedMetrics -Report $report

    $results += [ordered]@{
        profile = $normalizedProfile
        verdict = [string]$report.verdict
        report = $reportPath
        monitor_log = [string]$report.artifacts.monitor_log
        runtime_pid = [int]$report.metrics.runtime_pid
        observed_scheduler_profile = [string]$report.metrics.observed_scheduler_profile
        observed_game_profile = [string]$report.metrics.observed_game_profile
        max_pending_commands = [int]$report.metrics.max_pending_commands
        runtime_child_pid_changes = [int]$report.metrics.runtime_child_pid_changes
        final_warnings = @($report.warnings)
        final_failures = @($report.failures)
        derived_metrics = $derivedMetrics
        latest_sample = $latestSample
    }

    Start-Sleep -Seconds 2
}

$summary = [ordered]@{
    run_id = $summaryId
    generated_at = (Get-Date).ToString("o")
    config = [ordered]@{
        profiles = $Profiles
        duration_minutes = $DurationMinutes
        harness_duration_minutes = $harnessDurationMinutes
        live_mode = $LiveMode
        with_ui = $WithUi
        game_profile = $GameProfile
        init_mode = $InitMode
        enable_operator_diagnostics = [bool]$EnableOperatorDiagnostics
        operator_diagnostic_profile = $OperatorDiagnosticProfile
        operator_diagnostic_start_delay_seconds = $OperatorDiagnosticStartDelaySeconds
        operator_diagnostic_interval_seconds = $OperatorDiagnosticIntervalSeconds
        stop_existing_runtime = [bool]$StopExistingRuntime
    }
    results = $results
}

$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
Write-Host ("Bakeoff summary written to {0}" -f $summaryPath)
