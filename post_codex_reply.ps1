param(
    [Parameter(Mandatory = $true)]
    [string]$Text,
    [string]$Subject = "[CODEX] operator reply",
    [string]$Source = "operator_manual"
)

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$inboxPath = Join-Path $scriptDirectory "aurora_external_inbox.jsonl"
$logPath = Join-Path $scriptDirectory "aurora_external_bridge_log.jsonl"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$messageId = "{0}-{1}" -f ([DateTimeOffset]::Now.ToUnixTimeMilliseconds()), (Get-Random -Minimum 100000 -Maximum 999999)

$record = [ordered]@{
    message_id = $messageId
    timestamp  = $timestamp
    author     = "user"
    source     = $Source
    subject    = $Subject
    text       = $Text.Trim()
    metadata   = [ordered]@{
        via = "post_codex_reply.ps1"
    }
}

$jsonLine = $record | ConvertTo-Json -Depth 5 -Compress
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::AppendAllText($inboxPath, $jsonLine + [Environment]::NewLine, $utf8NoBom)

$logRecord = [ordered]@{
    timestamp  = $timestamp
    event      = "message_appended"
    source     = $Source
    message_id = $messageId
    subject    = $Subject
}
$logLine = $logRecord | ConvertTo-Json -Depth 4 -Compress
[System.IO.File]::AppendAllText($logPath, $logLine + [Environment]::NewLine, $utf8NoBom)

Write-Output ($record | ConvertTo-Json -Depth 5)
