param(
    [string]$To = "user@example.com",
    [string]$Subject = "[CODEX] Codex task finished",
    [string]$Body = "Codex finished the requested task.`n`nReply to this email or send a new email with subject starting [CODEX] to send a message back into the local Aurora/Codex bridge.",
    [string]$Summary = "",
    [switch]$SkipDialog,
    [switch]$SkipEmail
)

$ErrorActionPreference = "Stop"

function Build-NotificationBody {
    param(
        [string]$ProvidedBody,
        [string]$ProvidedSummary
    )

    $bodyText = $ProvidedBody
    if ($ProvidedSummary -and $ProvidedSummary.Trim()) {
        $summaryText = $ProvidedSummary.Trim()
        $bodyText = @"
Codex finished.

Summary:
$summaryText

Reply to this email or send a new email with subject starting [CODEX] to send a message back into the local Aurora/Codex bridge.
"@
    }
    return $bodyText
}

function Get-OutlookState {
    $process = Get-Process OUTLOOK -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $process) {
        return @{
            available = $false
            reason = "outlook_not_running"
            title = ""
        }
    }

    $title = ""
    try {
        $title = $process.MainWindowTitle
    } catch {
        $title = ""
    }

    return @{
        available = $true
        reason = "outlook_running"
        title = $title
    }
}

function Encode-MailtoComponent {
    param(
        [string]$Value
    )

    return [System.Uri]::EscapeDataString($Value)
}

function Send-OutlookMailBounded {
    param(
        [string]$Recipient,
        [string]$MailSubject,
        [string]$MailBody,
        [int]$TimeoutSeconds = 15
    )

    $tempScript = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "codex-outlook-notify-$([guid]::NewGuid().ToString('N')).ps1")
    $scriptContent = @"
`$ErrorActionPreference = 'Stop'
`$outlook = New-Object -ComObject Outlook.Application
`$mail = `$outlook.CreateItem(0)
`$mail.To = '$($Recipient.Replace("'", "''"))'
`$mail.Subject = '$($MailSubject.Replace("'", "''"))'
`$mail.Body = '$($MailBody.Replace("'", "''"))'
`$mail.Send()
"@
    Set-Content -Path $tempScript -Value $scriptContent -Encoding ASCII

    try {
        $proc = Start-Process -FilePath powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $tempScript) -PassThru -WindowStyle Hidden
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            return @{
                ok = $false
                reason = "outlook_send_timeout"
            }
        }
        if ($proc.ExitCode -eq 0) {
            return @{
                ok = $true
                reason = "sent_via_outlook"
            }
        }
        return @{
            ok = $false
            reason = "outlook_send_failed"
            exit_code = $proc.ExitCode
        }
    } finally {
        Remove-Item $tempScript -Force -ErrorAction SilentlyContinue
    }
}

function Send-OutlookMailViaMailto {
    param(
        [string]$Recipient,
        [string]$MailSubject,
        [string]$MailBody
    )

    try {
        $pythonCandidates = @(
            "C:\Anaconda\envs\aurora\python.exe",
            "C:\Anaconda\python.exe",
            "python.exe"
        )
        $pythonExe = $pythonCandidates | Where-Object { $_ -eq "python.exe" -or (Test-Path $_) } | Select-Object -First 1
        if (-not $pythonExe) {
            return @{
                ok = $false
                reason = "python_not_available_for_ui_send"
            }
        }

        $helperPath = Join-Path $PSScriptRoot "send_outlook_mail_ui.py"
        if (-not (Test-Path $helperPath)) {
            return @{
                ok = $false
                reason = "ui_send_helper_missing"
            }
        }

        $raw = & $pythonExe $helperPath --to $Recipient --subject $MailSubject --body $MailBody 2>&1
        if ($LASTEXITCODE -ne 0) {
            return @{
                ok = $false
                reason = "mailto_sendkeys_failed"
                error = ($raw | Out-String).Trim()
            }
        }

        $parsed = $raw | Out-String | ConvertFrom-Json
        if ($parsed.ok) {
            return @{
                ok = $true
                reason = $parsed.reason
            }
        }

        return @{
            ok = $false
            reason = $parsed.reason
        }
    } catch {
        return @{
            ok = $false
            reason = "mailto_sendkeys_failed"
            error = $_.Exception.Message
        }
    }
}

function Show-PersistentDialog {
    param(
        [string]$DialogTitle,
        [string]$DialogBody
    )

    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($DialogBody, $DialogTitle, "OK", "Information") | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$Body = Build-NotificationBody -ProvidedBody $Body -ProvidedSummary $Summary
$status = [ordered]@{
    timestamp = $timestamp
    to = $To
    subject = $Subject
    email_attempted = $false
    email_sent = $false
    email_reason = ""
    dialog_shown = $false
}

if (-not $SkipEmail) {
    $outlookState = Get-OutlookState
    if ($outlookState.available) {
        $status.email_attempted = $true
        $sendResult = Send-OutlookMailBounded -Recipient $To -MailSubject $Subject -MailBody $Body
        if (-not $sendResult.ok) {
            $sendResult = Send-OutlookMailViaMailto -Recipient $To -MailSubject $Subject -MailBody $Body
        }
        $status.email_sent = [bool]$sendResult.ok
        $status.email_reason = $sendResult.reason
    } else {
        $status.email_reason = $outlookState.reason
    }
} else {
    $status.email_reason = "email_skipped_by_flag"
}

$statusJson = $status | ConvertTo-Json -Depth 4
$statusText = @(
    "timestamp=$($status.timestamp)"
    "to=$($status.to)"
    "subject=$($status.subject)"
    "email_attempted=$($status.email_attempted)"
    "email_sent=$($status.email_sent)"
    "email_reason=$($status.email_reason)"
) -join [Environment]::NewLine

$jsonPath = Join-Path $PSScriptRoot "codex_notify_last.json"
$textPath = Join-Path $PSScriptRoot "codex_notify_last.txt"
Set-Content -Path $jsonPath -Value $statusJson -Encoding UTF8
Set-Content -Path $textPath -Value $statusText -Encoding ASCII

if (-not $status.email_sent -and -not $SkipDialog) {
    $dialogBody = @"
Codex finished.

Subject: $Subject
Time: $timestamp

Email path was not available.
Reason: $($status.email_reason)

Status file:
$textPath
"@
    Show-PersistentDialog -DialogTitle "Codex Finished" -DialogBody $dialogBody
    $status.dialog_shown = $true
    $statusJson = $status | ConvertTo-Json -Depth 4
    Set-Content -Path $jsonPath -Value $statusJson -Encoding UTF8
}

Write-Output $statusJson
