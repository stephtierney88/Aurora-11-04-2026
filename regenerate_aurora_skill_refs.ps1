param(
    [switch]$Force,
    [switch]$Check,
    [switch]$Watch,
    [switch]$SyncSkills,
    [string]$SkillRoot,
    [int]$PollSeconds = 2
)

$ErrorActionPreference = 'Stop'
$python = if ($env:AURORA_PYTHON) { $env:AURORA_PYTHON } elseif (Test-Path -LiteralPath 'C:\Anaconda\envs\aurora\python.exe') { 'C:\Anaconda\envs\aurora\python.exe' } else { 'python' }
$generatorScript = Join-Path $PSScriptRoot 'tools\generate_aurora_references.py'
if ($Check -and ($Watch -or $SyncSkills)) { throw '-Check cannot be combined with -Watch or -SyncSkills.' }
if ($PollSeconds -lt 1) { throw 'PollSeconds must be at least 1.' }

function Sync-InstalledSkillReferences {
    $exportSkillRoot = $SkillRoot
    if (-not $exportSkillRoot) {
        $exportCodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
        $exportSkillRoot = Join-Path $exportCodexRoot 'skills'
    }
    $layout = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'tools\aurora_maps\reference_layout.json') -Raw | ConvertFrom-Json
    $groups = @(
        @{Name='aurora2-command-catalog'; Files=@($layout.commands.PSObject.Properties.Value)},
        @{Name='aurora2-program-map-lite'; Files=@($layout.runtime.lite)},
        @{Name='aurora2-program-map-deep'; Files=@($layout.runtime.PSObject.Properties | Where-Object Name -NE 'lite' | ForEach-Object Value)},
        @{Name='aurora2-control-panel-map'; Files=@($layout.ui.PSObject.Properties.Value)}
    )
    foreach ($group in $groups) {
        $target = Join-Path (Join-Path $exportSkillRoot $group.Name) 'references'
        if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw "Installed skill references are missing: $target" }
    }
    foreach ($group in $groups) {
        $target = Join-Path (Join-Path $exportSkillRoot $group.Name) 'references'
        foreach ($relative in @($group.Files | Sort-Object -Unique)) {
            $source = Join-Path (Join-Path $PSScriptRoot 'aurora_reference_maps') $relative
            Copy-Item -LiteralPath $source -Destination (Join-Path $target ([IO.Path]::GetFileName($relative))) -Force
        }
    }
    Write-Host 'Installed skill references exported from the verified workspace.'
}

function Invoke-Regeneration {
    $generatorArgs = @('--root', $PSScriptRoot)
    if ($Check) { $generatorArgs += '--check' }
    elseif (-not $Force) { $generatorArgs += '--if-needed' }
    & $python $generatorScript @generatorArgs
    if ($LASTEXITCODE -ne 0) { throw "Aurora reference generation/check failed (exit $LASTEXITCODE); installed skills were not synced." }
    if ($SyncSkills) { Sync-InstalledSkillReferences }
}

function Get-ReferenceInputStamp {
    $inputs = @(
        Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.py' -File
        Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'tools') -Filter '*aurora*' -File
        Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'tools\aurora_maps') -File
        Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'docs\reference-packs') -File
        Get-Item -LiteralPath (Join-Path $PSScriptRoot 'docs\notes\aurora_current_status.md'), (Join-Path $PSScriptRoot 'docs\notes\aurora_runtime_roadmap.md'), $PSCommandPath
        Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'aurora_reference_maps\runtime'), (Join-Path $PSScriptRoot 'aurora_reference_maps\ui') -Filter '*.md' -File
    )
    return (($inputs | Sort-Object FullName | ForEach-Object { $_.FullName + ':' + $_.LastWriteTimeUtc.Ticks }) -join '|')
}

Invoke-Regeneration
if ($Watch) {
    $lastInputStamp = Get-ReferenceInputStamp
    Write-Host 'Watching Aurora reference inputs. Press Ctrl+C to stop.'
    while ($true) {
        Start-Sleep -Seconds $PollSeconds
        $inputStamp = Get-ReferenceInputStamp
        if ($inputStamp -ne $lastInputStamp) {
            Invoke-Regeneration
            $lastInputStamp = Get-ReferenceInputStamp
        }
    }
}
