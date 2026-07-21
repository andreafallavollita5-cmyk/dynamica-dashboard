param(
    [string]$TaskName = "Dynamica Retail - Aggiornamento dashboard",
    [string]$UserId = "MMM\andrea.fallavollita"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$batchPath = Join-Path $projectRoot "run_daily_update.bat"
if (-not (Test-Path -LiteralPath $batchPath)) {
    throw "Batch non trovato: $batchPath"
}

$credential = Get-Credential -UserName $UserId -Message "Credenziali Windows per l'automazione Dynamica"
if ($null -eq $credential) {
    throw "Registrazione annullata: credenziali non inserite."
}

$action = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\cmd.exe" `
    -Argument "/d /c `"$batchPath`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
$principal = New-ScheduledTaskPrincipal `
    -UserId $credential.UserName `
    -LogonType Password `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Aggiorna Google/Meta Ads, CRM, Google Sheet, export, archivio e latest GitHub."

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $task `
    -User $credential.UserName `
    -Password $credential.GetNetworkCredential().Password `
    -Force | Out-Null

Write-Host "Attività registrata: $TaskName"
Write-Host "Prossima esecuzione:" (Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime
