param(
    [string]$Distro = "Ubuntu",
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ComposeFile = "compose.local.yaml",
    [int]$WaitSeconds = 180,
    [switch]$NoKeepAlive
)

$ErrorActionPreference = "Stop"

$logDir = Join-Path $env:LOCALAPPDATA "CQV-IT-Manager\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "local-startup.log"

function Write-Log {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $logPath -Value $line
    Write-Host $line
}

function Invoke-WslBash {
    param([string]$Command)

    & wsl.exe -d $Distro -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed with exit code $LASTEXITCODE"
    }
}

function Convert-ToWslPath {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if ($fullPath -match "^([A-Za-z]):\\(.*)$") {
        $drive = $Matches[1].ToLowerInvariant()
        $pathPart = $Matches[2].Replace("\", "/")
        return "/mnt/$drive/$pathPart"
    }

    $converted = & wsl.exe -d $Distro -- wslpath -a $fullPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to convert path to WSL path: $fullPath"
    }

    return $converted.Trim()
}

function Start-WslKeepAlive {
    $pattern = "wsl.exe -d $Distro -- bash -lc"
    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -like "*$pattern*" -and
            $_.CommandLine -like "*while true; do sleep 60; done*"
        }

    if ($existing) {
        Write-Log "WSL keepalive is already running."
        return
    }

    $keepAliveScript = "wsl.exe -d $Distro -- bash -lc 'while true; do sleep 60; done'"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($keepAliveScript))

    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", $encoded) `
        -WindowStyle Hidden

    Write-Log "Started WSL keepalive process."
}

function Start-DockerInWsl {
    Write-Log "Starting Docker service inside WSL distro '$Distro'."

    & wsl.exe -d $Distro -u root -- sh -lc "service docker start >/dev/null 2>&1 || true"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start Docker service in WSL."
    }

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        & wsl.exe -d $Distro -- sh -lc "docker info >/dev/null 2>&1"
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Docker is ready in WSL."
            return
        }

        Start-Sleep -Seconds 2
    }

    throw "Docker did not become ready in WSL within 45 seconds."
}

function Wait-HttpOk {
    param(
        [string]$Name,
        [string]$Url
    )

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Log "$Name is available: $Url"
                return
            }
        }
        catch {
            Start-Sleep -Seconds 3
        }
    }

    Write-Log "$Name did not respond within $WaitSeconds seconds: $Url"
}

try {
    Write-Log "Starting CQV IT Manager local stack."
    Write-Log "Project path: $ProjectPath"

    if (-not $NoKeepAlive) {
        Start-WslKeepAlive
    }

    $wslProjectPath = Convert-ToWslPath -Path $ProjectPath
    Start-DockerInWsl

    $composeCommand = "cd `"$wslProjectPath`" && docker compose -f `"$ComposeFile`" up -d"
    Write-Log "Running Docker Compose: $ComposeFile"
    Invoke-WslBash -Command $composeCommand

    Wait-HttpOk -Name "Backend health check" -Url "http://localhost:8818/api/health"
    Wait-HttpOk -Name "Frontend login page" -Url "http://localhost:3000/manage/it/login"

    Write-Log "CQV IT Manager local stack startup finished."
    Write-Log "Frontend URL: http://localhost:3000/manage/it/"
}
catch {
    Write-Log "Startup failed: $($_.Exception.Message)"
    throw
}
