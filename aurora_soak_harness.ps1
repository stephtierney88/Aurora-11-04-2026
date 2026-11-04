param(
    [ValidateSet("preflight", "offline30-ui", "offline30-headless", "offline60-ui", "overnight-ui", "pokemon1-ui-testinit", "pokemon5-ui-liveinit", "custom")]
    [string]$Preset = "offline30-ui",
    [switch]$Launch,
    [int]$RuntimePid = 0,
    [int]$DurationMinutes = 0,
    [Nullable[bool]]$WithUi = $null,
    [Nullable[bool]]$LiveMode = $null,
    [Nullable[bool]]$LoadLiveInit = $null,
    [Nullable[bool]]$BattleProfile = $null,
    [ValidateSet("", "firered", "blue")]
    [string]$GameProfile = "",
    [string]$InitMode = "",
    [double]$ScreenshotIntervalSeconds = 0,
    [int]$ReviewTurnInterval = 0,
    [int]$CritiqueTurnInterval = 0,
    [ValidateSet("", "none", "low", "medium", "high")]
    [string]$ReviewThinking = "",
    [ValidateSet("", "none", "low", "medium", "high")]
    [string]$CritiqueThinking = "",
    [ValidateSet("", "balanced", "responsive", "conservative", "legacy")]
    [string]$TurnSchedulerProfile = "",
    [switch]$EnableStartupSmoke,
    [string]$SmokeProfile = "confirm_cursor_until_progress",
    [int]$SmokeMaxCycles = 0,
    [double]$SmokeExitAfterSeconds = 0,
    [double]$PollSeconds = 2.0,
    [double]$StartupGraceSeconds = 0,
    [double]$StateStaleSeconds = 0,
    [double]$ScreenshotStaleSeconds = 0,
    [double]$GameplayObstructionGraceSeconds = 0,
    [double]$QueueDrainGraceSeconds = 0,
    [int]$PendingQueueLimit = 12,
    [int]$ChildProcessChangeLimit = 4,
    [double]$MaxCombinedLogGrowthMbPerHour = 25.0,
    [Nullable[bool]]$EnableUiStress = $null,
    [double]$UiStressStartDelaySeconds = 0,
    [double]$UiStressStateFreshSeconds = 0,
    [double]$UiStressTimeoutSeconds = 0,
    [switch]$InjectStaleStartupArtifacts,
    [switch]$InjectScreenshotCaptureFailureOnce,
    [switch]$InjectPendingQueueFlood,
    [int]$PendingQueueFloodCount = 0,
    [double]$PendingQueueFloodStartDelaySeconds = 0,
    [double]$PendingQueueFloodDrainDelaySeconds = 0,
    [switch]$InjectEmulatorMinimizeOnce,
    [double]$EmulatorMinimizeStartDelaySeconds = 0,
    [double]$EmulatorMinimizeDurationSeconds = 0,
    [Nullable[bool]]$ForceEmulatorForegroundOnStart = $null,
    [Nullable[bool]]$MaximizeEmulatorOnStart = $null,
    [switch]$ToggleEmulatorFullscreenOnStart,
    [double]$EmulatorForegroundStartDelaySeconds = 0,
    [double]$ForegroundMismatchGraceSeconds = 0,
    [double]$ForegroundRecoveryIntervalSeconds = 0,
    [switch]$EnableOperatorDiagnostics,
    [ValidateSet("", "default", "interrogation")]
    [string]$OperatorDiagnosticProfile = "",
    [double]$OperatorDiagnosticStartDelaySeconds = 0,
    [double]$OperatorDiagnosticIntervalSeconds = 0,
    [Nullable[bool]]$EnableGameplayAutoExecution = $null,
    [switch]$StopOnTimeout,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

function Get-DefaultPresetConfig {
    param([string]$PresetName)

    switch ($PresetName) {
        "preflight" {
            return @{
                DurationMinutes = 3
                WithUi = $true
                LiveMode = $false
                LoadLiveInit = $false
                BattleProfile = $false
                InitMode = "test"
                ScreenshotIntervalSeconds = 0.20
                ReviewTurnInterval = 8
                CritiqueTurnInterval = 24
                ReviewThinking = "medium"
                CritiqueThinking = "high"
                EnableStartupSmoke = $true
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $true
                UiStressStartDelaySeconds = 20.0
            }
        }
        "offline30-ui" {
            return @{
                DurationMinutes = 30
                WithUi = $true
                LiveMode = $false
                LoadLiveInit = $false
                BattleProfile = $false
                InitMode = "test"
                ScreenshotIntervalSeconds = 0.35
                ReviewTurnInterval = 12
                CritiqueTurnInterval = 45
                ReviewThinking = "medium"
                CritiqueThinking = "high"
                EnableStartupSmoke = $false
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $true
                UiStressStartDelaySeconds = 20.0
            }
        }
        "offline30-headless" {
            return @{
                DurationMinutes = 30
                WithUi = $false
                LiveMode = $false
                LoadLiveInit = $false
                BattleProfile = $false
                InitMode = "test"
                ScreenshotIntervalSeconds = 0.35
                ReviewTurnInterval = 12
                CritiqueTurnInterval = 45
                ReviewThinking = "medium"
                CritiqueThinking = "high"
                EnableStartupSmoke = $false
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $false
                UiStressStartDelaySeconds = 0.0
            }
        }
        "offline60-ui" {
            return @{
                DurationMinutes = 60
                WithUi = $true
                LiveMode = $false
                LoadLiveInit = $false
                BattleProfile = $false
                InitMode = "test"
                ScreenshotIntervalSeconds = 0.50
                ReviewTurnInterval = 16
                CritiqueTurnInterval = 60
                ReviewThinking = "medium"
                CritiqueThinking = "high"
                EnableStartupSmoke = $false
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $true
                UiStressStartDelaySeconds = 20.0
            }
        }
        "overnight-ui" {
            return @{
                DurationMinutes = 480
                WithUi = $true
                LiveMode = $false
                LoadLiveInit = $false
                BattleProfile = $false
                InitMode = "test"
                ScreenshotIntervalSeconds = 1.50
                ReviewTurnInterval = 24
                CritiqueTurnInterval = 90
                ReviewThinking = "low"
                CritiqueThinking = "medium"
                EnableStartupSmoke = $false
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $true
                UiStressStartDelaySeconds = 30.0
            }
        }
        "pokemon1-ui-testinit" {
            return @{
                DurationMinutes = 1
                WithUi = $true
                LiveMode = $true
                LoadLiveInit = $false
                BattleProfile = $true
                GameProfile = "firered"
                InitMode = "test"
                ScreenshotIntervalSeconds = 0.45
                ReviewTurnInterval = 6
                CritiqueTurnInterval = 18
                ReviewThinking = "low"
                CritiqueThinking = "medium"
                EnableStartupSmoke = $false
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $false
                UiStressStartDelaySeconds = 0.0
                EnableGameplayAutoExecution = $true
                ForceEmulatorForegroundOnStart = $true
                MaximizeEmulatorOnStart = $true
            }
        }
        "pokemon5-ui-liveinit" {
            return @{
                DurationMinutes = 5
                WithUi = $true
                LiveMode = $true
                LoadLiveInit = $true
                BattleProfile = $true
                GameProfile = "firered"
                InitMode = "load"
                ScreenshotIntervalSeconds = 0.40
                ReviewTurnInterval = 8
                CritiqueTurnInterval = 24
                ReviewThinking = "medium"
                CritiqueThinking = "high"
                EnableStartupSmoke = $false
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $true
                UiStressStartDelaySeconds = 45.0
                EnableGameplayAutoExecution = $true
                ForceEmulatorForegroundOnStart = $true
                MaximizeEmulatorOnStart = $true
            }
        }
        default {
            return @{
                DurationMinutes = 30
                WithUi = $true
                LiveMode = $false
                LoadLiveInit = $false
                BattleProfile = $false
                InitMode = "test"
                ScreenshotIntervalSeconds = 0.35
                ReviewTurnInterval = 12
                CritiqueTurnInterval = 45
                ReviewThinking = "medium"
                CritiqueThinking = "high"
                EnableStartupSmoke = $false
                SmokeProfile = "confirm_cursor_until_progress"
                SmokeMaxCycles = 4
                SmokeExitAfterSeconds = 90
                EnableUiStress = $true
                UiStressStartDelaySeconds = 20.0
                EnableGameplayAutoExecution = $false
            }
        }
    }
}

if (-not ([System.Management.Automation.PSTypeName]'AuroraHarness.NativeMethods').Type) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
namespace AuroraHarness {
    public static class NativeMethods {
        [DllImport("user32.dll")]
        public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);
    }
}
"@
}

$SW_SHOWNORMAL = 1
$SW_SHOWMINIMIZED = 2
$SW_SHOWMAXIMIZED = 3
$SW_MINIMIZE = 6
$SW_RESTORE = 9

function Resolve-Setting {
    param(
        [object]$CurrentValue,
        [object]$DefaultValue
    )

    if ($null -eq $CurrentValue) {
        return $DefaultValue
    }
    if ($CurrentValue -is [string]) {
        if ([string]::IsNullOrWhiteSpace($CurrentValue)) {
            return $DefaultValue
        }
        return $CurrentValue
    }
    if ($CurrentValue -is [int] -or $CurrentValue -is [double]) {
        if ([double]$CurrentValue -le 0) {
            return $DefaultValue
        }
        return $CurrentValue
    }
    return $CurrentValue
}

function Get-AuroraProcessRows {
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'aurora2\.py' -or
            $_.CommandLine -match 'aurora2_control_panel\.py'
        )
    } | Select-Object ProcessId, ParentProcessId, Name, CommandLine
}

function Get-RuntimeProcessRows {
    Get-AuroraProcessRows | Where-Object { $_.CommandLine -match 'aurora2\.py' -and $_.CommandLine -notmatch 'aurora2_control_panel\.py' }
}

function Get-ControlPanelProcessRows {
    Get-AuroraProcessRows | Where-Object { $_.CommandLine -match 'aurora2_control_panel\.py' }
}

function Test-PidAlive {
    param([int]$TargetPid)
    if ($TargetPid -le 0) {
        return $false
    }
    return $null -ne (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue)
}

function Read-JsonFileRetry {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        try {
            return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
        } catch {
            Start-Sleep -Milliseconds 120
        }
    }
    return $null
}

function Wait-ForJsonFile {
    param(
        [string]$Path,
        [double]$TimeoutSeconds = 5.0
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $payload = Read-JsonFileRetry -Path $Path
        if ($payload) {
            return $payload
        }
        Start-Sleep -Milliseconds 250
    }
    return $null
}

function Get-FileSignature {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    try {
        $item = Get-Item -LiteralPath $Path
    } catch {
        return $null
    }

    $hashText = ""
    try {
        $hash = Get-FileHash -LiteralPath $Path -Algorithm SHA1 -ErrorAction Stop
        $hashText = $hash.Hash.ToLowerInvariant()
    } catch {
        # Screenshots can be sampled while the writer still has the file open.
        # Keep the signature usable for freshness checks even if the hash is temporarily unavailable.
        $hashText = ""
    }

    return [ordered]@{
        path = $item.FullName
        length = [int64]$item.Length
        mtime_utc = $item.LastWriteTimeUtc.ToString("o")
        sha1 = $hashText
    }
}

function Add-ReportLine {
    param(
        [string]$LogPath,
        [string]$Message
    )

    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[${timestamp}] $Message"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Write-ExternalInboxRecord {
    param(
        [string]$InboxPath,
        [string]$Text,
        [string]$LogPath,
        [string]$Source = "soak_harness",
        [string]$Author = "user",
        [string]$Subject = "",
        [bool]$Raw = $false
    )

    $record = [ordered]@{
        message_id = "{0}-{1}" -f [int64]([DateTimeOffset]::Now.ToUnixTimeMilliseconds()), (Get-Random -Minimum 100000 -Maximum 999999)
        timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        author = $Author
        source = $Source
        subject = $(if ($Subject) { $Subject } else { $Source })
        text = $Text
        metadata = [ordered]@{
            requested_by = "aurora_soak_harness"
            ingest_mode = $(if ($Raw) { "raw" } else { "normal" })
        }
    }
    Add-Content -LiteralPath $InboxPath -Value ($record | ConvertTo-Json -Compress -Depth 6) -Encoding UTF8
    return $record
}

function Request-CleanRuntimeShutdown {
    param(
        [string]$InboxPath,
        [string]$LogPath
    )

    [void](Write-ExternalInboxRecord -InboxPath $InboxPath -Text "SHUTDOWN_RUNTIME()" -LogPath $LogPath -Source "soak_harness" -Subject "runtime shutdown" -Raw $true)
    Add-ReportLine -LogPath $LogPath -Message "Queued SHUTDOWN_RUNTIME() through aurora_external_inbox.jsonl"
}

function Get-EmulatorWindowProcess {
    param([string]$WindowHint = "VBA-RR")

    $rawHint = if ($null -eq $WindowHint) { "" } else { [string]$WindowHint }
    $hint = [WildcardPattern]::Escape($rawHint.Trim())
    if ([string]::IsNullOrWhiteSpace($hint)) {
        return $null
    }
    return Get-Process | Where-Object {
        $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -and $_.MainWindowTitle -like "*$hint*"
    } | Sort-Object Id | Select-Object -First 1
}

function Invoke-EmulatorMinimize {
    param(
        [string]$WindowHint,
        [string]$LogPath
    )

    $proc = Get-EmulatorWindowProcess -WindowHint $WindowHint
    if (-not $proc) {
        return [ordered]@{ ok = $false; reason = "No emulator window matched '$WindowHint'."; pid = 0; title = "" }
    }
    [void][AuroraHarness.NativeMethods]::ShowWindowAsync($proc.MainWindowHandle, $SW_MINIMIZE)
    Add-ReportLine -LogPath $LogPath -Message "Minimized emulator window PID=$($proc.Id) title='$($proc.MainWindowTitle)'."
    return [ordered]@{ ok = $true; reason = "minimized"; pid = [int]$proc.Id; title = $proc.MainWindowTitle }
}

function Invoke-EmulatorRestore {
    param(
        [string]$WindowHint,
        [string]$LogPath
    )

    $proc = Get-EmulatorWindowProcess -WindowHint $WindowHint
    if (-not $proc) {
        return [ordered]@{ ok = $false; reason = "No emulator window matched '$WindowHint'."; pid = 0; title = "" }
    }
    [void][AuroraHarness.NativeMethods]::ShowWindowAsync($proc.MainWindowHandle, $SW_RESTORE)
    Start-Sleep -Milliseconds 200
    [void][AuroraHarness.NativeMethods]::SetForegroundWindow($proc.MainWindowHandle)
    Add-ReportLine -LogPath $LogPath -Message "Restored emulator window PID=$($proc.Id) title='$($proc.MainWindowTitle)'."
    return [ordered]@{ ok = $true; reason = "restored"; pid = [int]$proc.Id; title = $proc.MainWindowTitle }
}

function Invoke-EmulatorForegroundSetup {
    param(
        [string]$WindowHint,
        [bool]$Maximize,
        [bool]$ToggleFullscreen,
        [string]$LogPath
    )

    $proc = Get-EmulatorWindowProcess -WindowHint $WindowHint
    if (-not $proc) {
        return [ordered]@{ ok = $false; reason = "No emulator window matched '$WindowHint'."; pid = 0; title = ""; fullscreen = $false; maximized = $false }
    }

    $showMode = $(if ($Maximize) { $SW_SHOWMAXIMIZED } else { $SW_RESTORE })
    [void][AuroraHarness.NativeMethods]::ShowWindowAsync($proc.MainWindowHandle, $showMode)
    Start-Sleep -Milliseconds 250
    [void][AuroraHarness.NativeMethods]::SetForegroundWindow($proc.MainWindowHandle)
    Start-Sleep -Milliseconds 250

    $fullscreenToggled = $false
    if ($ToggleFullscreen) {
        try {
            $shell = New-Object -ComObject WScript.Shell
            [void]$shell.AppActivate($proc.Id)
            Start-Sleep -Milliseconds 150
            $shell.SendKeys('%{ENTER}')
            Start-Sleep -Milliseconds 350
            $fullscreenToggled = $true
        } catch {
            Add-ReportLine -LogPath $LogPath -Message ("WARN: Emulator fullscreen toggle failed: {0}" -f $_.Exception.Message)
        }
    }

    Add-ReportLine -LogPath $LogPath -Message ("Prepared emulator foreground PID={0} title='{1}' maximize={2} fullscreen_toggle={3}." -f $proc.Id, $proc.MainWindowTitle, $Maximize, $fullscreenToggled)
    return [ordered]@{
        ok = $true
        reason = "foreground_prepared"
        pid = [int]$proc.Id
        title = $proc.MainWindowTitle
        maximized = [bool]$Maximize
        fullscreen = [bool]$fullscreenToggled
    }
}

function Invoke-EmulatorDismissMenu {
    param(
        [string]$WindowHint,
        [string]$LogPath
    )

    $proc = Get-EmulatorWindowProcess -WindowHint $WindowHint
    if (-not $proc) {
        return [ordered]@{ ok = $false; reason = "No emulator window matched '$WindowHint'."; pid = 0; title = "" }
    }

    try {
        $shell = New-Object -ComObject WScript.Shell
        [void]$shell.AppActivate($proc.Id)
        Start-Sleep -Milliseconds 120
        $shell.SendKeys('{ESC}')
        Start-Sleep -Milliseconds 200
        Add-ReportLine -LogPath $LogPath -Message ("Sent ESC to emulator PID={0} title='{1}' to dismiss a stray menu/dropdown." -f $proc.Id, $proc.MainWindowTitle)
        return [ordered]@{ ok = $true; reason = "escape_sent"; pid = [int]$proc.Id; title = $proc.MainWindowTitle }
    } catch {
        return [ordered]@{ ok = $false; reason = $_.Exception.Message; pid = [int]$proc.Id; title = $proc.MainWindowTitle }
    }
}

function Get-PendingFloodCommands {
    param([int]$Count)

    $templates = @(
        'UPDATE_CONTEXT(flood_probe_ctx_{0:D2})',
        'ADD_GOAL(flood_goal_{0:D2};low;diagnostic)',
        'ADD_APRIORITY_GOAL(flood_apriority_{0:D2})',
        'ADD_UNKNOWN_PRIORITY(flood_unknown_{0:D2})',
        'UPDATE_CURRENT_AREA(flood_area_{0:D2})',
        'UPDATE_TARGET_AREA(flood_target_{0:D2})',
        'UPDATE_TRAVEL_HEADING(flood_heading_{0:D2})',
        'UPDATE_LAST_LANDMARK(flood_landmark_{0:D2})',
        'UPDATE_ROUTE_INTENT(flood_route_{0:D2})',
        'UPDATE_LOCAL_PATH_PLAN(flood_step_{0:D2})',
        'UPDATE_ROUTE_BLOCKERS(flood_blocker_{0:D2})',
        'UPDATE_RECENT_MOVEMENT_RESULTS(flood_result_{0:D2})',
        'UPDATE_NOTES(flood_note_{0:D2})',
        'ADD_JOURNAL(flood_journal_{0:D2})',
        'UPDATE_PINNED_IMMEDIATE(flood_immediate_{0:D2})',
        'UPDATE_PINNED_SHORT_TERM(flood_short_{0:D2})',
        'GB:press(a)',
        'GB:press(b)',
        'GB:Start',
        'GB:Select',
        'GB:move_key(up, 1)',
        'GB:move_key(down, 1)',
        'GB:move_key(left, 1)',
        'GB:move_key(right, 1)',
        'PYAG:move(100, 100, 0.05)',
        'PYAG:click(100, 100, left)'
    )

    $commands = @()
    for ($index = 0; $index -lt $Count; $index++) {
        $template = $templates[$index % $templates.Count]
        $commands += ('QUEUE_PENDING(' + ($template -f ($index + 1)) + ')')
    }
    return $commands
}

function Get-OperatorDiagnosticMessages {
    param(
        [string]$Profile = "default",
        [string]$GameProfile = "firered"
    )

    $normalizedProfile = if ([string]::IsNullOrWhiteSpace($Profile)) { "default" } else { $Profile.Trim().ToLowerInvariant() }
    $normalizedGameProfile = if ([string]::IsNullOrWhiteSpace($GameProfile)) { "firered" } else { $GameProfile.Trim().ToLowerInvariant() }
    $gameLabel = if ($normalizedGameProfile -eq "blue") { "Pokemon Blue" } else { "Pokemon FireRed" }
    $saveNote = if ($normalizedGameProfile -eq "blue") {
        "Treat emulator save-state handling as operator-only; do not invent runtime save/load commands."
    } else {
        "On this VBA-RR setup, in-game SAVE is not trusted as emulator persistence. Slot #1 save-state is operator/manual via F1 and load/restart from slot #1 is operator/manual via Shift+F1. Do not invent runtime save/load commands."
    }
    if ($normalizedProfile -eq "interrogation") {
        return @(
            [ordered]@{
                author = "system"
                source = "system_supervisor"
                subject = "context interrogation"
                text = "System supervisor check for ${gameLabel}: say exactly what primary window or scene you believe is visible right now, cite two concrete visual cues from the latest screenshot, and state whether gameplay input is safe to attempt. $saveNote"
            },
            [ordered]@{
                author = "user"
                source = "tester_diagnostic"
                subject = "action trace"
                text = "Tester question for ${gameLabel}: what do you believe your most recent action or pending action was, what evidence suggests it executed or failed, and what mismatch if any exists between chat history and the latest screenshot? $saveNote"
            },
            [ordered]@{
                author = "system"
                source = "system_supervisor"
                subject = "obstruction triage"
                text = "System supervisor check for ${gameLabel}: if gameplay is obstructed or uncertain, name the likely blocker such as wrong foreground window, emulator menu, desktop/editor view, or collision, then state the safest recovery command. $saveNote"
            },
            [ordered]@{
                author = "user"
                source = "tester_diagnostic"
                subject = "context coherence"
                text = "Tester question for ${gameLabel}: summarize the minimal context you think you currently have from screenshot, state snapshot, and recent messages, and explicitly call out anything you are uncertain or missing. $saveNote"
            }
        )
    }

    return @(
        [ordered]@{
            author = "user"
            source = "tester_diagnostic"
            subject = "tester diagnostic"
            text = "Supervisor diagnostic for ${gameLabel}: briefly state what window or scene you believe is visible, whether the emulator appears unobstructed, and the one best next gameplay action if confidence is high. $saveNote"
        },
        [ordered]@{
            author = "user"
            source = "tester_diagnostic"
            subject = "tester diagnostic"
            text = "Supervisor diagnostic for ${gameLabel}: if the last gameplay input did not seem to land, say whether focus loss, menu state, or world collision is the more likely blocker before suggesting the next step. $saveNote"
        },
        [ordered]@{
            author = "user"
            source = "tester_diagnostic"
            subject = "tester diagnostic"
            text = "Supervisor note for ${gameLabel}: if progress feels blocked, update recent movement results or route blockers before trying a different move."
        },
        [ordered]@{
            author = "user"
            source = "tester_diagnostic"
            subject = "tester diagnostic"
            text = "Supervisor note for ${gameLabel}: keep using semantic GB commands, stay grounded in the latest screenshot, and explicitly say when you are uncertain what is on screen. $saveNote"
        }
    )
}

function Read-NewTracebackMatches {
    param(
        [string]$Path,
        [long]$Offset
    )

    $result = [ordered]@{
        offset = $Offset
        matches = @()
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        return $result
    }

    $stream = $null
    try {
        $stream = New-Object System.IO.FileStream(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        if ($stream.Length -le $Offset) {
            return $result
        }

        $stream.Seek($Offset, [System.IO.SeekOrigin]::Begin) | Out-Null
        $newLength = [int]($stream.Length - $Offset)
        $buffer = New-Object byte[] $newLength
        [void]$stream.Read($buffer, 0, $buffer.Length)
        $text = [System.Text.Encoding]::UTF8.GetString($buffer)
        $result.offset = [long]$stream.Length
    } finally {
        if ($stream) {
            $stream.Dispose()
        }
    }

    foreach ($pattern in @("Traceback \(most recent call last\):", "Fatal Python error:", "terminated with an exception:", "Process '.*' terminated unexpectedly\. Restarting")) {
        $matches = [regex]::Matches($text, $pattern)
        foreach ($match in $matches) {
            $result.matches += $match.Value
        }
    }
    return $result
}

function Resolve-PanelPid {
    param(
        [string]$PidFilePath
    )

    if (Test-Path -LiteralPath $PidFilePath) {
        try {
            $raw = (Get-Content -LiteralPath $PidFilePath -Raw -Encoding UTF8).Trim()
            $pidValue = 0
            if ([int]::TryParse($raw, [ref]$pidValue) -and (Test-PidAlive -TargetPid $pidValue)) {
                return $pidValue
            }
        } catch {
        }
    }

    $panelRows = Get-ControlPanelProcessRows
    if ($panelRows.Count -eq 1) {
        return [int]$panelRows[0].ProcessId
    }
    if ($panelRows.Count -gt 1) {
        return [int](($panelRows | Sort-Object ProcessId -Descending | Select-Object -First 1).ProcessId)
    }
    return 0
}

function Wait-ForNewRuntimePid {
    param(
        [System.Collections.Generic.HashSet[int]]$BaselineIds,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $rows = Get-RuntimeProcessRows | Sort-Object ProcessId -Descending
        foreach ($row in $rows) {
            if (-not $BaselineIds.Contains([int]$row.ProcessId)) {
                return [int]$row.ProcessId
            }
        }
        Start-Sleep -Milliseconds 500
    }
    return 0
}

$presetConfig = Get-DefaultPresetConfig -PresetName $Preset

$DurationMinutes = [int](Resolve-Setting -CurrentValue $DurationMinutes -DefaultValue $presetConfig.DurationMinutes)
$WithUi = [bool](Resolve-Setting -CurrentValue $WithUi -DefaultValue $presetConfig.WithUi)
$LiveMode = [bool](Resolve-Setting -CurrentValue $LiveMode -DefaultValue $presetConfig.LiveMode)
$LoadLiveInit = [bool](Resolve-Setting -CurrentValue $LoadLiveInit -DefaultValue $presetConfig.LoadLiveInit)
$BattleProfile = [bool](Resolve-Setting -CurrentValue $BattleProfile -DefaultValue $presetConfig.BattleProfile)
$GameProfile = [string](Resolve-Setting -CurrentValue $GameProfile -DefaultValue $(if ($presetConfig.ContainsKey('GameProfile')) { $presetConfig.GameProfile } else { "firered" }))
$InitMode = [string](Resolve-Setting -CurrentValue $InitMode -DefaultValue $presetConfig.InitMode)
$ScreenshotIntervalSeconds = [double](Resolve-Setting -CurrentValue $ScreenshotIntervalSeconds -DefaultValue $presetConfig.ScreenshotIntervalSeconds)
$ReviewTurnInterval = [int](Resolve-Setting -CurrentValue $ReviewTurnInterval -DefaultValue $presetConfig.ReviewTurnInterval)
$CritiqueTurnInterval = [int](Resolve-Setting -CurrentValue $CritiqueTurnInterval -DefaultValue $presetConfig.CritiqueTurnInterval)
$ReviewThinking = [string](Resolve-Setting -CurrentValue $ReviewThinking -DefaultValue $presetConfig.ReviewThinking)
$CritiqueThinking = [string](Resolve-Setting -CurrentValue $CritiqueThinking -DefaultValue $presetConfig.CritiqueThinking)
$TurnSchedulerProfile = [string](Resolve-Setting -CurrentValue $TurnSchedulerProfile -DefaultValue $(if ($presetConfig.ContainsKey('TurnSchedulerProfile')) { $presetConfig.TurnSchedulerProfile } else { "" }))
$resolvedSmoke = if ($PSBoundParameters.ContainsKey("EnableStartupSmoke")) { [bool]$EnableStartupSmoke } else { [bool]$presetConfig.EnableStartupSmoke }
$SmokeProfile = [string](Resolve-Setting -CurrentValue $SmokeProfile -DefaultValue $presetConfig.SmokeProfile)
$SmokeMaxCycles = [int](Resolve-Setting -CurrentValue $SmokeMaxCycles -DefaultValue $presetConfig.SmokeMaxCycles)
$SmokeExitAfterSeconds = [double](Resolve-Setting -CurrentValue $SmokeExitAfterSeconds -DefaultValue $presetConfig.SmokeExitAfterSeconds)
$PollSeconds = [double](Resolve-Setting -CurrentValue $PollSeconds -DefaultValue 2.0)
$StartupGraceSeconds = [double](Resolve-Setting -CurrentValue $StartupGraceSeconds -DefaultValue $(if ($LiveMode) { 45.0 } else { 12.0 }))
$StateStaleSeconds = [double](Resolve-Setting -CurrentValue $StateStaleSeconds -DefaultValue ([Math]::Max($(if ($LiveMode) { 45.0 } else { 10.0 }), $ScreenshotIntervalSeconds * 20.0)))
$ScreenshotStaleSeconds = [double](Resolve-Setting -CurrentValue $ScreenshotStaleSeconds -DefaultValue ([Math]::Max($(if ($LiveMode) { 60.0 } else { 25.0 }), $ScreenshotIntervalSeconds * 40.0)))
$GameplayObstructionGraceSeconds = if ($PSBoundParameters.ContainsKey("GameplayObstructionGraceSeconds")) { [double]$GameplayObstructionGraceSeconds } else { [double](Resolve-Setting -CurrentValue $GameplayObstructionGraceSeconds -DefaultValue $(if ($LiveMode) { 30.0 } else { 0.0 })) }
$QueueDrainGraceSeconds = [double](Resolve-Setting -CurrentValue $QueueDrainGraceSeconds -DefaultValue ([Math]::Max(90.0, $ScreenshotStaleSeconds)))
$EnableUiStress = [bool](Resolve-Setting -CurrentValue $EnableUiStress -DefaultValue $presetConfig.EnableUiStress)
$UiStressStartDelaySeconds = [double](Resolve-Setting -CurrentValue $UiStressStartDelaySeconds -DefaultValue $(if ($EnableUiStress) { $presetConfig.UiStressStartDelaySeconds } else { 0.0 }))
$UiStressStateFreshSeconds = [double](Resolve-Setting -CurrentValue $UiStressStateFreshSeconds -DefaultValue ([Math]::Max(30.0, $StateStaleSeconds)))
$UiStressTimeoutSeconds = [double](Resolve-Setting -CurrentValue $UiStressTimeoutSeconds -DefaultValue 180.0)
$PendingQueueFloodCount = [int](Resolve-Setting -CurrentValue $PendingQueueFloodCount -DefaultValue 18)
$PendingQueueFloodStartDelaySeconds = [double](Resolve-Setting -CurrentValue $PendingQueueFloodStartDelaySeconds -DefaultValue $(if ($InjectPendingQueueFlood) { 80.0 } else { 0.0 }))
$PendingQueueFloodDrainDelaySeconds = [double](Resolve-Setting -CurrentValue $PendingQueueFloodDrainDelaySeconds -DefaultValue $(if ($InjectPendingQueueFlood) { 20.0 } else { 0.0 }))
$EmulatorMinimizeStartDelaySeconds = [double](Resolve-Setting -CurrentValue $EmulatorMinimizeStartDelaySeconds -DefaultValue $(if ($InjectEmulatorMinimizeOnce) { 150.0 } else { 0.0 }))
$EmulatorMinimizeDurationSeconds = [double](Resolve-Setting -CurrentValue $EmulatorMinimizeDurationSeconds -DefaultValue $(if ($InjectEmulatorMinimizeOnce) { 8.0 } else { 0.0 }))
$ForceEmulatorForegroundOnStart = [bool](Resolve-Setting -CurrentValue $ForceEmulatorForegroundOnStart -DefaultValue $(if ($presetConfig.ContainsKey('ForceEmulatorForegroundOnStart')) { $presetConfig.ForceEmulatorForegroundOnStart } else { $false }))
$MaximizeEmulatorOnStart = [bool](Resolve-Setting -CurrentValue $MaximizeEmulatorOnStart -DefaultValue $(if ($presetConfig.ContainsKey('MaximizeEmulatorOnStart')) { $presetConfig.MaximizeEmulatorOnStart } else { $false }))
$EmulatorForegroundStartDelaySeconds = [double](Resolve-Setting -CurrentValue $EmulatorForegroundStartDelaySeconds -DefaultValue $(if ($ForceEmulatorForegroundOnStart) { 6.0 } else { 0.0 }))
$ForegroundMismatchGraceSeconds = if ($PSBoundParameters.ContainsKey("ForegroundMismatchGraceSeconds")) { [double]$ForegroundMismatchGraceSeconds } else { [double](Resolve-Setting -CurrentValue $ForegroundMismatchGraceSeconds -DefaultValue $(if ($LiveMode) { 20.0 } else { 0.0 })) }
$ForegroundRecoveryIntervalSeconds = [double](Resolve-Setting -CurrentValue $ForegroundRecoveryIntervalSeconds -DefaultValue $(if ($ForceEmulatorForegroundOnStart) { 10.0 } else { 0.0 }))
$EnableOperatorDiagnostics = [bool](Resolve-Setting -CurrentValue $EnableOperatorDiagnostics -DefaultValue $false)
$OperatorDiagnosticProfile = [string](Resolve-Setting -CurrentValue $OperatorDiagnosticProfile -DefaultValue "default")
$OperatorDiagnosticStartDelaySeconds = [double](Resolve-Setting -CurrentValue $OperatorDiagnosticStartDelaySeconds -DefaultValue $(if ($EnableOperatorDiagnostics) { 45.0 } else { 0.0 }))
$OperatorDiagnosticIntervalSeconds = [double](Resolve-Setting -CurrentValue $OperatorDiagnosticIntervalSeconds -DefaultValue $(if ($EnableOperatorDiagnostics) { 75.0 } else { 0.0 }))
$EnableGameplayAutoExecution = [bool](Resolve-Setting -CurrentValue $EnableGameplayAutoExecution -DefaultValue $(if ($presetConfig.ContainsKey('EnableGameplayAutoExecution')) { $presetConfig.EnableGameplayAutoExecution } else { $false }))

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$launchCmdPath = Join-Path $repoRoot "launch_aurora2.cmd"
$statePath = Join-Path $repoRoot "aurora_control_panel_state.json"
$statePidPath = Join-Path $repoRoot "aurora_control_panel.pid"
$commandLogPath = Join-Path $repoRoot "aurora_command_execution_log.jsonl"
$chatLogPath = Join-Path $repoRoot "aurora_chat_history_log.jsonl"
$bridgeLogPath = Join-Path $repoRoot "aurora_external_bridge_log.jsonl"
$externalInboxPath = Join-Path $repoRoot "aurora_external_inbox.jsonl"
$screenshotsDir = Join-Path $repoRoot "screenshots"
$runRoot = Join-Path $repoRoot "soak_runs"
$runId = "aurora-soak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$artifactDir = Join-Path $runRoot $runId
$transcriptPath = Join-Path $artifactDir "monitor.log"
$reportPath = Join-Path $artifactDir "report.json"
$stdoutPath = Join-Path $artifactDir "runtime_stdout.log"
$stderrPath = Join-Path $artifactDir "runtime_stderr.log"
$launchWrapperPath = Join-Path $artifactDir "launch_wrapper.cmd"
$uiStressScriptPath = Join-Path $repoRoot "aurora_control_panel_stress_test.py"
$uiStressStdoutPath = Join-Path $artifactDir "ui_stress_stdout.log"
$uiStressStderrPath = Join-Path $artifactDir "ui_stress_stderr.log"
$uiStressReportPath = Join-Path $artifactDir "ui_stress_report.json"
$uiStressLogPath = Join-Path $artifactDir "ui_stress.log"
$staleStartupBackupDir = Join-Path $artifactDir "stale_startup_backup"
$screenshotFaultMarkerPath = Join-Path $artifactDir "screenshot_fault_once.marker"
$uiStressPython = "C:\Anaconda\envs\aurora\python.exe"
if (-not (Test-Path -LiteralPath $uiStressPython)) {
    $uiStressPython = "python"
}

$resolvedConfig = [ordered]@{
    preset = $Preset
    launch = [bool]$Launch
    runtime_pid = $RuntimePid
    duration_minutes = $DurationMinutes
    with_ui = [bool]$WithUi
    live_mode = [bool]$LiveMode
    load_live_init = [bool]$LoadLiveInit
    battle_profile = [bool]$BattleProfile
    game_profile = $GameProfile
    init_mode = $InitMode
    screenshot_interval_seconds = $ScreenshotIntervalSeconds
    review_turn_interval = $ReviewTurnInterval
    critique_turn_interval = $CritiqueTurnInterval
    review_thinking = $ReviewThinking
    critique_thinking = $CritiqueThinking
    turn_scheduler_profile = $TurnSchedulerProfile
    startup_smoke_enabled = [bool]$resolvedSmoke
    smoke_profile = $SmokeProfile
    smoke_max_cycles = $SmokeMaxCycles
    smoke_exit_after_seconds = $SmokeExitAfterSeconds
    poll_seconds = $PollSeconds
    startup_grace_seconds = $StartupGraceSeconds
    state_stale_seconds = $StateStaleSeconds
    screenshot_stale_seconds = $ScreenshotStaleSeconds
    gameplay_obstruction_grace_seconds = $GameplayObstructionGraceSeconds
    queue_drain_grace_seconds = $QueueDrainGraceSeconds
    pending_queue_limit = $PendingQueueLimit
    child_process_change_limit = $ChildProcessChangeLimit
    max_combined_log_growth_mb_per_hour = $MaxCombinedLogGrowthMbPerHour
    ui_stress_enabled = [bool]$EnableUiStress
    ui_stress_start_delay_seconds = $UiStressStartDelaySeconds
    ui_stress_state_fresh_seconds = $UiStressStateFreshSeconds
    ui_stress_timeout_seconds = $UiStressTimeoutSeconds
    inject_stale_startup_artifacts = [bool]$InjectStaleStartupArtifacts
    inject_screenshot_capture_failure_once = [bool]$InjectScreenshotCaptureFailureOnce
    inject_pending_queue_flood = [bool]$InjectPendingQueueFlood
    pending_queue_flood_count = $PendingQueueFloodCount
    pending_queue_flood_start_delay_seconds = $PendingQueueFloodStartDelaySeconds
    pending_queue_flood_drain_delay_seconds = $PendingQueueFloodDrainDelaySeconds
    inject_emulator_minimize_once = [bool]$InjectEmulatorMinimizeOnce
    emulator_minimize_start_delay_seconds = $EmulatorMinimizeStartDelaySeconds
    emulator_minimize_duration_seconds = $EmulatorMinimizeDurationSeconds
    force_emulator_foreground_on_start = [bool]$ForceEmulatorForegroundOnStart
    maximize_emulator_on_start = [bool]$MaximizeEmulatorOnStart
    toggle_emulator_fullscreen_on_start = [bool]$ToggleEmulatorFullscreenOnStart
    emulator_foreground_start_delay_seconds = $EmulatorForegroundStartDelaySeconds
    foreground_mismatch_grace_seconds = $ForegroundMismatchGraceSeconds
    foreground_recovery_interval_seconds = $ForegroundRecoveryIntervalSeconds
    enable_operator_diagnostics = [bool]$EnableOperatorDiagnostics
    operator_diagnostic_profile = $OperatorDiagnosticProfile
    operator_diagnostic_start_delay_seconds = $OperatorDiagnosticStartDelaySeconds
    operator_diagnostic_interval_seconds = $OperatorDiagnosticIntervalSeconds
    enable_gameplay_auto_execution = [bool]$EnableGameplayAutoExecution
    stop_on_timeout = [bool]$StopOnTimeout
    repo_root = $repoRoot
}

if ($ValidateOnly) {
    $resolvedConfig | ConvertTo-Json -Depth 10
    exit 0
}

New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

$report = [ordered]@{
    run_id = $runId
    preset = $Preset
    started_at = (Get-Date).ToString("o")
    repo_root = $repoRoot
    verdict = "running"
    failures = @()
    warnings = @()
    config = $resolvedConfig
    artifacts = [ordered]@{
        monitor_log = $transcriptPath
        report = $reportPath
        runtime_stdout = $stdoutPath
        runtime_stderr = $stderrPath
        launch_wrapper = $launchWrapperPath
        ui_stress_stdout = $uiStressStdoutPath
        ui_stress_stderr = $uiStressStderrPath
        ui_stress_report = $uiStressReportPath
        ui_stress_log = $uiStressLogPath
        stale_startup_backup = $staleStartupBackupDir
        screenshot_fault_marker = $screenshotFaultMarkerPath
    }
    samples = @()
    metrics = [ordered]@{
        runtime_pid = 0
        control_panel_pid = 0
        runtime_child_pid_changes = 0
        max_pending_commands = 0
        max_combined_log_growth_mb_per_hour = 0.0
        observed_game_profile = ""
        observed_game_profile_source = ""
        observed_scheduler_profile = ""
    }
    ui_stress = [ordered]@{
        enabled = [bool]$EnableUiStress
        status = $(if ($EnableUiStress) { "pending" } else { "disabled" })
        pid = 0
        started_at = ""
        ended_at = ""
        exit_code = $null
        report = $null
    }
}

function Initialize-StaleStartupArtifacts {
    New-Item -ItemType Directory -Path $staleStartupBackupDir -Force | Out-Null

    $targetFiles = @(
        $statePath,
        $commandLogPath,
        $chatLogPath,
        $bridgeLogPath
    )

    foreach ($path in $targetFiles) {
        if (Test-Path -LiteralPath $path) {
            Copy-Item -LiteralPath $path -Destination (Join-Path $staleStartupBackupDir ([System.IO.Path]::GetFileName($path))) -Force
        }
    }

    $staleTimestamp = "2000-01-01 00:00:00"
    $staleSnapshot = [ordered]@{
        timestamp = $staleTimestamp
        session_id = "stale-startup-fixture"
        runtime_summary = "stale startup fixture present before runtime boot"
        auth_summary = "stale startup fixture"
        last_screenshot_path = ""
        last_screenshot_timestamp = $staleTimestamp
        latest_feedback = @("stale startup fixture present before runtime boot")
        pending_commands = @(
            [ordered]@{
                command = "SHOW_RUNTIME()"
                risk = "medium"
                category = "runtime"
                reason = "stale startup fixture"
                support_count = 1
                repeat_count = 1
                turns_until_due = 99
                execute_by_inference = 99
                operating_context = "unknown"
                queue_mode = "normal"
                priority_score = 0
                importance_score = 0
                queue_status = "queued"
            }
        )
        image_memory = @()
        paths = [ordered]@{
            screenshots_dir = $screenshotsDir
            command_log = $commandLogPath
            chat_log = $chatLogPath
            external_inbox = $externalInboxPath
            state_file = $statePath
            model_catalog = (Join-Path $repoRoot "aurora_model_catalog.json")
        }
    }
    $staleSnapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding UTF8

    $staleRecords = @(
        @{ path = $commandLogPath; event = "stale_startup_fixture"; extra = @{ source = "fault_injection"; command = "SHOW_RUNTIME()" } },
        @{ path = $chatLogPath; event = "stale_startup_fixture"; extra = @{ role = "system"; content_summary = "stale startup fixture" } },
        @{ path = $bridgeLogPath; event = "stale_startup_fixture"; extra = @{ source = "fault_injection"; message_id = "stale-fixture-0001" } }
    )
    foreach ($recordSpec in $staleRecords) {
        $payload = [ordered]@{
            timestamp = $staleTimestamp
            session_id = "stale-startup-fixture"
            event = $recordSpec.event
        }
        foreach ($entry in $recordSpec.extra.GetEnumerator()) {
            $payload[$entry.Key] = $entry.Value
        }
        Set-Content -LiteralPath $recordSpec.path -Value (($payload | ConvertTo-Json -Compress) + [Environment]::NewLine) -Encoding UTF8
    }

    $staleWriteTime = [datetime]"2000-01-01T00:00:00Z"
    foreach ($path in $targetFiles) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path
            $item.LastWriteTimeUtc = $staleWriteTime
        }
    }

    Add-ReportLine -LogPath $transcriptPath -Message "Seeded stale startup snapshot/log artifacts and backed up originals."
}

Add-ReportLine -LogPath $transcriptPath -Message ("Resolved config: " + ($resolvedConfig | ConvertTo-Json -Compress -Depth 10))

if ($InjectStaleStartupArtifacts) {
    Initialize-StaleStartupArtifacts
}

$expectedScreenshotRestartRemaining = if ($InjectScreenshotCaptureFailureOnce) { 1 } else { 0 }
$pendingFloodCommands = @()
if ($InjectPendingQueueFlood) {
    $pendingFloodCommands = Get-PendingFloodCommands -Count $PendingQueueFloodCount
}
$operatorDiagnosticMessages = if ($EnableOperatorDiagnostics) { Get-OperatorDiagnosticMessages -Profile $OperatorDiagnosticProfile -GameProfile $GameProfile } else { @() }

$launchWrapperPid = 0
$auroraBaseline = New-Object 'System.Collections.Generic.HashSet[int]'
$observedAurora = New-Object 'System.Collections.Generic.HashSet[int]'
$orphanTargets = New-Object 'System.Collections.Generic.HashSet[int]'
$panelPidHistory = New-Object 'System.Collections.Generic.HashSet[int]'
$runtimeBaseline = New-Object 'System.Collections.Generic.HashSet[int]'
foreach ($row in Get-AuroraProcessRows) {
    [void]$auroraBaseline.Add([int]$row.ProcessId)
}
foreach ($row in Get-RuntimeProcessRows) {
    [void]$runtimeBaseline.Add([int]$row.ProcessId)
}

if ($Launch) {
    if (-not (Test-Path -LiteralPath $launchCmdPath)) {
        throw "Launcher not found at $launchCmdPath"
    }

    $argList = @($(if ($LiveMode) { "--live" } else { "--offline" }), $(if ($LoadLiveInit) { "--live-init" } else { "--no-live-init" }), "--no-chat-log-echo")
    if ($WithUi) {
        $argList += "--with-ui"
    } else {
        $argList += "--no-ui"
    }
    if ($BattleProfile) {
        $argList += "--battle-profile"
    }
    if ($InitMode) {
        $argList += @("--init-mode", $InitMode)
    }
    if ($GameProfile) {
        $argList += @("--game-profile", $GameProfile)
    }
    if ($TurnSchedulerProfile) {
        $argList += @("--turn-scheduler-profile", $TurnSchedulerProfile)
    }
    $argList += @("--screenshot-interval", $ScreenshotIntervalSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture))
    $argList += @("--review-turn-interval", $ReviewTurnInterval)
    $argList += @("--critique-turn-interval", $CritiqueTurnInterval)
    if ($ReviewThinking) {
        $argList += @("--review-thinking", $ReviewThinking)
    }
    if ($CritiqueThinking) {
        $argList += @("--critique-thinking", $CritiqueThinking)
    }
    if ($resolvedSmoke) {
        $argList += @("--smoke-test", "--smoke-profile", $SmokeProfile)
    } else {
        $argList += "--no-smoke-test"
    }

    $quotedArgs = ($argList | ForEach-Object {
        $text = [string]$_
        if ($text.Contains(" ")) {
            '"' + $text + '"'
        } else {
            $text
        }
    }) -join " "

    $wrapperLines = @(
        "@echo off",
        "setlocal",
        ('cd /d "{0}"' -f $repoRoot),
        ('set "AURORA_SMOKE_TEST={0}"' -f $(if ($resolvedSmoke) { "1" } else { "0" })),
        ('set "AURORA_SMOKE_TEST_PROFILE={0}"' -f $SmokeProfile),
        ('set "AURORA_SMOKE_TEST_MAX_CYCLES={0}"' -f $SmokeMaxCycles),
        ('set "AURORA_SMOKE_TEST_EXIT_AFTER={0}"' -f $SmokeExitAfterSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture)),
        'set "AURORA_SMOKE_TEST_FORCE_EXIT=0"',
        'set "AURORA_ENABLE_TEXT_INPUT_PROCESS=0"',
        ('set "AURORA_GAME_PROFILE={0}"' -f $GameProfile),
        ('set "AURORA_TURN_SCHEDULER_PROFILE={0}"' -f $TurnSchedulerProfile),
        ('set "AURORA_FAULT_SCREENSHOT_FAIL_ONCE={0}"' -f $(if ($InjectScreenshotCaptureFailureOnce) { "1" } else { "0" })),
        ('set "AURORA_FAULT_SCREENSHOT_FAIL_AFTER_FRAMES={0}"' -f $(if ($InjectScreenshotCaptureFailureOnce) { "5" } else { "999999" })),
        ('set "AURORA_FAULT_SCREENSHOT_FAIL_MARKER={0}"' -f $screenshotFaultMarkerPath),
        ('call "{0}" {1} 1>>"{2}" 2>>"{3}"' -f $launchCmdPath, $quotedArgs, $stdoutPath, $stderrPath),
        "endlocal"
    )
    Set-Content -LiteralPath $launchWrapperPath -Value $wrapperLines -Encoding ASCII

    $launchProcess = Start-Process -FilePath $launchWrapperPath -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru
    $launchWrapperPid = $launchProcess.Id
    Add-ReportLine -LogPath $transcriptPath -Message "Launch wrapper started as PID $launchWrapperPid"
    Add-ReportLine -LogPath $transcriptPath -Message "Launch args: $quotedArgs"

    $RuntimePid = Wait-ForNewRuntimePid -BaselineIds $runtimeBaseline -TimeoutSeconds 20
    if ($RuntimePid -le 0) {
        throw "Unable to find a newly launched aurora2.py process."
    }
} elseif ($RuntimePid -le 0) {
    $runningRows = Get-RuntimeProcessRows | Sort-Object ProcessId -Descending
    if ($runningRows.Count -eq 1) {
        $RuntimePid = [int]$runningRows[0].ProcessId
    } elseif ($runningRows.Count -gt 1) {
        throw "Multiple Aurora runtime processes are active. Rerun with -RuntimePid <pid>."
    } else {
        throw "No Aurora runtime process found. Start Aurora first or rerun with -Launch."
    }
}

$report.metrics.runtime_pid = $RuntimePid
[void]$observedAurora.Add($RuntimePid)
[void]$orphanTargets.Add($RuntimePid)
Add-ReportLine -LogPath $transcriptPath -Message "Monitoring runtime PID $RuntimePid"

$timeoutAt = (Get-Date).AddMinutes($DurationMinutes)
$stateProgressAt = $null
$stateStaleStart = $null
$screenshotProgressAt = $null
$screenshotStaleStart = $null
$gameplayObstructedSince = $null
$queuePressureStart = $null
$panelMissingSince = $null
$currentScreenshotKey = ""
$currentStateMtime = ""
$currentChildPids = @()
$lastPendingCount = 0
$stdoutOffset = 0L
$stderrOffset = 0L
$combinedLogBaselineBytes = 0L
$combinedLogBaselineTime = Get-Date
$latestSample = $null
$monitorStartedAt = Get-Date
$pendingFloodInjected = $false
$pendingFloodCleared = $false
$pendingFloodInjectedAt = $null
$emulatorMinimized = $false
$emulatorRestored = $false
$emulatorMinimizedAt = $null
$emulatorForegroundPrepared = $false
$lastForegroundRecoveryAt = $null
$lastMenuDismissAt = $null
$foregroundMismatchSince = $null
$emulatorFullscreenRecoveryPending = [bool]$ToggleEmulatorFullscreenOnStart
$operatorDiagnosticIndex = 0
$nextOperatorDiagnosticAt = $null
$gameplayAutoExecutionInjected = $false
if ($EnableOperatorDiagnostics) {
    $nextOperatorDiagnosticAt = $OperatorDiagnosticStartDelaySeconds
}

foreach ($path in @($commandLogPath, $chatLogPath, $bridgeLogPath)) {
    if (Test-Path -LiteralPath $path) {
        $combinedLogBaselineBytes += (Get-Item -LiteralPath $path).Length
    }
}

function Add-Failure {
    param([string]$Message)

    if ($report.failures -notcontains $Message) {
        $report.failures += $Message
        Add-ReportLine -LogPath $transcriptPath -Message "FAIL: $Message"
    }
}

function Add-Warning {
    param([string]$Message)

    if ($report.warnings -notcontains $Message) {
        $report.warnings += $Message
        Add-ReportLine -LogPath $transcriptPath -Message "WARN: $Message"
    }
}

function Invoke-UiStressPhase {
    $report.ui_stress.status = "waiting"

    if (-not (Test-Path -LiteralPath $uiStressScriptPath)) {
        $report.ui_stress.status = "missing_script"
        $report.ui_stress.ended_at = (Get-Date).ToString("o")
        Add-Failure "UI stress script is missing: aurora_control_panel_stress_test.py"
        return
    }

    $readyDeadline = (Get-Date).AddSeconds([Math]::Max(10.0, $UiStressStartDelaySeconds + $UiStressStateFreshSeconds))
    $uiReady = $false
    while ((Get-Date) -lt $readyDeadline) {
        $nowReady = Get-Date
        $stateItemReady = if (Test-Path -LiteralPath $statePath) { Get-Item -LiteralPath $statePath } else { $null }
        $panelPidReady = if ($WithUi) { Resolve-PanelPid -PidFilePath $statePidPath } else { 0 }
        $panelAliveReady = if ($WithUi) { Test-PidAlive -TargetPid $panelPidReady } else { $false }
        $stateAgeReady = if ($stateItemReady) { ($nowReady.ToUniversalTime() - $stateItemReady.LastWriteTimeUtc).TotalSeconds } else { [double]::PositiveInfinity }
        $delayReady = ($nowReady - $monitorStartedAt).TotalSeconds -ge $UiStressStartDelaySeconds
        $uiReady = $stateItemReady -and $stateAgeReady -le $UiStressStateFreshSeconds -and ((-not $WithUi) -or $panelAliveReady)
        if ($delayReady -and $uiReady) {
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $uiReady) {
        $report.ui_stress.status = "not_ready"
        $report.ui_stress.ended_at = (Get-Date).ToString("o")
        Add-Failure "UI stress phase could not start because the runtime/UI never became ready enough."
        return
    }

    $report.ui_stress.status = "running"
    $report.ui_stress.started_at = (Get-Date).ToString("o")
    Add-ReportLine -LogPath $transcriptPath -Message "Starting UI stress phase."
    & $uiStressPython $uiStressScriptPath --artifact-dir $artifactDir --run-id ("{0}-ui-stress" -f $runId) --state-fresh-seconds $UiStressStateFreshSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture) 1>> $uiStressStdoutPath 2>> $uiStressStderrPath
    $uiStressExitCode = $LASTEXITCODE
    $report.ui_stress.ended_at = (Get-Date).ToString("o")
    $report.ui_stress.exit_code = $uiStressExitCode

    $uiStressReport = Wait-ForJsonFile -Path $uiStressReportPath -TimeoutSeconds 8.0
    if ($uiStressReport) {
        $report.ui_stress.report = $uiStressReport
    }

    if ($uiStressReport -and $uiStressReport.verdict -eq "pass") {
        $report.ui_stress.status = "pass"
        Add-ReportLine -LogPath $transcriptPath -Message "UI stress phase passed."
    } elseif ($uiStressReport -and $uiStressReport.verdict) {
        $report.ui_stress.status = [string]$uiStressReport.verdict
        $uiStressFailureText = ""
        if ($uiStressReport.failures) {
            $uiStressFailureText = ": " + ((@($uiStressReport.failures) -join " | "))
        }
        Add-Failure ("UI stress phase reported verdict '{0}'{1}" -f $uiStressReport.verdict, $uiStressFailureText)
    } elseif ($uiStressExitCode -eq 0) {
        $report.ui_stress.status = "pass"
        Add-ReportLine -LogPath $transcriptPath -Message "UI stress phase passed."
    } else {
        $report.ui_stress.status = "fail"
        Add-Failure ("UI stress phase failed with exit code {0}." -f $uiStressExitCode)
    }
}

if ($EnableUiStress) {
    Invoke-UiStressPhase
}

while ($true) {
    $now = Get-Date
    $runtimeAlive = Test-PidAlive -TargetPid $RuntimePid
    $runtimeAgeSeconds = ($now - $monitorStartedAt).TotalSeconds
    $panelPid = if ($WithUi) { Resolve-PanelPid -PidFilePath $statePidPath } else { 0 }
    $panelAlive = if ($WithUi) { Test-PidAlive -TargetPid $panelPid } else { $false }
    $report.metrics.control_panel_pid = $panelPid
    if ($panelPid -gt 0) {
        [void]$observedAurora.Add($panelPid)
        [void]$panelPidHistory.Add($panelPid)
        [void]$orphanTargets.Add($panelPid)
    }

    if ($WithUi) {
        if ($panelAlive) {
            $panelMissingSince = $null
        } elseif (-not $panelMissingSince) {
            $panelMissingSince = $now
        } elseif (($now - $panelMissingSince).TotalSeconds -ge 20) {
            Add-Failure "Control panel is not alive while the soak expects UI mode."
        }
    }

    if ($runtimeAlive -and $InjectPendingQueueFlood -and -not $pendingFloodInjected -and $runtimeAgeSeconds -ge $PendingQueueFloodStartDelaySeconds) {
        foreach ($floodCommand in $pendingFloodCommands) {
            [void](Write-ExternalInboxRecord -InboxPath $externalInboxPath -Text $floodCommand -LogPath $transcriptPath -Source "pending_queue_flood" -Subject "pending queue flood" -Raw $true)
        }
        $pendingFloodInjected = $true
        $pendingFloodInjectedAt = $now
        Add-ReportLine -LogPath $transcriptPath -Message ("Injected pending queue flood with {0} QUEUE_PENDING command(s)." -f $pendingFloodCommands.Count)
    }

    if ($runtimeAlive -and $pendingFloodInjected -and -not $pendingFloodCleared -and $pendingFloodInjectedAt -and (($now - $pendingFloodInjectedAt).TotalSeconds -ge $PendingQueueFloodDrainDelaySeconds)) {
        [void](Write-ExternalInboxRecord -InboxPath $externalInboxPath -Text "CLEAR_PENDING(all)" -LogPath $transcriptPath -Source "pending_queue_flood" -Subject "pending queue flood drain" -Raw $true)
        $pendingFloodCleared = $true
        Add-ReportLine -LogPath $transcriptPath -Message "Queued CLEAR_PENDING(all) after pending queue flood."
    }

    if ($runtimeAlive -and $InjectEmulatorMinimizeOnce -and -not $emulatorMinimized -and $runtimeAgeSeconds -ge $EmulatorMinimizeStartDelaySeconds) {
        $minimizeResult = Invoke-EmulatorMinimize -WindowHint "VBA-RR" -LogPath $transcriptPath
        if ($minimizeResult.ok) {
            $emulatorMinimized = $true
            $emulatorMinimizedAt = $now
        } else {
            Add-Failure ("Emulator minimize injection failed: {0}" -f $minimizeResult.reason)
            $emulatorMinimized = $true
            $emulatorRestored = $true
        }
    }

    if ($runtimeAlive -and $emulatorMinimized -and -not $emulatorRestored -and $emulatorMinimizedAt -and (($now - $emulatorMinimizedAt).TotalSeconds -ge $EmulatorMinimizeDurationSeconds)) {
        $restoreResult = Invoke-EmulatorRestore -WindowHint "VBA-RR" -LogPath $transcriptPath
        if (-not $restoreResult.ok) {
            Add-Failure ("Emulator restore injection failed: {0}" -f $restoreResult.reason)
        }
        $emulatorRestored = $true
    }

    if ($runtimeAlive -and $EnableOperatorDiagnostics -and $nextOperatorDiagnosticAt -ne $null -and $runtimeAgeSeconds -ge $nextOperatorDiagnosticAt) {
        $message = $operatorDiagnosticMessages[$operatorDiagnosticIndex % $operatorDiagnosticMessages.Count]
        $messageText = [string]$message.text
        $messageAuthor = if ($message.author) { [string]$message.author } else { "user" }
        $messageSource = if ($message.source) { [string]$message.source } else { "tester_diagnostic" }
        $messageSubject = if ($message.subject) { [string]$message.subject } else { "tester diagnostic" }
        [void](Write-ExternalInboxRecord -InboxPath $externalInboxPath -Text $messageText -LogPath $transcriptPath -Source $messageSource -Author $messageAuthor -Subject $messageSubject -Raw $false)
        Add-ReportLine -LogPath $transcriptPath -Message ("Queued operator diagnostic message #{0} [{1}/{2}]: {3}" -f ($operatorDiagnosticIndex + 1), $messageAuthor, $messageSource, $messageText)
        $operatorDiagnosticIndex += 1
        $nextOperatorDiagnosticAt += $OperatorDiagnosticIntervalSeconds
    }

    if ($runtimeAlive -and $EnableGameplayAutoExecution -and -not $gameplayAutoExecutionInjected -and $runtimeAgeSeconds -ge 20.0) {
        [void](Write-ExternalInboxRecord -InboxPath $externalInboxPath -Text "SET_EXECUTION_MODE(auto)" -LogPath $transcriptPath -Source "gameplay_auto_mode" -Subject "gameplay auto mode" -Raw $true)
        [void](Write-ExternalInboxRecord -InboxPath $externalInboxPath -Text "SET_ACTION_MODE(gb)" -LogPath $transcriptPath -Source "gameplay_auto_mode" -Subject "gameplay auto mode" -Raw $true)
        [void](Write-ExternalInboxRecord -InboxPath $externalInboxPath -Text "APPROVE_PENDING(all)" -LogPath $transcriptPath -Source "gameplay_auto_mode" -Subject "gameplay auto mode" -Raw $true)
        $gameplayAutoExecutionInjected = $true
        Add-ReportLine -LogPath $transcriptPath -Message "Injected bounded gameplay auto-execution mode (SET_EXECUTION_MODE(auto), SET_ACTION_MODE(gb), APPROVE_PENDING(all))."
    }

    if ($runtimeAlive -and $ForceEmulatorForegroundOnStart -and -not $emulatorForegroundPrepared -and $runtimeAgeSeconds -ge $EmulatorForegroundStartDelaySeconds) {
        $foregroundPrep = Invoke-EmulatorForegroundSetup -WindowHint "VBA-RR" -Maximize:$MaximizeEmulatorOnStart -ToggleFullscreen:$ToggleEmulatorFullscreenOnStart -LogPath $transcriptPath
        if ($foregroundPrep.ok) {
            $emulatorForegroundPrepared = $true
        } else {
            Add-Failure ("Emulator foreground setup failed: {0}" -f $foregroundPrep.reason)
            $emulatorForegroundPrepared = $true
        }
    }

    $stateItem = if (Test-Path -LiteralPath $statePath) { Get-Item -LiteralPath $statePath } else { $null }
    $stateObject = if ($stateItem) { Read-JsonFileRetry -Path $statePath } else { $null }

        if ($stateItem) {
            $stateMtimeText = $stateItem.LastWriteTimeUtc.ToString("o")
            if ($stateMtimeText -ne $currentStateMtime) {
                $currentStateMtime = $stateMtimeText
                $stateProgressAt = $now
                $stateStaleStart = $null
        } elseif ($runtimeAlive -and $runtimeAgeSeconds -ge $StartupGraceSeconds) {
            if (-not $stateStaleStart) {
                $stateStaleStart = $now
            } elseif (($now - $stateStaleStart).TotalSeconds -ge $StateStaleSeconds) {
                Add-Failure "aurora_control_panel_state.json stopped updating while the runtime was still alive."
            }
        }
    } elseif ($runtimeAlive -and $runtimeAgeSeconds -ge $StartupGraceSeconds) {
        Add-Failure "aurora_control_panel_state.json is missing while the runtime is alive."
    }

    $pendingCount = 0
    $screenshotPath = ""
    $screenshotSignature = $null
    $gameplayVisibility = ""
    $gameplayVisibilityReason = ""
    $gameplayForegroundWindow = ""
    $reportedGameProfile = ""
    $reportedGameProfileSource = ""
    $reportedSchedulerProfile = ""
    if ($stateObject) {
        $pendingRows = @($stateObject.pending_commands)
        $pendingCount = $pendingRows.Count
        if ($pendingCount -gt $report.metrics.max_pending_commands) {
            $report.metrics.max_pending_commands = $pendingCount
        }
        $screenshotPath = [string]$stateObject.last_screenshot_path
        $gameplayVisibility = [string]$stateObject.gameplay.visibility
        $gameplayVisibilityReason = [string]$stateObject.gameplay.visibility_reason
        $gameplayForegroundWindow = [string]$stateObject.gameplay.foreground_window
        $reportedGameProfile = [string]$stateObject.modes.game_profile
        $reportedGameProfileSource = [string]$stateObject.modes.game_profile_source
        $reportedSchedulerProfile = [string]$stateObject.scheduler.profile
        if ($reportedGameProfile) {
            $report.metrics.observed_game_profile = $reportedGameProfile
            $report.metrics.observed_game_profile_source = $reportedGameProfileSource
        }
        if ($reportedSchedulerProfile) {
            $report.metrics.observed_scheduler_profile = $reportedSchedulerProfile
        }
        if ($screenshotPath -and (Test-Path -LiteralPath $screenshotPath)) {
            $screenshotSignature = Get-FileSignature -Path $screenshotPath
        }
    }

    if ($runtimeAlive -and $stateObject -and $runtimeAgeSeconds -ge $StartupGraceSeconds -and $GameProfile) {
        if ([string]::IsNullOrWhiteSpace($reportedGameProfile)) {
            Add-Failure "State export did not report modes.game_profile after startup grace."
        } elseif ($reportedGameProfile.Trim().ToLowerInvariant() -ne $GameProfile.Trim().ToLowerInvariant()) {
            Add-Failure ("State export game profile mismatch. expected='{0}' observed='{1}' source='{2}'" -f $GameProfile, $reportedGameProfile, $reportedGameProfileSource)
        }
    }

    if ($runtimeAlive -and $stateObject -and $runtimeAgeSeconds -ge $StartupGraceSeconds -and $TurnSchedulerProfile) {
        if ([string]::IsNullOrWhiteSpace($reportedSchedulerProfile)) {
            Add-Failure "State export did not report scheduler.profile after startup grace."
        } elseif ($reportedSchedulerProfile.Trim().ToLowerInvariant() -ne $TurnSchedulerProfile.Trim().ToLowerInvariant()) {
            Add-Failure ("State export scheduler profile mismatch. expected='{0}' observed='{1}'" -f $TurnSchedulerProfile, $reportedSchedulerProfile)
        }
    }

    if ($screenshotSignature) {
        $screenshotKey = "$($screenshotSignature.path)|$($screenshotSignature.sha1)|$($screenshotSignature.mtime_utc)"
        if ($screenshotKey -ne $currentScreenshotKey) {
            $currentScreenshotKey = $screenshotKey
            $screenshotProgressAt = $now
            $screenshotStaleStart = $null
        } elseif ($runtimeAlive) {
            if (-not $screenshotStaleStart) {
                $screenshotStaleStart = $now
            } elseif (($now - $screenshotStaleStart).TotalSeconds -ge $ScreenshotStaleSeconds) {
                Add-Failure "Latest screenshot path/hash stopped changing for too long."
            }
        }
    } elseif ($runtimeAlive -and $stateObject -and $runtimeAgeSeconds -ge $StartupGraceSeconds) {
        Add-Failure "State export does not point at a readable latest screenshot."
    }

    if ($LiveMode -and $runtimeAlive -and $stateObject -and $runtimeAgeSeconds -ge $StartupGraceSeconds -and $GameplayObstructionGraceSeconds -gt 0) {
        if ($gameplayVisibility -eq "obstructed") {
            if (-not $gameplayObstructedSince) {
                $gameplayObstructedSince = $now
            } elseif (($now - $gameplayObstructedSince).TotalSeconds -ge $GameplayObstructionGraceSeconds) {
                Add-Failure ("Gameplay view remained obstructed for too long. reason='{0}' foreground='{1}'" -f $gameplayVisibilityReason, $gameplayForegroundWindow)
            }
        } else {
            $gameplayObstructedSince = $null
        }
    } else {
        $gameplayObstructedSince = $null
    }

    if ($LiveMode -and $runtimeAlive -and $stateObject -and $ForegroundMismatchGraceSeconds -gt 0) {
        $foregroundLooksWrong = $false
        if ($gameplayForegroundWindow -and $gameplayForegroundWindow -match 'Codex|Visual Studio Code|Code') {
            $foregroundLooksWrong = $true
        }
        $needsForegroundRecovery = ($gameplayVisibility -eq "obstructed" -or ($gameplayVisibility -eq "unknown" -and $foregroundLooksWrong))
        if ($ForceEmulatorForegroundOnStart -and $needsForegroundRecovery -and $ForegroundRecoveryIntervalSeconds -gt 0) {
            if ($ToggleEmulatorFullscreenOnStart -and -not $foregroundMismatchSince) {
                $emulatorFullscreenRecoveryPending = $true
            }
            $shouldRecoverNow = (-not $lastForegroundRecoveryAt) -or (($now - $lastForegroundRecoveryAt).TotalSeconds -ge $ForegroundRecoveryIntervalSeconds)
            if ($shouldRecoverNow) {
                $toggleFullscreenOnRecovery = [bool]$ToggleEmulatorFullscreenOnStart -and [bool]$emulatorFullscreenRecoveryPending
                $recoveryResult = Invoke-EmulatorForegroundSetup -WindowHint "VBA-RR" -Maximize:$MaximizeEmulatorOnStart -ToggleFullscreen:$toggleFullscreenOnRecovery -LogPath $transcriptPath
                $lastForegroundRecoveryAt = $now
                if ($toggleFullscreenOnRecovery) {
                    $emulatorFullscreenRecoveryPending = $false
                }
                if ($recoveryResult.ok) {
                    Add-ReportLine -LogPath $transcriptPath -Message "Re-applied emulator foreground recovery during gameplay soak."
                } else {
                    Add-Warning ("Foreground recovery attempt failed: {0}" -f $recoveryResult.reason)
                }
            }
        }
        $dropdownObstruction = ($gameplayVisibility -eq "obstructed" -and $gameplayVisibilityReason -match 'dropdown|menu')
        if ($dropdownObstruction) {
            $shouldDismissMenu = (-not $lastMenuDismissAt) -or (($now - $lastMenuDismissAt).TotalSeconds -ge 12.0)
            if ($shouldDismissMenu) {
                $dismissResult = Invoke-EmulatorDismissMenu -WindowHint "VBA-RR" -LogPath $transcriptPath
                $lastMenuDismissAt = $now
                if (-not $dismissResult.ok) {
                    Add-Warning ("Emulator menu-dismiss attempt failed: {0}" -f $dismissResult.reason)
                }
            }
        }
        if ($gameplayVisibility -eq "obstructed" -or ($gameplayVisibility -eq "unknown" -and $foregroundLooksWrong)) {
            if (-not $foregroundMismatchSince) {
                $foregroundMismatchSince = $now
            } elseif (($now - $foregroundMismatchSince).TotalSeconds -ge $ForegroundMismatchGraceSeconds) {
                Add-Failure ("Gameplay soak stayed in the wrong foreground/window state too long. visibility='{0}' foreground='{1}' reason='{2}'" -f $gameplayVisibility, $gameplayForegroundWindow, $gameplayVisibilityReason)
            }
        } else {
            $foregroundMismatchSince = $null
            if ($ToggleEmulatorFullscreenOnStart) {
                $emulatorFullscreenRecoveryPending = $true
            }
        }
    } else {
        $foregroundMismatchSince = $null
    }

    if ($pendingCount -gt $PendingQueueLimit) {
        if (-not $queuePressureStart) {
            $queuePressureStart = $now
        } elseif (($now - $queuePressureStart).TotalSeconds -ge $QueueDrainGraceSeconds) {
            Add-Failure "Pending command queue grew past the limit and did not drain."
        }
    } else {
        $queuePressureStart = $null
    }
    if ($pendingCount -lt $lastPendingCount) {
        $queuePressureStart = $null
    }
    $lastPendingCount = $pendingCount

    $childRows = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $RuntimePid } | Select-Object -ExpandProperty ProcessId
    $childRows = @($childRows | Sort-Object)
    if ($currentChildPids.Count -gt 0) {
        $before = ($currentChildPids -join ",")
        $after = ($childRows -join ",")
        if ($before -ne $after) {
            $report.metrics.runtime_child_pid_changes += 1
            Add-ReportLine -LogPath $transcriptPath -Message "Child process set changed: [$before] -> [$after]"
            if ($report.metrics.runtime_child_pid_changes -gt $ChildProcessChangeLimit) {
                Add-Failure "Runtime child process restarts spiked above the configured limit."
            }
        }
    }
    $currentChildPids = $childRows

    $stdoutTraceResult = Read-NewTracebackMatches -Path $stdoutPath -Offset $stdoutOffset
    $stderrTraceResult = Read-NewTracebackMatches -Path $stderrPath -Offset $stderrOffset
    foreach ($traceResult in @($stdoutTraceResult, $stderrTraceResult)) {
        if ($traceResult -and $traceResult.matches.Count -gt 0) {
            foreach ($match in $traceResult.matches) {
                if ($InjectScreenshotCaptureFailureOnce -and ($expectedScreenshotRestartRemaining -gt 0) -and $match -match "Process 'screenshot' terminated unexpectedly\. Restarting") {
                    $expectedScreenshotRestartRemaining -= 1
                    Add-Warning "Observed expected injected screenshot worker restart."
                    continue
                }
                Add-Failure "Unhandled traceback or worker exception signal detected: $match"
            }
        }
    }
    $stdoutOffset = $stdoutTraceResult.offset
    $stderrOffset = $stderrTraceResult.offset

    $combinedLogBytes = 0L
    foreach ($path in @($commandLogPath, $chatLogPath, $bridgeLogPath)) {
        if (Test-Path -LiteralPath $path) {
            $combinedLogBytes += (Get-Item -LiteralPath $path).Length
        }
    }
    $elapsedHours = [Math]::Max(0.001, ($now - $combinedLogBaselineTime).TotalHours)
    $growthMbPerHour = (($combinedLogBytes - $combinedLogBaselineBytes) / 1MB) / $elapsedHours
    if ($growthMbPerHour -gt $report.metrics.max_combined_log_growth_mb_per_hour) {
        $report.metrics.max_combined_log_growth_mb_per_hour = [Math]::Round($growthMbPerHour, 3)
    }
    if ($growthMbPerHour -gt $MaxCombinedLogGrowthMbPerHour) {
        Add-Warning ("Combined command/chat/bridge logs are growing at {0:N2} MB/hour." -f $growthMbPerHour)
    }

    $latestSample = [ordered]@{
        timestamp = $now.ToString("o")
        runtime_alive = $runtimeAlive
        control_panel_alive = $panelAlive
        pending_commands = $pendingCount
        state_mtime_utc = $currentStateMtime
        screenshot_path = $screenshotPath
        screenshot_sha1 = if ($screenshotSignature) { $screenshotSignature.sha1 } else { "" }
        gameplay_visibility = $gameplayVisibility
        gameplay_visibility_reason = $gameplayVisibilityReason
        gameplay_foreground_window = $gameplayForegroundWindow
        game_profile = $reportedGameProfile
        game_profile_source = $reportedGameProfileSource
        scheduler_profile = $reportedSchedulerProfile
        child_pids = $currentChildPids
        log_growth_mb_per_hour = [Math]::Round($growthMbPerHour, 3)
    }
    $report.samples = @($report.samples) + @($latestSample)

    $heartbeatScreenshotKey = "-"
    if ($screenshotSignature -and $screenshotSignature.sha1) {
        $heartbeatScreenshotKey = [string]$screenshotSignature.sha1
        if ($heartbeatScreenshotKey.Length -gt 8) {
            $heartbeatScreenshotKey = $heartbeatScreenshotKey.Substring(0, 8)
        }
    }

    Add-ReportLine -LogPath $transcriptPath -Message (
        "Heartbeat runtime_alive={0} panel_alive={1} pending={2} screenshot={3} gameplay={4} child_changes={5}" -f
        $runtimeAlive,
        $panelAlive,
        $pendingCount,
        $heartbeatScreenshotKey,
        ($(if ($gameplayVisibility) { $gameplayVisibility } else { "-" })),
        $report.metrics.runtime_child_pid_changes
    )

    if (-not $runtimeAlive) {
        Add-ReportLine -LogPath $transcriptPath -Message "Runtime PID $RuntimePid has exited."
        break
    }

    if ($now -ge $timeoutAt) {
        if ($StopOnTimeout) {
            Add-Warning "Duration reached; requesting clean runtime shutdown."
            Request-CleanRuntimeShutdown -InboxPath $externalInboxPath -LogPath $transcriptPath
            $shutdownDeadline = (Get-Date).AddSeconds(30)
            while ((Get-Date) -lt $shutdownDeadline) {
                if (-not (Test-PidAlive -TargetPid $RuntimePid)) {
                    break
                }
                Start-Sleep -Seconds 2
            }
            if (Test-PidAlive -TargetPid $RuntimePid) {
                Add-Warning "Runtime did not exit after clean shutdown request; forcing process stop."
                Stop-Process -Id $RuntimePid -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 4
            }
        } else {
            Add-Warning "Duration reached while the runtime is still alive. Leaving it running."
        }
        break
    }

    Start-Sleep -Seconds $PollSeconds
}

Start-Sleep -Seconds 3
$postCheckNow = Get-Date
if ($EnableUiStress -and -not $report.ui_stress.report -and (Test-Path -LiteralPath $uiStressReportPath)) {
    $report.ui_stress.report = Wait-ForJsonFile -Path $uiStressReportPath -TimeoutSeconds 3.0
}

$postRuntimeAlive = Test-PidAlive -TargetPid $RuntimePid
if ($InjectScreenshotCaptureFailureOnce -and -not (Test-Path -LiteralPath $screenshotFaultMarkerPath)) {
    Add-Failure "Injected screenshot capture fault marker was never written; the one-shot screenshot failure did not trigger."
}
if ($InjectPendingQueueFlood -and -not $pendingFloodInjected) {
    Add-Failure "Pending queue flood injection never triggered."
}
if ($InjectPendingQueueFlood -and -not $pendingFloodCleared) {
    Add-Failure "Pending queue flood clear step never triggered."
}
if ($EnableGameplayAutoExecution -and -not $gameplayAutoExecutionInjected) {
    Add-Failure "Gameplay auto-execution mode was never injected."
}
if ($ForceEmulatorForegroundOnStart -and -not $emulatorForegroundPrepared) {
    Add-Failure "Emulator foreground preparation never triggered."
}
if ($InjectEmulatorMinimizeOnce -and -not $emulatorMinimized) {
    Add-Failure "Emulator minimize injection never triggered."
}
if ($InjectEmulatorMinimizeOnce -and -not $emulatorRestored) {
    Add-Failure "Emulator restore step never triggered."
}
if ($postRuntimeAlive -and -not $StopOnTimeout) {
    $report.verdict = "incomplete"
    Add-Warning "Run ended while the runtime was still alive; orphan check deferred."
} else {
    $remainingRows = Get-AuroraProcessRows
    $remainingTargets = @(
        $remainingRows | Where-Object {
            $pidValue = [int]$_.ProcessId
            $orphanTargets.Contains($pidValue) -or (-not $auroraBaseline.Contains($pidValue))
        }
    )
    $remainingText = @($remainingTargets | ForEach-Object { "PID=$($_.ProcessId) CMD=$($_.CommandLine)" })
    if ($remainingTargets.Count -gt 0) {
        Add-Failure ("Orphaned Aurora process(es) remained after exit: " + ($remainingText -join " | "))
    }
}

if ($Launch -and $resolvedSmoke -and -not $report.failures.Count -and -not $postRuntimeAlive) {
    $report.verdict = "pass"
} elseif ($report.failures.Count -gt 0) {
    $report.verdict = "fail"
} elseif ($report.verdict -ne "incomplete") {
    $report.verdict = "pass"
}

$report.ended_at = (Get-Date).ToString("o")

$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Add-ReportLine -LogPath $transcriptPath -Message ("Final verdict: " + $report.verdict)

switch ($report.verdict) {
    "pass" { exit 0 }
    "incomplete" { exit 2 }
    default { exit 1 }
}
