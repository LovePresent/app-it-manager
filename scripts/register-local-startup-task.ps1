param(
    [string]$TaskName = "CQV IT Manager Local",
    [string]$Distro = "Ubuntu",
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$startScript = Join-Path $PSScriptRoot "start-local-wsl-docker.ps1"
if (-not (Test-Path $startScript)) {
    throw "Startup script does not exist: $startScript"
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powershellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -Distro `"$Distro`" -ProjectPath `"$ProjectPath`""

function Install-StartupFolderLauncher {
    $startupDir = [Environment]::GetFolderPath("Startup")
    if (-not $startupDir) {
        throw "Could not resolve the current user's Startup folder."
    }

    $launcherPath = Join-Path $startupDir "CQV IT Manager Local.vbs"
    $command = "$powershellPath $arguments"
    $escapedCommand = $command.Replace('"', '""')

    $content = @"
Set shell = CreateObject("WScript.Shell")
shell.Run "$escapedCommand", 0, False
"@

    Set-Content -Path $launcherPath -Value $content -Encoding ASCII
    return $launcherPath
}

function Start-LocalStackHidden {
    Start-Process `
        -FilePath $powershellPath `
        -ArgumentList $arguments `
        -WindowStyle Hidden
}

$action = New-ScheduledTaskAction `
    -Execute $powershellPath `
    -Argument $arguments `
    -WorkingDirectory $ProjectPath

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

$principal = New-ScheduledTaskPrincipal `
    -UserId $identity `
    -LogonType Interactive `
    -RunLevel Limited

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Start CQV IT Manager local WSL Docker stack at Windows logon." `
        -Force | Out-Null

    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 5

    $task = Get-ScheduledTask -TaskName $TaskName
    $info = Get-ScheduledTaskInfo -TaskName $TaskName

    [pscustomobject]@{
        Method = "ScheduledTask"
        TaskName = $task.TaskName
        State = $task.State
        LastRunTime = $info.LastRunTime
        LastTaskResult = $info.LastTaskResult
        StartupScript = $startScript
    }
}
catch {
    Write-Warning "Scheduled Task registration failed. Falling back to the current user's Startup folder. $($_.Exception.Message)"

    $launcherPath = Install-StartupFolderLauncher
    Start-LocalStackHidden

    [pscustomobject]@{
        Method = "StartupFolder"
        Launcher = $launcherPath
        StartupScript = $startScript
        StartedNow = $true
    }
}
